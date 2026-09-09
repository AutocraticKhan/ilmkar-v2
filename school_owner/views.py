"""Chain / Group Owner dashboard views.

Access model: every view is wrapped in ``owner_required`` — the signed-in
user must be an owner (owns a Chain, or is assigned as a school's owner, or
holds an Owner-role membership). All data is resolved through
``school_owner.utils.owner_schools``, so an owner can only ever see and
affect the schools they own.
"""
import datetime
import json

from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from SAAS_admin.models import School

from .metrics import branch_metrics, consolidated, monthly_statement
from .models import (
    ApprovalRequest,
    BranchAnnouncement,
    Chain,
    GroupPolicy,
    GroupPolicyOverride,
    JobPosting,
    Student,
    StaffMember,
    TransferLog,
)
from .utils import ensure_chain_for_owner, is_owner, owner_schools


def _chain_of(user):
    """The Chain owned by this user, or None.

    Uses an existence query — never ``getattr(user, "owned_chain", None)``,
    which raises RelatedObjectDoesNotExist when the user owns no chain.
    """
    if not getattr(user, "is_authenticated", False):
        return None
    return Chain.objects.filter(owner=user).first()


def _owner_chain(user):
    """The owner's group, auto-created when they own schools but have none.

    Owners are now just accounts assigned to schools; the per-account group
    is created lazily so the superuser never has to set up a named chain.
    """
    chain = _chain_of(user)
    if chain is None and owner_schools(user).exists():
        chain = ensure_chain_for_owner(user)
    return chain


def _visible_branches(user):
    """Schools visible to this owner (the tenant scope)."""
    return list(owner_schools(user))


def _visible_branch(user, school_id):
    """Resolve a School by id, but ONLY if this user owns it.

    This is the isolation guard: an owner can never touch a school outside
    their scope (owner FK / chain / Owner-role membership), even with a
    crafted foreign id.
    """
    if school_id in (None, "", "all"):
        return None
    try:
        return owner_schools(user).get(pk=int(school_id))
    except (School.DoesNotExist, TypeError, ValueError):
        return None


def _is_owner(user):
    return is_owner(user)


owner_required = user_passes_test(_is_owner, login_url="/")


def _pending_count(chain):
    return (
        chain.approval_requests.filter(
            status=ApprovalRequest.Status.PENDING
        ).count()
        if chain
        else 0
    )


def _parse_body(request):
    try:
        return json.loads(request.body or "{}"), None
    except json.JSONDecodeError:
        return None, JsonResponse({"error": "Invalid request body."}, status=400)


# ---------- pages ----------


@login_required
@owner_required
def dashboard(request):
    """Home: combined KPIs, side-by-side branch comparison + scorecard."""
    chain = _owner_chain(request.user)
    branches = [branch_metrics(s) for s in _visible_branches(request.user)]
    return render(
        request,
        "school_owner/dashboard.html",
        {
            "chain": chain,
            "branches": branches,
            "totals": consolidated(branches),
            "pending_approvals": _pending_count(chain),
        },
    )


@login_required
@owner_required
def financials(request):
    """Consolidated financial statement + per-branch breakdown."""
    chain = _owner_chain(request.user)
    schools = _visible_branches(request.user)
    branches = [branch_metrics(s) for s in schools]
    return render(
        request,
        "school_owner/financials.html",
        {
            "chain": chain,
            "branches": branches,
            "totals": consolidated(branches),
            "months": monthly_statement(schools),
        },
    )


# ---------- transfers ----------


@login_required
@owner_required
def transfers(request):
    """Move a student or staff member between branches without re-entering
    their data. The move updates the row's school FK; history is kept in
    TransferLog."""
    chain = _owner_chain(request.user)
    branches = _visible_branches(request.user)
    return render(
        request,
        "school_owner/transfers.html",
        {
            "chain": chain,
            "branches": [
                {"id": b.pk, "name": b.name, "city": b.city} for b in branches
            ],
            "students": [
                s.as_dict() for s in Student.objects.filter(school__in=branches)
            ],
            "staff": [
                m.as_dict() for m in StaffMember.objects.filter(school__in=branches)
            ],
            "history": [
                t.as_dict() for t in (chain.transfers.all()[:25] if chain else [])
            ],
            "pending_approvals": _pending_count(chain),
        },
    )


def _sync_registry_count(school):
    """TODO(placeholder): School.students is the registry number the operator
    console shows; keep it aligned with the placeholder student rows until
    the real admissions module owns that field."""
    school.students = Student.objects.filter(
        school=school, status=Student.Status.ACTIVE
    ).count()
    school.save(update_fields=["students"])


@require_POST
@login_required
@owner_required
def transfer_person(request):
    chain = _owner_chain(request.user)
    if chain is None:
        return JsonResponse(
            {"error": "Set up your owner group first."}, status=400
        )
    data, err = _parse_body(request)
    if err:
        return err

    person_type = data.get("person_type")
    if person_type not in TransferLog.PersonType.values:
        return JsonResponse({"error": "Unknown person type."}, status=400)

    from_school = _visible_branch(request.user, data.get("from_school_id"))
    to_school = _visible_branch(request.user, data.get("to_school_id"))
    if from_school is None or to_school is None:
        return JsonResponse(
            {"error": "Both branches must belong to your group."}, status=400
        )
    if from_school.pk == to_school.pk:
        return JsonResponse({"error": "Pick two different branches."}, status=400)

    person_id = data.get("person_id")
    if person_type == TransferLog.PersonType.STUDENT:
        person = Student.objects.filter(pk=person_id, school=from_school).first()
        if person is None:
            return JsonResponse(
                {"error": "Student not found in the source branch."}, status=404
            )
        display = person.full_name
        with transaction.atomic():
            person.school = to_school
            # The classroom belongs to the old branch — clear it so the
            # receiving branch can assign a new one.
            person.classroom = None
            person.save(update_fields=["school", "classroom"])
            _sync_registry_count(from_school)
            _sync_registry_count(to_school)
    else:
        person = StaffMember.objects.filter(pk=person_id, school=from_school).first()
        if person is None:
            return JsonResponse(
                {"error": "Staff member not found in the source branch."}, status=404
            )
        display = person.full_name
        person.school = to_school
        person.save(update_fields=["school"])
        _sync_registry_count(from_school)
        _sync_registry_count(to_school)

    log = TransferLog.objects.create(
        chain=chain,
        person_type=person_type,
        person_display=display,
        from_school=from_school,
        to_school=to_school,
        note=(data.get("note") or "").strip()[:300],
        moved_by=request.user,
    )
    return JsonResponse({"ok": True, "transfer": log.as_dict()})


# ---------- group-wide policies ----------


@login_required
@owner_required
def policies(request):
    """Group-wide policies with optional per-branch overrides."""
    chain = _owner_chain(request.user)
    branches = _visible_branches(request.user)
    return render(
        request,
        "school_owner/policies.html",
        {
            "chain": chain,
            "branches": [
                {"id": b.pk, "name": b.name, "city": b.city} for b in branches
            ],
            "policies": [
                p.as_dict() for p in (chain.policies.all() if chain else [])
            ],
            "pending_approvals": _pending_count(chain),
        },
    )


@require_POST
@login_required
@owner_required
def policy_create(request):
    chain = _owner_chain(request.user)
    if chain is None:
        return JsonResponse(
            {"error": "Set up your owner group first."}, status=400
        )
    data, err = _parse_body(request)
    if err:
        return err

    name = (data.get("name") or "").strip()
    if not name:
        return JsonResponse({"error": "Policy name is required."}, status=400)
    category = data.get("category")
    if category not in GroupPolicy.Category.values:
        category = GroupPolicy.Category.OTHER

    policy = GroupPolicy.objects.create(
        chain=chain,
        name=name,
        category=category,
        default_value=(data.get("default_value") or "").strip(),
        created_by=request.user,
    )
    return JsonResponse({"policy": policy.as_dict()}, status=201)


@require_POST
@login_required
@owner_required
def policy_override(request, policy_id):
    chain = _chain_of(request.user)
    policy = chain.policies.filter(pk=policy_id).first() if chain else None
    if policy is None:
        return JsonResponse({"error": "Policy not found."}, status=404)
    data, err = _parse_body(request)
    if err:
        return err

    school = _visible_branch(request.user, data.get("school_id"))
    if school is None:
        return JsonResponse({"error": "Pick a branch of your group."}, status=400)
    value = (data.get("value") or "").strip()
    if not value:
        return JsonResponse({"error": "Override value is required."}, status=400)

    GroupPolicyOverride.objects.update_or_create(
        policy=policy, school=school, defaults={"value": value}
    )
    return JsonResponse({"policy": policy.as_dict()})


@require_POST
@login_required
@owner_required
def policy_override_delete(request, policy_id):
    chain = _chain_of(request.user)
    policy = chain.policies.filter(pk=policy_id).first() if chain else None
    if policy is None:
        return JsonResponse({"error": "Policy not found."}, status=404)
    data, err = _parse_body(request)
    if err:
        return err

    school = _visible_branch(request.user, data.get("school_id"))
    if school is None:
        return JsonResponse({"error": "Pick a branch of your group."}, status=400)
    policy.overrides.filter(school=school).delete()
    return JsonResponse({"policy": policy.as_dict()})


@require_POST
@login_required
@owner_required
def policy_delete(request, policy_id):
    chain = _chain_of(request.user)
    policy = chain.policies.filter(pk=policy_id).first() if chain else None
    if policy is None:
        return JsonResponse({"error": "Policy not found."}, status=404)
    name = policy.name
    policy.delete()  # cascades to its per-branch overrides
    return JsonResponse({"ok": True, "name": name})


# ---------- central hiring ----------


@login_required
@owner_required
def hiring(request):
    """Post a job once for the group; staff get placed at the branch that
    needs them."""
    chain = _owner_chain(request.user)
    branches = _visible_branches(request.user)
    return render(
        request,
        "school_owner/hiring.html",
        {
            "chain": chain,
            "branches": [
                {"id": b.pk, "name": b.name, "city": b.city} for b in branches
            ],
            "jobs": [
                j.as_dict() for j in (chain.job_postings.all() if chain else [])
            ],
            "open_jobs": (
                chain.job_postings.filter(status=JobPosting.Status.OPEN).count()
                if chain
                else 0
            ),
            "pending_approvals": _pending_count(chain),
        },
    )


@require_POST
@login_required
@owner_required
def job_create(request):
    chain = _owner_chain(request.user)
    if chain is None:
        return JsonResponse(
            {"error": "Set up your owner group first."}, status=400
        )
    data, err = _parse_body(request)
    if err:
        return err

    title = (data.get("title") or "").strip()
    if not title:
        return JsonResponse({"error": "Job title is required."}, status=400)

    # Preferred branch is optional — null means "place at whichever branch
    # needs them". A foreign branch id is rejected by the isolation guard.
    branch = _visible_branch(request.user, data.get("branch_id"))

    job = JobPosting.objects.create(
        chain=chain,
        title=title,
        description=(data.get("description") or "").strip(),
        preferred_branch=branch,
        created_by=request.user,
    )
    return JsonResponse({"job": job.as_dict()}, status=201)


@require_POST
@login_required
@owner_required
def job_fill(request, job_id):
    """Mark a posting filled and record the branch where staff were placed."""
    chain = _chain_of(request.user)
    job = chain.job_postings.filter(pk=job_id).first() if chain else None
    if job is None:
        return JsonResponse({"error": "Job posting not found."}, status=404)
    data, err = _parse_body(request)
    if err:
        return err

    branch = _visible_branch(request.user, data.get("branch_id"))
    if branch is None:
        return JsonResponse(
            {"error": "Pick the branch where the position was filled."}, status=400
        )

    job.status = JobPosting.Status.FILLED
    job.filled_branch = branch
    job.filled_at = timezone.now()
    job.save(update_fields=["status", "filled_branch", "filled_at"])
    return JsonResponse({"job": job.as_dict()})


@require_POST
@login_required
@owner_required
def job_reopen(request, job_id):
    chain = _chain_of(request.user)
    job = chain.job_postings.filter(pk=job_id).first() if chain else None
    if job is None:
        return JsonResponse({"error": "Job posting not found."}, status=404)

    job.status = JobPosting.Status.OPEN
    job.filled_branch = None
    job.filled_at = None
    job.save(update_fields=["status", "filled_branch", "filled_at"])
    return JsonResponse({"job": job.as_dict()})


@require_POST
@login_required
@owner_required
def job_delete(request, job_id):
    chain = _chain_of(request.user)
    job = chain.job_postings.filter(pk=job_id).first() if chain else None
    if job is None:
        return JsonResponse({"error": "Job posting not found."}, status=404)
    title = job.title
    job.delete()
    return JsonResponse({"ok": True, "title": title})


# ---------- central announcements ----------


@login_required
@owner_required
def announcements(request):
    """Send a notice to all branches at once or to a single branch."""
    chain = _owner_chain(request.user)
    branches = _visible_branches(request.user)
    return render(
        request,
        "school_owner/announcements.html",
        {
            "chain": chain,
            "branches": [
                {"id": b.pk, "name": b.name, "city": b.city} for b in branches
            ],
            "notices": [
                n.as_dict()
                for n in (chain.branch_announcements.all() if chain else [])
            ],
            "pending_approvals": _pending_count(chain),
        },
    )


@require_POST
@login_required
@owner_required
def announcement_create(request):
    chain = _owner_chain(request.user)
    if chain is None:
        return JsonResponse(
            {"error": "Set up your owner group first."}, status=400
        )
    data, err = _parse_body(request)
    if err:
        return err

    title = (data.get("title") or "").strip()
    body = (data.get("body") or "").strip()
    if not title or not body:
        return JsonResponse(
            {"error": "Title and message are required."}, status=400
        )

    # school_id empty/null = every branch; otherwise the isolation guard
    # makes sure the target branch belongs to this owner.
    branch = _visible_branch(request.user, data.get("school_id"))

    notice = BranchAnnouncement.objects.create(
        chain=chain,
        school=branch,
        title=title,
        body=body,
        created_by=request.user,
    )
    return JsonResponse({"announcement": notice.as_dict()}, status=201)


@require_POST
@login_required
@owner_required
def announcement_delete(request, announcement_id):
    chain = _chain_of(request.user)
    notice = (
        chain.branch_announcements.filter(pk=announcement_id).first()
        if chain
        else None
    )
    if notice is None:
        return JsonResponse({"error": "Announcement not found."}, status=404)
    title = notice.title
    notice.delete()
    return JsonResponse({"ok": True, "title": title})


# ---------- approval workflows ----------


@login_required
@owner_required
def approvals(request):
    """Branch requests (budget, new hire, \u2026) decided centrally by the owner.

    TODO(placeholder): the "record a request" action below exists only so
    the workflow is testable before the branch principal dashboard lands —
    principals will submit requests from their own dashboard later.
    """
    chain = _owner_chain(request.user)
    branches = _visible_branches(request.user)
    requests = [
        r.as_dict() for r in (chain.approval_requests.all() if chain else [])
    ]
    return render(
        request,
        "school_owner/approvals.html",
        {
            "chain": chain,
            "branches": [
                {"id": b.pk, "name": b.name, "city": b.city} for b in branches
            ],
            "requests": requests,
            "pending_approvals": sum(
                1 for r in requests if r["status"] == ApprovalRequest.Status.PENDING
            ),
        },
    )


@require_POST
@login_required
@owner_required
def approval_create(request):
    """TODO(placeholder): manual intake of a branch request until branch
    principal dashboards can submit these themselves."""
    chain = _owner_chain(request.user)
    if chain is None:
        return JsonResponse(
            {"error": "Set up your owner group first."}, status=400
        )
    data, err = _parse_body(request)
    if err:
        return err

    branch = _visible_branch(request.user, data.get("school_id"))
    if branch is None:
        return JsonResponse({"error": "Pick a branch of your group."}, status=400)
    title = (data.get("title") or "").strip()
    if not title:
        return JsonResponse({"error": "Request title is required."}, status=400)

    request_type = data.get("request_type")
    if request_type not in ApprovalRequest.Type.values:
        request_type = ApprovalRequest.Type.OTHER

    amount_raw = (data.get("amount") or "").strip()
    amount = None
    if amount_raw:
        try:
            amount = max(0, float(amount_raw))
        except ValueError:
            return JsonResponse({"error": "Amount must be a number."}, status=400)

    req = ApprovalRequest.objects.create(
        chain=chain,
        school=branch,
        request_type=request_type,
        title=title,
        details=(data.get("details") or "").strip(),
        amount=amount,
        requested_by=(data.get("requested_by") or "").strip()[:120],
    )
    return JsonResponse({"request": req.as_dict()}, status=201)


@require_POST
@login_required
@owner_required
def approval_decide(request, request_id):
    """Approve or reject a branch request. Only PENDING requests can be
    decided — the outcome is final (re-deciding is refused)."""
    chain = _chain_of(request.user)
    req = (
        chain.approval_requests.filter(pk=request_id).first() if chain else None
    )
    if req is None:
        return JsonResponse({"error": "Request not found."}, status=404)
    data, err = _parse_body(request)
    if err:
        return err

    decision = data.get("decision")
    if decision not in (ApprovalRequest.Status.APPROVED, ApprovalRequest.Status.REJECTED):
        return JsonResponse(
            {"error": "Decision must be approved or rejected."}, status=400
        )
    if req.status != ApprovalRequest.Status.PENDING:
        return JsonResponse(
            {"error": "This request has already been decided."}, status=400
        )

    req.status = decision
    req.decision_note = (data.get("note") or "").strip()[:300]
    req.decided_at = timezone.now()
    req.save(update_fields=["status", "decision_note", "decided_at"])
    return JsonResponse({"request": req.as_dict()})





