import datetime
import json

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .models import (
    Announcement,
    ImpersonationLog,
    Invoice,
    School,
    SchoolUser,
    SupportTicket,
    SupportReply,
)


def _is_superuser(user):
    return user.is_active and user.is_superuser


def _is_owner(user):
    """True when the user may use the owner dashboard.

    Owners are accounts assigned to own one or more schools (school.owner),
    accounts that own a chain/group, or accounts holding an Owner-role
    membership on a school (Users page). Implemented in school_owner.utils
    to keep the apps decoupled (imported lazily to avoid a cycle).
    """
    if not getattr(user, "is_authenticated", False):
        return False
    from school_owner.utils import is_owner

    return is_owner(user)


def _is_school_admin(user):
    """True when the user may use the school admin dashboard.

    Principals hold a principal-role membership on one school. Imported
    lazily like _is_owner to keep the apps decoupled.
    TODO(integration): when teacher/front-desk apps land, their roles
    route here too.
    """
    if not getattr(user, "is_authenticated", False):
        return False
    from School_Admin.utils import is_school_admin

    return is_school_admin(user)


def _is_teacher(user):
    """True when the user may use the teacher/staff dashboard at
    /teacher/. Teachers hold a teacher-role SchoolUser membership;
    principals are admitted too as a read-through (Teachers.utils).
    Imported lazily like _is_owner to keep the apps decoupled.
    """
    if not getattr(user, "is_authenticated", False):
        return False
    from Teachers.utils import is_teacher

    return is_teacher(user)


def _is_student(user):
    """True when the user may use the student dashboard at /student/.
    Students hold a student-role SchoolUser membership (Student.utils).
    Imported lazily like _is_owner to keep the apps decoupled.
    """
    if not getattr(user, "is_authenticated", False):
        return False
    from Student.utils import is_student

    return is_student(user)


def _is_parent(user):
    """True when the user may use the parent/family dashboard at /parent/.
    Parents hold a parent-role SchoolUser membership (Parents.utils).
    Imported lazily like _is_owner to keep the apps decoupled.
    """
    if not getattr(user, "is_authenticated", False):
        return False
    from Parents.utils import is_parent

    return is_parent(user)


def _is_accountant(user):
    """True when the user may use the finance dashboard at /finance/.
    Accountants hold an accountant-role SchoolUser membership
    (Accountant.utils); principals are admitted too as a read-through
    (approvals + review). Imported lazily like _is_owner.
    """
    if not getattr(user, "is_authenticated", False):
        return False
    from Accountant.utils import is_accountant

    return is_accountant(user)


superuser_required = user_passes_test(_is_superuser, login_url="/")


# Shown when a valid account has no console access. Broad on purpose:
# school-level accounts (created on the Users page) are NOT owner logins
# until the superuser assigns them as a school's owner.
_NO_CONSOLE_ACCESS_MSG = (
    "This account can't sign in to a console. Only platform operators, "
    "school/group owners, school admins (principals), accountants, "
    "teachers/staff, students and parents/families can. Ask the platform "
    "operator to assign a role to your account."
)


def login_view(request):
    """Login page served at the home URL.

    Routes by account type: superusers reach the operator console, chain
    owners their group dashboard, school admins the principal dashboard
    and teachers/staff their dashboard at /teacher/ (Teachers app).
    """
    if request.user.is_authenticated:
        if request.user.is_superuser:
            return redirect("SAAS_admin:dashboard")
        if _is_owner(request.user):
            return redirect("school_owner:dashboard")
        if _is_school_admin(request.user):
            return redirect("School_Admin:dashboard")
        # Accountants: accountant-role memberships land at /finance/
        # (checked AFTER principals so the principal route keeps priority).
        if _is_accountant(request.user):
            return redirect("Accountant:dashboard")
        # Teachers / staff: teacher-role memberships land here (checked
        # AFTER principals so the principal route keeps priority).
        if _is_teacher(request.user):
            return redirect("Teachers:dashboard")
        # Students: student-role memberships land at /student/.
        if _is_student(request.user):
            return redirect("Student:dashboard")
        # Parents/families: parent-role memberships land at /parent/.
        if _is_parent(request.user):
            return redirect("Parents:dashboard")
        return render(
            request,
            "SAAS_admin/login.html",
            {"error": _NO_CONSOLE_ACCESS_MSG},
        )

    error = None
    if request.method == "POST":
        username = request.POST.get("username", "")
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            if _is_superuser(user):
                login(request, user)
                return redirect("SAAS_admin:dashboard")
            # Owners: accounts assigned to own schools (or a chain/group), or
            # holding an Owner-role membership on a school.
            if _is_owner(user):
                login(request, user)
                return redirect("school_owner:dashboard")
            # School admins: principal-role memberships on a school.
            if _is_school_admin(user):
                login(request, user)
                return redirect("School_Admin:dashboard")
            # Accountants: accountant-role memberships land at /finance/.
            if _is_accountant(user):
                login(request, user)
                return redirect("Accountant:dashboard")
            # Teachers / staff: teacher-role memberships land here.
            if _is_teacher(user):
                login(request, user)
                return redirect("Teachers:dashboard")
            # Students: student-role memberships land at /student/.
            if _is_student(user):
                login(request, user)
                return redirect("Student:dashboard")
            # Parents/families: parent-role memberships land at /parent/.
            if _is_parent(user):
                login(request, user)
                return redirect("Parents:dashboard")
            error = _NO_CONSOLE_ACCESS_MSG
        else:
            error = "Invalid username or password."

    return render(request, "SAAS_admin/login.html", {"error": error})


@login_required
@superuser_required
def dashboard(request):
    schools = [
        s.as_dict() for s in School.objects.select_related("chain")
        .annotate(_user_count=Count("memberships"))
    ]
    # Existing accounts the superuser can assign as a school's owner from
    # the add-school drawer. Any active non-operator account is eligible —
    # the owner flag helps the UI group them.
    owners = [
        {
            "id": u.pk,
            "username": u.get_username(),
            "email": u.email or "",
            "is_owner": School.objects.filter(owner=u).exists(),
        }
        for u in User.objects.filter(is_active=True)
        .exclude(is_superuser=True)
        .order_by("username")
    ]
    # Chains remain supported for bulk assignment (Chains page).
    from school_owner.models import Chain

    chains = [c.as_dict() for c in Chain.objects.all()]
    return render(
        request,
        "SAAS_admin/dashboard.html",
        {"schools": schools, "chains": chains, "owners": owners},
    )


@login_required
@superuser_required
def users(request):
    """User management page: pick a school, then manage its users."""
    schools = [
        s.as_dict() for s in School.objects.annotate(_user_count=Count("memberships"))
    ]
    return render(
        request,
        "SAAS_admin/users.html",
        {"schools": schools},
    )


@require_POST
def logout_view(request):
    _end_impersonation_log(request)
    logout(request)
    return redirect("SAAS_admin:home")


# ---------- JSON API (superuser only) ----------


def _school_or_404(school_id):
    try:
        return School.objects.get(pk=school_id)
    except School.DoesNotExist:
        return None


def _parse_body(request):
    try:
        return json.loads(request.body or "{}"), None
    except json.JSONDecodeError:
        return None, JsonResponse({"error": "Invalid request body."}, status=400)


@require_POST
@superuser_required
def school_create(request):
    data, err = _parse_body(request)
    if err:
        return err

    name = (data.get("name") or "").strip()
    city = (data.get("city") or "").strip()
    if not name or not city:
        return JsonResponse(
            {"error": "School name and city are required."}, status=400
        )

    package = data.get("package")
    if package not in School.Package.values:
        package = School.Package.STARTER

    try:
        students = max(0, int(data.get("students") or 0))
    except (TypeError, ValueError):
        students = 0

    renewal_raw = (data.get("renewal") or "").strip()
    renewal = None
    if renewal_raw:
        try:
            renewal = datetime.date.fromisoformat(renewal_raw)
        except ValueError:
            return JsonResponse(
                {"error": "Invalid renewal date. Use YYYY-MM-DD."}, status=400
            )

    # Owner assignment: the superuser picks an EXISTING account (owner_id);
    # that account owns the school and the school joins their group/chain.
    owner = None
    owner_id = data.get("owner_id")
    if owner_id not in (None, "", "null"):
        owner = (
            User.objects.filter(pk=owner_id, is_active=True)
            .exclude(is_superuser=True)
            .first()
        )
        if owner is None:
            return JsonResponse(
                {"error": "Unknown owner account."}, status=400
            )

    # Fallback: assign to an existing chain directly (Chains page flow).
    chain = None
    if owner is None and data.get("chain_id") not in (None, "", "null"):
        chain, chain_err = _resolve_chain(data.get("chain_id"))
        if chain_err:
            return chain_err

    school = School.objects.create(
        name=name,
        city=city,
        chain=chain,
        package=package,
        students=students,
        renewal=renewal,
        status=School.Status.TRIAL,
        contact=(data.get("contact") or "").strip() or "\u2014",
        email=(data.get("email") or "").strip() or "\u2014",
    )
    if owner is not None:
        from school_owner.utils import assign_owner

        assign_owner(school, owner)
    return JsonResponse({"school": school.as_dict()}, status=201)


def _resolve_chain(chain_id):
    """Resolve a chain id strictly — returns (chain, error_response).

    Used anywhere the operator console assigns a school to a chain so a bad
    id never silently drops the assignment.
    """
    if chain_id in (None, "", "null"):
        return None, None
    from school_owner.models import Chain

    try:
        return Chain.objects.get(pk=int(chain_id)), None
    except (Chain.DoesNotExist, TypeError, ValueError):
        return None, JsonResponse({"error": "Unknown chain."}, status=400)


@require_POST
@superuser_required
def school_package(request, school_id):
    school = _school_or_404(school_id)
    if school is None:
        return JsonResponse({"error": "School not found."}, status=404)
    data, err = _parse_body(request)
    if err:
        return err

    package = data.get("package")
    if package not in School.Package.values:
        return JsonResponse({"error": "Unknown package."}, status=400)

    school.package = package
    school.save(update_fields=["package"])
    return JsonResponse({"school": school.as_dict()})


@require_POST
@superuser_required
def school_status(request, school_id):
    school = _school_or_404(school_id)
    if school is None:
        return JsonResponse({"error": "School not found."}, status=404)
    data, err = _parse_body(request)
    if err:
        return err

    status = data.get("status")
    if status not in School.Status.values:
        return JsonResponse({"error": "Unknown status."}, status=400)

    school.status = status
    school.save(update_fields=["status"])
    return JsonResponse({"school": school.as_dict()})


@require_POST
@superuser_required
def school_owner_set(request, school_id):
    """Assign an EXISTING account as the school's owner (or clear it).

    The account doesn't need any special role beforehand — assignment alone
    makes it an owner. The school joins the owner's group so the owner
    dashboard shows it alongside their other schools.
    """
    school = _school_or_404(school_id)
    if school is None:
        return JsonResponse({"error": "School not found."}, status=404)
    data, err = _parse_body(request)
    if err:
        return err

    owner = None
    owner_id = data.get("owner_id")
    if owner_id not in (None, "", "null"):
        owner = (
            User.objects.filter(pk=owner_id, is_active=True)
            .exclude(is_superuser=True)
            .first()
        )
        if owner is None:
            return JsonResponse(
                {"error": "Unknown owner account."}, status=400
            )

    from school_owner.utils import assign_owner

    assign_owner(school, owner)
    return JsonResponse({"school": school.as_dict()})


@require_POST
@superuser_required
def school_delete(request, school_id):
    school = _school_or_404(school_id)
    if school is None:
        return JsonResponse({"error": "School not found."}, status=404)

    name = school.name
    # Collect the user accounts linked to this school before it disappears.
    # Superuser/operator accounts are never removed from here.
    user_ids = list(
        school.memberships.exclude(user__is_superuser=True).values_list(
            "user_id", flat=True
        )
    )
    # Deleting the school cascades to every related row (memberships and any
    # other models linked to it with on_delete=CASCADE).
    school.delete()
    # Then remove the user accounts that belonged exclusively to this school.
    User.objects.filter(id__in=user_ids).delete()
    return JsonResponse(
        {"ok": True, "name": name, "deleted_users": len(user_ids)}
    )


# ---------- user management API (superuser only) ----------


def _membership_or_none(school_id, user_id):
    return (
        SchoolUser.objects.filter(school_id=school_id, user_id=user_id)
        .select_related("user")
        .first()
    )


@require_GET
@superuser_required
def school_users(request, school_id):
    school = _school_or_404(school_id)
    if school is None:
        return JsonResponse({"error": "School not found."}, status=404)
    users = [m.as_dict() for m in school.memberships.select_related("user")]
    return JsonResponse({"school": school.as_dict(), "users": users})


@require_POST
@superuser_required
def user_create(request, school_id):
    school = _school_or_404(school_id)
    if school is None:
        return JsonResponse({"error": "School not found."}, status=404)
    data, err = _parse_body(request)
    if err:
        return err

    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    role = data.get("role")

    if not username or not password:
        return JsonResponse(
            {"error": "Username and password are required."}, status=400
        )
    if role not in SchoolUser.Role.values:
        return JsonResponse({"error": "Unknown role."}, status=400)
    if User.objects.filter(username__iexact=username).exists():
        return JsonResponse({"error": "That username is already taken."}, status=400)

    user = User(
        username=username,
        email=(data.get("email") or "").strip(),
        first_name=(data.get("first_name") or "").strip(),
        last_name=(data.get("last_name") or "").strip(),
    )
    try:
        validate_password(password, user)
    except ValidationError as e:
        return JsonResponse({"error": " ".join(e.messages)}, status=400)

    user.set_password(password)
    user.save()
    membership = SchoolUser.objects.create(school=school, user=user, role=role)
    return JsonResponse({"membership": membership.as_dict()}, status=201)


@require_POST
@superuser_required
def user_role(request, school_id, user_id):
    school = _school_or_404(school_id)
    if school is None:
        return JsonResponse({"error": "School not found."}, status=404)
    membership = _membership_or_none(school_id, user_id)
    if membership is None:
        return JsonResponse({"error": "User not found in this school."}, status=404)
    data, err = _parse_body(request)
    if err:
        return err

    role = data.get("role")
    if role not in SchoolUser.Role.values:
        return JsonResponse({"error": "Unknown role."}, status=400)

    membership.role = role
    membership.save(update_fields=["role"])
    return JsonResponse({"membership": membership.as_dict()})


@require_POST
@superuser_required
def user_delete(request, school_id, user_id):
    school = _school_or_404(school_id)
    if school is None:
        return JsonResponse({"error": "School not found."}, status=404)
    membership = _membership_or_none(school_id, user_id)
    if membership is None:
        return JsonResponse({"error": "User not found in this school."}, status=404)

    if membership.user.is_superuser:
        return JsonResponse(
            {"error": "Operator accounts cannot be deleted here."}, status=400
        )

    username = membership.user.get_username()
    # Deleting the user cascades to the membership row as well.
    membership.user.delete()
    return JsonResponse({"ok": True, "username": username})


# ---------- billing page ----------


@login_required
@superuser_required
def billing(request):
    invoices = [
        i.as_dict() for i in Invoice.objects.select_related("school")
    ]
    schools = [s.as_dict() for s in School.objects.all()]
    return render(
        request,
        "SAAS_admin/billing.html",
        {"invoices": invoices, "schools": schools},
    )


@require_POST
@superuser_required
def invoice_paid(request, invoice_id):
    invoice = Invoice.objects.select_related("school").filter(pk=invoice_id).first()
    if invoice is None:
        return JsonResponse({"error": "Invoice not found."}, status=404)
    invoice.status = Invoice.Status.PAID
    invoice.paid_at = datetime.date.today()
    invoice.save(update_fields=["status", "paid_at"])
    return JsonResponse({"invoice": invoice.as_dict()})


# ---------- usage page ----------


def _usage_risk(latest, prev):
    """Heuristic churn-risk flag from the two most recent usage snapshots."""
    if latest is None:
        return "no_data"
    if prev is not None:
        if prev.logins > 0:
            drop = (prev.logins - latest.logins) / prev.logins
        else:
            drop = 0
        if prev.active_students > 0:
            sdrop = (
                (prev.active_students - latest.active_students)
                / prev.active_students
            )
        else:
            sdrop = 0
        if drop > 0.30 or sdrop > 0.25:
            return "at_risk"
        if drop > 0.10:
            return "watch"
    if latest.logins == 0:
        return "at_risk"
    return "healthy"


@login_required
@superuser_required
def usage(request):
    rows = []
    for school in School.objects.all().order_by("name"):
        snaps = list(school.usage_snapshots.order_by("-date")[:2])
        latest = snaps[0] if snaps else None
        prev = snaps[1] if len(snaps) > 1 else None
        rows.append({
            "id": school.pk,
            "name": school.name,
            "city": school.city,
            "status": school.status,
            "enrolled": school.students,
            "logins": latest.logins if latest else 0,
            "logins_prev": prev.logins if prev else None,
            "storage_mb": latest.storage_mb if latest else 0,
            "active_students": latest.active_students if latest else 0,
            "active_students_prev": prev.active_students if prev else None,
            "snapshot_date": latest.date.isoformat() if latest else None,
            "risk": _usage_risk(latest, prev),
        })
    return render(request, "SAAS_admin/usage.html", {"usage_rows": rows})

# ---------- support page ----------


@login_required
@superuser_required
def support(request):
    tickets = [t.as_dict() for t in SupportTicket.objects.select_related("school")]
    impersonations = [i.as_dict() for i in ImpersonationLog.objects.all()]
    return render(
        request,
        "SAAS_admin/support.html",
        {"tickets": tickets, "impersonations": impersonations},
    )


def _ticket_or_404(ticket_id):
    ticket = SupportTicket.objects.select_related("school").filter(
        pk=ticket_id
    ).first()
    if ticket is None:
        return None, JsonResponse({"error": "Ticket not found."}, status=404)
    return ticket, None


@require_GET
@superuser_required
def ticket_detail(request, ticket_id):
    ticket, err = _ticket_or_404(ticket_id)
    if err:
        return err
    replies = [r.as_dict() for r in ticket.replies.all()]
    return JsonResponse({"ticket": ticket.as_dict(), "replies": replies})


@require_POST
@superuser_required
def ticket_reply(request, ticket_id):
    ticket, err = _ticket_or_404(ticket_id)
    if err:
        return err
    data, err = _parse_body(request)
    if err:
        return err
    body = (data.get("body") or "").strip()
    if not body:
        return JsonResponse({"error": "Reply body is required."}, status=400)
    reply = SupportReply.objects.create(
        ticket=ticket,
        is_staff=True,
        author=request.user.get_username(),
        body=body,
    )
    # a reply moves an open ticket into pending until the school responds
    if ticket.status == SupportTicket.Status.OPEN:
        ticket.status = SupportTicket.Status.PENDING
        ticket.save(update_fields=["status"])
    return JsonResponse({"reply": reply.as_dict(), "ticket": ticket.as_dict()})


@require_POST
@superuser_required
def ticket_status(request, ticket_id):
    ticket, err = _ticket_or_404(ticket_id)
    if err:
        return err
    data, err = _parse_body(request)
    if err:
        return err
    status = data.get("status")
    if status not in SupportTicket.Status.values:
        return JsonResponse({"error": "Unknown status."}, status=400)
    ticket.status = status
    ticket.save(update_fields=["status"])
    return JsonResponse({"ticket": ticket.as_dict()})


@require_POST
@superuser_required
def ticket_priority(request, ticket_id):
    ticket, err = _ticket_or_404(ticket_id)
    if err:
        return err
    data, err = _parse_body(request)
    if err:
        return err
    priority = data.get("priority")
    if priority not in SupportTicket.Priority.values:
        return JsonResponse({"error": "Unknown priority."}, status=400)
    ticket.priority = priority
    ticket.save(update_fields=["priority"])
    return JsonResponse({"ticket": ticket.as_dict()})

# ---------- announcements page ----------


@login_required
@superuser_required
def announcements(request):
    items = [a.as_dict() for a in Announcement.objects.all()]
    return render(
        request,
        "SAAS_admin/announcements.html",
        {"announcements": items},
    )


@require_POST
@superuser_required
def announcement_create(request):
    data, err = _parse_body(request)
    if err:
        return err
    title = (data.get("title") or "").strip()
    body = (data.get("body") or "").strip()
    severity = data.get("severity")
    if not title or not body:
        return JsonResponse(
            {"error": "Title and body are required."}, status=400
        )
    if severity not in Announcement.Severity.values:
        severity = Announcement.Severity.INFO
    item = Announcement.objects.create(
        title=title,
        body=body,
        severity=severity,
        created_by=request.user,
    )
    return JsonResponse({"announcement": item.as_dict()}, status=201)


@require_POST
@superuser_required
def announcement_delete(request, announcement_id):
    item = Announcement.objects.filter(pk=announcement_id).first()
    if item is None:
        return JsonResponse({"error": "Announcement not found."}, status=404)
    title = item.title
    item.delete()
    return JsonResponse({"ok": True, "title": title})


# ---------- impersonation (log in as school) ----------


def _end_impersonation_log(request):
    log_id = request.session.get("impersonation_log_id")
    if log_id:
        ImpersonationLog.objects.filter(
            pk=log_id, ended_at__isnull=True
        ).update(ended_at=timezone.now())


@require_POST
@superuser_required
def impersonate_start(request, school_id):
    school = _school_or_404(school_id)
    if school is None:
        return JsonResponse({"error": "School not found."}, status=404)

    membership = (
        school.memberships.filter(
            role__in=[SchoolUser.Role.OWNER, SchoolUser.Role.PRINCIPAL]
        )
        .select_related("user")
        .first()
    )
    if membership is None:
        membership = school.memberships.select_related("user").first()
    if membership is None:
        return JsonResponse(
            {"error": "This school has no user accounts to sign in as."},
            status=400,
        )
    if membership.user.is_superuser:
        return JsonResponse(
            {"error": "Operator accounts cannot be impersonated."}, status=400
        )

    data, err = _parse_body(request)
    if err:
        return err
    note = (data.get("note") or "").strip()[:200]

    log = ImpersonationLog.objects.create(
        operator=request.user,
        school=school,
        user=membership.user,
        user_display=membership.user.get_username(),
        note=note,
    )
    operator_pk = request.user.pk
    # login() flushes the session in recent Django versions, so any keys we
    # want to survive must be written AFTER switching users.
    login(request, membership.user)
    request.session["impersonator_id"] = operator_pk
    request.session["impersonation_log_id"] = log.pk
    return JsonResponse(
        {"ok": True, "redirect": "/workspace/", "as": membership.user.get_username()}
    )


@require_POST
@login_required
def impersonate_end(request):
    _end_impersonation_log(request)
    op_id = request.session.pop("impersonator_id", None)
    request.session.pop("impersonation_log_id", None)
    operator = (
        User.objects.filter(pk=op_id, is_active=True, is_superuser=True).first()
        if op_id
        else None
    )
    if operator:
        login(request, operator)
        return JsonResponse({"ok": True, "redirect": "/dashboard/"})
    logout(request)
    return JsonResponse({"ok": True, "redirect": "/"})


@login_required
def workspace(request):
    """Stub school workspace shown while impersonating a school account."""
    log = ImpersonationLog.objects.filter(
        pk=request.session.get("impersonation_log_id", 0), ended_at__isnull=True
    ).select_related("school", "user").first()
    if log is None:
        for key in ("impersonator_id", "impersonation_log_id"):
            request.session.pop(key, None)
        return redirect("SAAS_admin:home")

    school = log.school
    membership = SchoolUser.objects.filter(
        school=school, user=request.user
    ).first()
    latest = school.usage_snapshots.order_by("-date").first()
    open_tickets = school.tickets.filter(
        status__in=[SupportTicket.Status.OPEN, SupportTicket.Status.PENDING]
    ).count()
    return render(
        request,
        "SAAS_admin/workspace.html",
        {
            "school": school,
            "log": log,
            "role_display": membership.get_role_display() if membership else "\u2014",
            "latest_usage": latest,
            "open_tickets": open_tickets,
        },
    )


# ---------- chains (groups of schools with a single owner) ----------


@login_required
@superuser_required
def chains(request):
    """Chains page: create groups, assign schools, manage owner logins."""
    from school_owner.models import Chain

    chains_ = [
        c.as_dict() | {"schools": [s.as_dict() for s in c.schools.all()]}
        for c in Chain.objects.all()
    ]
    schools = [
        s.as_dict() for s in School.objects.select_related("chain")
        .annotate(_user_count=Count("memberships"))
    ]
    return render(
        request,
        "SAAS_admin/chains.html",
        {"chains": chains_, "schools": schools},
    )


@require_POST
@superuser_required
def chain_create(request):
    """Create a chain and (optionally) its owner login in one step.

    If ``owner_username`` is given and does not exist yet, the account is
    created (with ``owner_password``). If the username exists, that account
    becomes the owner — best practice for reusing an existing staff account.
    The owner must not already own another chain or be a superuser.
    """
    from school_owner.models import Chain

    data, err = _parse_body(request)
    if err:
        return err

    name = (data.get("name") or "").strip()
    if not name:
        return JsonResponse({"error": "Chain name is required."}, status=400)

    username = (data.get("owner_username") or "").strip()
    if not username:
        return JsonResponse({"error": "Owner username is required."}, status=400)

    owner = User.objects.filter(username__iexact=username).first()
    if owner is None:
        password = data.get("owner_password") or ""
        if not password:
            return JsonResponse(
                {"error": "Password is required for a new owner account."},
                status=400,
            )
        owner = User(
            username=username,
            email=(data.get("owner_email") or "").strip(),
            first_name=(data.get("owner_first_name") or "").strip(),
            last_name=(data.get("owner_last_name") or "").strip(),
        )
        try:
            validate_password(password, owner)
        except ValidationError as e:
            return JsonResponse({"error": " ".join(e.messages)}, status=400)
        owner.set_password(password)
        owner.save()
    elif owner.is_superuser:
        return JsonResponse(
            {"error": "Operator accounts cannot own a chain."}, status=400
        )

    if getattr(owner, "owned_chain", None) is not None:
        return JsonResponse(
            {"error": f"@{owner.get_username()} already owns a chain."}, status=400
        )

    chain = Chain.objects.create(name=name, owner=owner)
    return JsonResponse({"chain": chain.as_dict()}, status=201)


@require_POST
@superuser_required
def chain_assign(request, chain_id):
    """Assign an existing school to a chain. A school belongs to at most one
    chain — assigning re-parents it from any previous chain."""
    from school_owner.models import Chain

    chain = Chain.objects.filter(pk=chain_id).first()
    if chain is None:
        return JsonResponse({"error": "Chain not found."}, status=404)
    data, err = _parse_body(request)
    if err:
        return err

    if data.get("school_id") in (None, "", "null"):
        return JsonResponse({"error": "Pick a school."}, status=400)
    school = School.objects.filter(pk=data.get("school_id")).first()
    if school is None:
        return JsonResponse({"error": "School not found."}, status=404)

    school.chain = chain
    school.save(update_fields=["chain"])
    return JsonResponse({"school": school.as_dict(), "chain": chain.as_dict()})


@require_POST
@superuser_required
def chain_unassign(request, school_id):
    """Remove a school from its chain (school stays in the registry)."""
    school = School.objects.filter(pk=school_id).first()
    if school is None:
        return JsonResponse({"error": "School not found."}, status=404)
    if school.chain_id is None:
        return JsonResponse({"error": "This school is not in a chain."}, status=400)
    school.chain = None
    school.save(update_fields=["chain"])
    return JsonResponse({"school": school.as_dict()})


@require_POST
@superuser_required
def chain_delete(request, chain_id):
    """Delete a chain. Schools remain in the registry (FK is SET_NULL) and
    the owner account is not touched."""
    from school_owner.models import Chain

    chain = Chain.objects.filter(pk=chain_id).first()
    if chain is None:
        return JsonResponse({"error": "Chain not found."}, status=404)
    name = chain.name
    owner_username = chain.owner.get_username()
    chain.delete()
    return JsonResponse({"ok": True, "name": name, "owner_username": owner_username})


@require_POST
@superuser_required
def chain_owner_password(request, chain_id):
    """Set a new password for the chain's owner login."""
    from school_owner.models import Chain

    chain = Chain.objects.filter(pk=chain_id).select_related("owner").first()
    if chain is None:
        return JsonResponse({"error": "Chain not found."}, status=404)
    data, err = _parse_body(request)
    if err:
        return err

    password = data.get("password") or ""
    if not password:
        return JsonResponse({"error": "Password is required."}, status=400)
    try:
        validate_password(password, chain.owner)
    except ValidationError as e:
        return JsonResponse({"error": " ".join(e.messages)}, status=400)
    chain.owner.set_password(password)
    chain.owner.save(update_fields=["password"])
    return JsonResponse({"ok": True, "owner": chain.owner.get_username()})


