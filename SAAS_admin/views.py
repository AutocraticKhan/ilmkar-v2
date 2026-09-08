import datetime
import json

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .models import School


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
    schools = [s.as_dict() for s in School.objects.all()]
    return render(
        request,
        "SAAS_admin/dashboard.html",
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
    school.delete()
    return JsonResponse({"ok": True, "name": name})
