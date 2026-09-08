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
from django.views.decorators.http import require_GET, require_POST

from .models import School, SchoolUser


def _is_superuser(user):
    return user.is_active and user.is_superuser


superuser_required = user_passes_test(_is_superuser, login_url="/")


def login_view(request):
    """Login page served at the home URL."""
    if request.user.is_authenticated:
        if request.user.is_superuser:
            return redirect("SAAS_admin:dashboard")
        return render(
            request,
            "SAAS_admin/login.html",
            {"error": "This account does not have operator access."},
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
            error = "This account does not have operator access."
        else:
            error = "Invalid username or password."

    return render(request, "SAAS_admin/login.html", {"error": error})


@login_required
@superuser_required
def dashboard(request):
    schools = [
        s.as_dict() for s in School.objects.annotate(_user_count=Count("memberships"))
    ]
    return render(
        request,
        "SAAS_admin/dashboard.html",
        {"schools": schools},
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

    school = School.objects.create(
        name=name,
        city=city,
        package=package,
        students=students,
        renewal=renewal,
        status=School.Status.TRIAL,
        contact=(data.get("contact") or "").strip() or "\u2014",
        email=(data.get("email") or "").strip() or "\u2014",
    )
    return JsonResponse({"school": school.as_dict()}, status=201)


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
