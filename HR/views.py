"""HR / People dashboard views.

Access model: every view is wrapped in ``hr_required`` — the signed-in
user must hold a ``SchoolUser`` membership with the ``hr`` role or the
``principal`` role (read-through, see ``utils``). PRINCIPALS ARE
READ-ONLY: every mutation endpoint is additionally wrapped in
``hr_write_required`` (``utils.can_mutate``), so a principal browsing
/hr/ can review everything but never decide leave, mark attendance,
hire, or feed payroll.

All data is resolved through ``utils.current_school`` — an HR user can
only ever see and affect the ONE school their account belongs to.

Mutation endpoints follow the platform conventions: JSON body in, JSON
out, every write appends an ``AuditLog`` row (the approval trail).
Leave approvals intentionally write to ``School_Admin.LeaveRequest``
(the single source of truth shared with the principal's dashboard).
"""
import datetime
import json
from decimal import Decimal, InvalidOperation
from functools import wraps

from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from School_Admin.models import LeaveRequest, StaffMember

from . import metrics, services
from .models import (
    Appraisal,
    AttendanceRecord,
    AuditLog,
    JobApplication,
    JobPosting,
    Interview,
    LeaveBalance,
    OnboardingChecklist,
    PayrollInput,
    StaffContract,
    StaffDocument,
    TrainingEnrollment,
    TrainingProgram,
)
from .utils import can_mutate, current_school, is_hr


def _school_of(request):
    """The tenant scope of this HR user (their ONE school)."""
    return current_school(request.user)


def _is_hr(user):
    return is_hr(user)


hr_required = user_passes_test(_is_hr, login_url="/")


def hr_write_required(view):
    """Mutation guard: HR staff only. Principals (read-through) get a
    JSON 403 instead of a redirect — the page JS shows the read-only
    toast and the dashboard keeps its 'changes are disabled' banner."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not can_mutate(request.user):
            return JsonResponse(
                {
                    "error": "Read-only access — only HR staff can make "
                             "changes (principals view only)."
                },
                status=403,
            )
        return view(request, *args, **kwargs)

    return wrapper


def _parse_body(request):
    try:
        return json.loads(request.body or "{}"), None
    except json.JSONDecodeError:
        return None, JsonResponse({"error": "Invalid request body."}, status=400)


def _actor(request):
    """Username stamped onto audit rows / approval trails."""
    return request.user.get_username()


def _parse_amount(value):
    """Decimal amount from a request field, or None when invalid."""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return amount if amount >= 0 else None


def _parse_date(value):
    """ISO date from a request field, or None when invalid/absent."""
    if not value:
        return None
    try:
        return datetime.date.fromisoformat(str(value))
    except ValueError:
        return None


def _bad(message):
    return JsonResponse({"error": message}, status=400)


def _forbidden(message):
    return JsonResponse({"error": message}, status=403)


# ---------- snapshot home ----------


@login_required
@hr_required
def dashboard(request):
    """People snapshot: headcount, the open work queue (leave approvals,
    document expiry, onboarding), recruitment pipeline, payroll-input
    state and the latest audited actions."""
    school = _school_of(request)
    today = datetime.date.today()
    period = services.current_period(today)

    staff_qs = StaffMember.objects.filter(school=school)
    active_staff = staff_qs.filter(is_active=True).count()
    new_this_month = staff_qs.filter(
        join_date__year=today.year, join_date__month=today.month
    ).count()

    leaves = metrics.pending_leaves(school)
    doc_alerts = metrics.doc_alerts(school, today=today)
    onboarding = metrics.onboarding_progress(school)
    open_tasks = OnboardingChecklist.objects.filter(
        school=school, is_done=False
    ).count()

    upcoming_interviews = [
        i.as_dict()
        for i in Interview.objects.filter(
            school=school,
            outcome=Interview.Outcome.SCHEDULED,
            scheduled_on__gte=today,
        ).select_related("application")[:6]
    ]

    open_payroll = None
    from Accountant.models import PayrollPeriod

    draft_run = PayrollPeriod.objects.filter(
        school=school, period=period, status=PayrollPeriod.Status.DRAFT
    ).first()
    if draft_run is not None:
        open_payroll = draft_run.as_dict()

    return render(
        request,
        "HR/dashboard.html",
        {
            "school": school,
            "period": period,
            "today": today.isoformat(),
            "kpis": {
                "active_staff": active_staff,
                "total_staff": staff_qs.count(),
                "new_this_month": new_this_month,
                "pending_leaves": leaves.count(),
            },
            "doc_alerts": doc_alerts,
            "doc_alert_count": len(doc_alerts),
            "expired_contracts": metrics.expired_contracts(school, today=today),
            "pending_leave_rows": [l.as_dict() for l in leaves[:6]],
            "pending_leave_total": leaves.count(),
            "onboarding": onboarding[:5],
            "onboarding_open_tasks": open_tasks,
            "pipeline": metrics.recruitment_pipeline(school),
            "upcoming_interviews": upcoming_interviews,
            "payroll_overview": metrics.payroll_input_overview(school, period),
            "draft_payroll": open_payroll,
            "appraisals": metrics.appraisal_summary(school),
            "training": metrics.training_summary(school),
            "recent_audit": [
                a.as_dict() for a in AuditLog.objects.filter(school=school)[:8]
            ],
        },
    )


# ---------- staff directory & contracts ----------


def _directory_rows(school):
    """One directory row per staff member: latest contract, open
    onboarding tasks and active/inactive state attached."""
    contracts = {}
    for contract in StaffContract.objects.filter(
        school=school
    ).select_related("staff"):
        contracts.setdefault(contract.staff_id, contract)  # first = latest
    open_tasks = {}
    for task in OnboardingChecklist.objects.filter(school=school, is_done=False):
        open_tasks[task.staff_id] = open_tasks.get(task.staff_id, 0) + 1
    rows = []
    for member in StaffMember.objects.filter(school=school):
        contract = contracts.get(member.pk)
        rows.append({
            "id": member.pk,
            "full_name": member.full_name,
            "designation": member.designation or "—",
            "department": member.department or "—",
            "phone": member.phone or "—",
            "email": member.email or "—",
            "join_date": (
                member.join_date.isoformat() if member.join_date else None
            ),
            "is_active": member.is_active,
            "contract": contract.as_dict() if contract else None,
            "contract_expired": bool(
                contract
                and contract.status == StaffContract.Status.ACTIVE
                and contract.is_expired
            ),
            "open_onboarding": open_tasks.get(member.pk, 0),
        })
    return rows


@login_required
@hr_required
def staff(request):
    """Staff directory & contracts: every staff member with their
    latest contract, onboarding status and active/inactive state."""
    school = _school_of(request)
    return render(
        request,
        "HR/staff.html",
        {
            "school": school,
            "staff": _directory_rows(school),
            "active_staff": StaffMember.objects.filter(
                school=school, is_active=True
            ).count(),
        },
    )


@login_required
@hr_required
@hr_write_required
@require_POST
def staff_create(request):
    """Hire: create the staff member, their first contract, and seed the
    onboarding checklist (the recruitment 'hire' flow reuses this)."""
    school = _school_of(request)
    body, error = _parse_body(request)
    if error:
        return error
    full_name = str(body.get("full_name", "")).strip()
    if not full_name:
        return _bad("Staff name is required.")
    join_date = _parse_date(body.get("join_date")) or datetime.date.today()
    member = StaffMember.objects.create(
        school=school,
        full_name=full_name,
        designation=str(body.get("designation", "")).strip(),
        department=str(body.get("department", "")).strip(),
        phone=str(body.get("phone", "")).strip(),
        email=str(body.get("email", "")).strip(),
        join_date=join_date,
    )
    salary = _parse_amount(body.get("monthly_salary"))
    StaffContract.objects.create(
        school=school,
        staff=member,
        kind=str(body.get("contract_kind") or StaffContract.Kind.PERMANENT),
        start_date=join_date,
        monthly_salary=salary or 0,
    )
    tasks = services.start_onboarding(school, member, due_date=join_date)
    AuditLog.record(
        school, _actor(request), "staff hired", member.full_name,
        note=f"contract + {tasks} onboarding task(s) created",
    )
    return JsonResponse(
        {"member": member.as_dict(), "onboarding": tasks}, status=201
    )


@login_required
@hr_required
@hr_write_required
@require_POST
def staff_toggle(request, staff_id):
    """Deactivate/reactivate a staff member (leaving keeps history)."""
    school = _school_of(request)
    member = StaffMember.objects.filter(school=school, pk=staff_id).first()
    if member is None:
        return JsonResponse({"error": "Staff member not found."}, status=404)
    member.is_active = not member.is_active
    member.save(update_fields=["is_active"])
    AuditLog.record(
        school, _actor(request),
        "staff reactivated" if member.is_active else "staff deactivated",
        member.full_name,
    )
    return JsonResponse({"member": member.as_dict()})


@login_required
@hr_required
@hr_write_required
@require_POST
def contract_create(request):
    """Add/renew a contract for an existing staff member (the previous
    one is closed so only ONE stays active per staff member)."""
    school = _school_of(request)
    body, error = _parse_body(request)
    if error:
        return error
    member = StaffMember.objects.filter(
        school=school, pk=body.get("staff_id")
    ).first()
    if member is None:
        return _bad("Pick a staff member.")
    start_date = _parse_date(body.get("start_date")) or datetime.date.today()
    StaffContract.objects.filter(
        school=school, staff=member, status=StaffContract.Status.ACTIVE
    ).update(status=StaffContract.Status.ENDED)
    salary = _parse_amount(body.get("monthly_salary"))
    contract = StaffContract.objects.create(
        school=school,
        staff=member,
        kind=str(body.get("kind") or StaffContract.Kind.PERMANENT),
        start_date=start_date,
        end_date=_parse_date(body.get("end_date")),
        monthly_salary=salary or 0,
        notes=str(body.get("notes", "")).strip(),
    )
    AuditLog.record(
        school, _actor(request), "contract created",
        f"{member.full_name} — {contract.get_kind_display()}",
        note=f"from {contract.start_date.isoformat()}"
        + (f" to {contract.end_date.isoformat()}" if contract.end_date else ""),
    )
    return JsonResponse({"contract": contract.as_dict()}, status=201)


@login_required
@hr_required
@hr_write_required
@require_POST
def contract_end(request, contract_id):
    """End a contract early (staff leaving / terms changed)."""
    school = _school_of(request)
    contract = StaffContract.objects.filter(school=school, pk=contract_id).first()
    if contract is None:
        return JsonResponse({"error": "Contract not found."}, status=404)
    contract.status = StaffContract.Status.ENDED
    contract.save(update_fields=["status"])
    AuditLog.record(
        school, _actor(request), "contract ended",
        f"{contract.staff.full_name} — {contract.get_kind_display()}",
    )
    return JsonResponse({"contract": contract.as_dict()})


# ---------- attendance ----------


def _month_days(year, month):
    """[{iso, day, weekday, weekend}] for the attendance grid header."""
    import calendar

    days = []
    last = calendar.monthrange(year, month)[1]
    for day in range(1, last + 1):
        d = datetime.date(year, month, day)
        days.append({
            "iso": d.isoformat(),
            "day": day,
            "weekday": d.weekday(),
            "weekend": d.weekday() >= 5,
        })
    return days


@login_required
@hr_required
def attendance(request):
    """Monthly attendance grid (one row per staff member, one column per
    day). HR marks; the principal sees the same grid read-only."""
    school = _school_of(request)
    try:
        year = int(request.GET.get("year", datetime.date.today().year))
        month = int(request.GET.get("month", datetime.date.today().month))
    except (TypeError, ValueError):
        today = datetime.date.today()
        year, month = today.year, today.month
    rows = metrics.attendance_month(school, year, month)
    marked_total = sum(r["marked"] for r in rows)
    present_total = sum(r["present"] for r in rows)
    return render(
        request,
        "HR/attendance.html",
        {
            "school": school,
            "year": year,
            "month": month,
            "month_label": datetime.date(year, month, 1).strftime("%B %Y"),
            "days": _month_days(year, month),
            "rows": rows,
            "marked_total": marked_total,
            "attendance_pct": (
                round(100 * present_total / marked_total, 1)
                if marked_total else None
            ),
            "prev": _shift_month(year, month, -1),
            "next": _shift_month(year, month, 1),
        },
    )


@login_required
@hr_required
@hr_write_required
@require_POST
def attendance_mark(request):
    """Mark (or re-mark) one staff member's attendance for one day.
    ``unpaid`` absents flow into the payroll bridge as a deduction."""
    school = _school_of(request)
    body, error = _parse_body(request)
    if error:
        return error
    member = StaffMember.objects.filter(
        school=school, pk=body.get("staff_id")
    ).first()
    if member is None:
        return _bad("Pick a staff member.")
    day = _parse_date(body.get("date"))
    if day is None:
        return _bad("Pick a date.")
    status = str(body.get("status") or AttendanceRecord.Status.PRESENT)
    if status not in AttendanceRecord.Status.values:
        return _bad("Invalid attendance status.")
    record, created = AttendanceRecord.objects.update_or_create(
        school=school,
        staff=member,
        date=day,
        defaults={
            "status": status,
            "unpaid": bool(body.get("unpaid")) and status == AttendanceRecord.Status.ABSENT,
            "note": str(body.get("note", "")).strip()[:200],
            "marked_by": _actor(request),
        },
    )
    AuditLog.record(
        school, _actor(request), "attendance marked",
        f"{member.full_name} — {day.isoformat()}",
        note=record.get_status_display()
        + (" (unpaid)" if record.unpaid else ""),
    )
    return JsonResponse({"record": record.as_dict()}, status=201 if created else 200)


def _shift_month(year, month, delta):
    month += delta
    if month == 0:
        return {"year": year - 1, "month": 12}
    if month == 13:
        return {"year": year + 1, "month": 1}
    return {"year": year, "month": month}


# ---------- leave approvals + balances ----------


def _leave_rows(school):
    """Leave requests with each staff member's balance snapshot."""
    balances = {
        b.staff_id: b for b in LeaveBalance.objects.filter(school=school)
    }
    return [
        {
            **leave.as_dict(),
            "remaining": (
                float(balances[leave.staff_id].remaining)
                if leave.staff_id in balances else None
            ),
        }
        for leave in LeaveRequest.objects.filter(school=school)
        .select_related("staff")[:120]
    ]


@login_required
@hr_required
def leaves(request):
    """Leave approvals: pending queue first, then history + per-staff
    balances. HR and the principal decide on the SAME rows (the
    principal's dashboard shows its own view of them)."""
    school = _school_of(request)
    return render(
        request,
        "HR/leaves.html",
        {
            "school": school,
            "leaves": _leave_rows(school),
            "pending": LeaveRequest.objects.filter(
                school=school, status=LeaveRequest.Status.PENDING
            ).count(),
            "balances": [
                b.as_dict() for b in LeaveBalance.objects.filter(school=school)
            ],
            "staff": [
                {"id": m.pk, "name": m.full_name}
                for m in StaffMember.objects.filter(school=school, is_active=True)
            ],
            "can_edit": can_mutate(request.user),
        },
    )


@login_required
@hr_required
@hr_write_required
@require_POST
def leave_create(request):
    """Record a leave request on a staff member's behalf (walk-up /
    phone requests — the staff-side app will POST these itself later)."""
    school = _school_of(request)
    body, error = _parse_body(request)
    if error:
        return error
    member = StaffMember.objects.filter(
        school=school, pk=body.get("staff_id")
    ).first()
    if member is None:
        return _bad("Pick a staff member.")
    from_date = _parse_date(body.get("from_date"))
    to_date = _parse_date(body.get("to_date")) or from_date
    if from_date is None:
        return _bad("Pick a from date.")
    if to_date < from_date:
        return _bad("To date can't be before the from date.")
    leave = LeaveRequest.objects.create(
        school=school,
        staff=member,
        from_date=from_date,
        to_date=to_date,
        reason=str(body.get("reason", "")).strip()[:300],
    )
    AuditLog.record(
        school, _actor(request), "leave filed",
        f"{member.full_name} {from_date.isoformat()}→{to_date.isoformat()}",
    )
    return JsonResponse({"leave": leave.as_dict()}, status=201)


def _apply_leave_balance(school, leave):
    """Approved leave consumes the staff member's yearly balance; unpaid
    leave is tracked separately (it deducts in payroll input)."""
    balance, _ = LeaveBalance.objects.get_or_create(
        school=school, staff=leave.staff, year=leave.from_date.year
    )
    days = (leave.to_date - leave.from_date).days + 1
    balance.used += days
    if "unpaid" in (leave.reason or "").lower():
        balance.unpaid_used += days
    balance.save()
    return balance


@login_required
@hr_required
@hr_write_required
@require_POST
def leave_approve(request, leave_id):
    """Approve a leave: freezes the request, consumes the yearly
    balance, and writes LEAVE attendance rows for the period so the
    payroll bridge sees paid leave (never a deduction)."""
    school = _school_of(request)
    leave = LeaveRequest.objects.filter(
        school=school, pk=leave_id
    ).select_related("staff").first()
    if leave is None:
        return JsonResponse({"error": "Leave request not found."}, status=404)
    if leave.status != LeaveRequest.Status.PENDING:
        return _bad("This leave has already been decided.")
    body, error = _parse_body(request)
    if error:
        return error
    leave.status = LeaveRequest.Status.APPROVED
    leave.decision_note = str(body.get("note", "")).strip()[:300]
    leave.decided_at = timezone.now()
    leave.save()
    balance = _apply_leave_balance(school, leave)
    # Attendance rows for the leave period so payroll sees paid leave.
    day = leave.from_date
    while day <= leave.to_date:
        AttendanceRecord.objects.update_or_create(
            school=school,
            staff=leave.staff,
            date=day,
            defaults={
                "status": AttendanceRecord.Status.LEAVE,
                "unpaid": False,
                "note": f"Approved leave #{leave.pk}",
                "marked_by": _actor(request),
            },
        )
        day += datetime.timedelta(days=1)
    AuditLog.record(
        school, _actor(request), "leave approved",
        f"{leave.staff.full_name} "
        f"{leave.from_date.isoformat()}→{leave.to_date.isoformat()}",
        note=leave.decision_note or f"{float(balance.remaining)} day(s) left",
    )
    return JsonResponse({"leave": leave.as_dict()})


@login_required
@hr_required
@hr_write_required
@require_POST
def leave_reject(request, leave_id):
    """Reject a pending leave with a short reason."""
    school = _school_of(request)
    leave = LeaveRequest.objects.filter(
        school=school, pk=leave_id
    ).select_related("staff").first()
    if leave is None:
        return JsonResponse({"error": "Leave request not found."}, status=404)
    if leave.status != LeaveRequest.Status.PENDING:
        return _bad("This leave has already been decided.")
    body, error = _parse_body(request)
    if error:
        return error
    leave.status = LeaveRequest.Status.REJECTED
    leave.decision_note = str(body.get("note", "")).strip()[:300]
    leave.decided_at = timezone.now()
    leave.save()
    AuditLog.record(
        school, _actor(request), "leave rejected",
        f"{leave.staff.full_name} "
        f"{leave.from_date.isoformat()}→{leave.to_date.isoformat()}",
        note=leave.decision_note,
    )
    return JsonResponse({"leave": leave.as_dict()})


@login_required
@hr_required
@hr_write_required
@require_POST
def balance_create(request):
    """Set a staff member's leave entitlement for a year (upsert)."""
    school = _school_of(request)
    body, error = _parse_body(request)
    if error:
        return error
    member = StaffMember.objects.filter(
        school=school, pk=body.get("staff_id")
    ).first()
    if member is None:
        return _bad("Pick a staff member.")
    try:
        year = int(body.get("year") or datetime.date.today().year)
    except (TypeError, ValueError):
        year = datetime.date.today().year
    entitled = _parse_amount(body.get("entitled"))
    carried = _parse_amount(body.get("carried_over"))
    balance, _ = LeaveBalance.objects.get_or_create(
        school=school, staff=member, year=year
    )
    if entitled is not None:
        balance.entitled = entitled
    if carried is not None:
        balance.carried_over = carried
    balance.save()
    AuditLog.record(
        school, _actor(request), "leave balance set",
        f"{member.full_name} — {year}",
        note=f"entitled {balance.entitled} + carried {balance.carried_over}",
    )
    return JsonResponse({"balance": balance.as_dict()}, status=201)


# ---------- recruitment ----------


@login_required
@hr_required
def recruitment(request):
    """Job postings -> applicants -> interviews (the hiring funnel)."""
    school = _school_of(request)
    today = datetime.date.today()
    postings = [p.as_dict() for p in school.hr_job_postings.all()]
    applications = [
        a.as_dict()
        for a in JobApplication.objects.filter(school=school)
        .select_related("posting", "posting")[:150]
    ]
    interviews = [
        i.as_dict()
        for i in Interview.objects.filter(school=school)
        .select_related("application")[:80]
    ]
    pipeline = metrics.recruitment_pipeline(school)
    return render(
        request,
        "HR/recruitment.html",
        {
            "school": school,
            "postings": postings,
            "applications": applications,
            "interviews": interviews,
            "pipeline": pipeline,
            "today": today.isoformat(),
            "can_edit": can_mutate(request.user),
        },
    )


@login_required
@hr_required
@hr_write_required
@require_POST
def posting_create(request):
    """Advertise a vacancy."""
    school = _school_of(request)
    body, error = _parse_body(request)
    if error:
        return error
    title = str(body.get("title", "")).strip()
    if not title:
        return _bad("Job title is required.")
    try:
        openings = max(1, int(body.get("openings") or 1))
    except (TypeError, ValueError):
        openings = 1
    posting = JobPosting.objects.create(
        school=school,
        title=title[:200],
        department=str(body.get("department", "")).strip(),
        openings=openings,
        description=str(body.get("description", "")).strip(),
        posted_on=_parse_date(body.get("posted_on")) or datetime.date.today(),
        closes_on=_parse_date(body.get("closes_on")),
    )
    AuditLog.record(school, _actor(request), "posting opened", posting.title)
    return JsonResponse({"posting": posting.as_dict()}, status=201)


@login_required
@hr_required
@hr_write_required
@require_POST
def posting_close(request, posting_id):
    """Close or mark a posting filled (stops new applications)."""
    school = _school_of(request)
    posting = school.hr_job_postings.filter(pk=posting_id).first()
    if posting is None:
        return JsonResponse({"error": "Posting not found."}, status=404)
    body, error = _parse_body(request)
    if error:
        return error
    status = str(body.get("status") or JobPosting.Status.CLOSED)
    if status not in (JobPosting.Status.CLOSED, JobPosting.Status.FILLED):
        return _bad("Status must be closed or filled.")
    posting.status = status
    posting.save(update_fields=["status"])
    AuditLog.record(
        school, _actor(request), f"posting {status}", posting.title
    )
    return JsonResponse({"posting": posting.as_dict()})


@login_required
@hr_required
@hr_write_required
@require_POST
def application_create(request):
    """Add an applicant to a posting's funnel."""
    school = _school_of(request)
    body, error = _parse_body(request)
    if error:
        return error
    posting = school.hr_job_postings.filter(pk=body.get("posting_id")).first()
    if posting is None:
        return _bad("Pick a job posting.")
    name = str(body.get("candidate_name", "")).strip()
    if not name:
        return _bad("Candidate name is required.")
    application = JobApplication.objects.create(
        school=school,
        posting=posting,
        candidate_name=name,
        phone=str(body.get("phone", "")).strip(),
        email=str(body.get("email", "")).strip(),
        experience=str(body.get("experience", "")).strip(),
        note=str(body.get("note", "")).strip(),
    )
    AuditLog.record(
        school, _actor(request), "application added",
        f"{name} — {posting.title}",
    )
    return JsonResponse({"application": application.as_dict()}, status=201)


@login_required
@hr_required
@hr_write_required
@require_POST
def application_stage(request, application_id):
    """Move an applicant along the funnel (shortlist, offer, reject...)."""
    school = _school_of(request)
    application = JobApplication.objects.filter(
        school=school, pk=application_id
    ).select_related("posting").first()
    if application is None:
        return JsonResponse({"error": "Application not found."}, status=404)
    body, error = _parse_body(request)
    if error:
        return error
    stage = str(body.get("stage") or "")
    if stage not in JobApplication.Stage.values:
        return _bad("Invalid stage.")
    application.stage = stage
    application.note = str(body.get("note", application.note)).strip()[:300]
    application.save()
    AuditLog.record(
        school, _actor(request), "applicant moved",
        f"{application.candidate_name} — {application.get_stage_display()}",
    )
    return JsonResponse({"application": application.as_dict()})


@login_required
@hr_required
@hr_write_required
@require_POST
def application_hire(request, application_id):
    """HIRED: convert an applicant into a staff member (first contract +
    onboarding checklist seeded), mark the posting filled and close the
    funnel stage. This is where recruitment hands over to HR records."""
    school = _school_of(request)
    application = JobApplication.objects.filter(
        school=school, pk=application_id
    ).select_related("posting").first()
    if application is None:
        return JsonResponse({"error": "Application not found."}, status=404)
    if application.stage == JobApplication.Stage.HIRED:
        return _bad("This applicant is already hired.")
    body, error = _parse_body(request)
    if error:
        return error
    join_date = _parse_date(body.get("join_date")) or datetime.date.today()
    salary = _parse_amount(body.get("monthly_salary"))
    member = StaffMember.objects.create(
        school=school,
        full_name=application.candidate_name,
        designation=application.posting.title,
        department=application.posting.department,
        phone=application.phone,
        email=application.email,
        join_date=join_date,
    )
    StaffContract.objects.create(
        school=school,
        staff=member,
        kind=str(body.get("contract_kind") or StaffContract.Kind.PROBATION),
        start_date=join_date,
        monthly_salary=salary or 0,
        notes=f"Hired for {application.posting.title}",
    )
    tasks = services.start_onboarding(school, member, due_date=join_date)
    application.stage = JobApplication.Stage.HIRED
    application.save(update_fields=["stage"])
    posting = application.posting
    if posting.status == JobPosting.Status.OPEN:
        posting.status = JobPosting.Status.FILLED
        posting.save(update_fields=["status"])
    AuditLog.record(
        school, _actor(request), "applicant hired",
        f"{application.candidate_name} — {posting.title}",
        note=f"staff #{member.pk} + {tasks} onboarding task(s)",
    )
    return JsonResponse(
        {"application": application.as_dict(), "staff_id": member.pk},
        status=201,
    )


@login_required
@hr_required
@hr_write_required
@require_POST
def interview_create(request):
    """Schedule an interview round for an applicant."""
    school = _school_of(request)
    body, error = _parse_body(request)
    if error:
        return error
    application = JobApplication.objects.filter(
        school=school, pk=body.get("application_id")
    ).first()
    if application is None:
        return _bad("Pick an applicant.")
    day = _parse_date(body.get("scheduled_on"))
    if day is None:
        return _bad("Pick an interview date.")
    round_no = application.interviews.count() + 1
    interview = Interview.objects.create(
        school=school,
        application=application,
        round_no=round_no,
        scheduled_on=day,
        scheduled_at=str(body.get("scheduled_at", "")).strip()[:10],
        interviewer=str(body.get("interviewer", "")).strip(),
        note=str(body.get("note", "")).strip(),
    )
    if application.stage == JobApplication.Stage.NEW:
        application.stage = JobApplication.Stage.SHORTLISTED
        application.save(update_fields=["stage"])
    AuditLog.record(
        school, _actor(request), "interview scheduled",
        f"{application.candidate_name} — R{round_no} on {day.isoformat()}",
    )
    return JsonResponse({"interview": interview.as_dict()}, status=201)


@login_required
@hr_required
@hr_write_required
@require_POST
def interview_outcome(request, interview_id):
    """Record an interview's outcome (+ score). Passing moves the
    applicant to the interviewed stage."""
    school = _school_of(request)
    interview = Interview.objects.filter(
        school=school, pk=interview_id
    ).select_related("application").first()
    if interview is None:
        return JsonResponse({"error": "Interview not found."}, status=404)
    body, error = _parse_body(request)
    if error:
        return error
    outcome = str(body.get("outcome") or "")
    if outcome not in Interview.Outcome.values:
        return _bad("Invalid outcome.")
    interview.outcome = outcome
    interview.note = str(body.get("note", interview.note)).strip()[:300]
    score = body.get("score")
    if score not in (None, ""):
        try:
            interview.score = max(0, min(100, int(score)))
        except (TypeError, ValueError):
            return _bad("Score must be a number (0-100).")
    interview.save()
    if outcome == Interview.Outcome.PASSED:
        application = interview.application
        if application.stage in (
            JobApplication.Stage.NEW, JobApplication.Stage.SHORTLISTED
        ):
            application.stage = JobApplication.Stage.INTERVIEWED
            application.save(update_fields=["stage"])
    AuditLog.record(
        school, _actor(request), "interview outcome",
        f"{interview.application.candidate_name} — R{interview.round_no} "
        f"{interview.get_outcome_display()}",
        note=interview.note,
    )
    return JsonResponse({"interview": interview.as_dict()})


# ---------- onboarding ----------


@login_required
@hr_required
def onboarding(request):
    """Onboarding checklists: per-hire progress plus every open task."""
    school = _school_of(request)
    tasks = [
        t.as_dict()
        for t in OnboardingChecklist.objects.filter(school=school)
        .select_related("staff")[:200]
    ]
    return render(
        request,
        "HR/onboarding.html",
        {
            "school": school,
            "progress": metrics.onboarding_progress(school),
            "tasks": tasks,
            "staff": [
                {"id": m.pk, "name": m.full_name}
                for m in StaffMember.objects.filter(school=school, is_active=True)
            ],
            "can_edit": can_mutate(request.user),
        },
    )


@login_required
@hr_required
@hr_write_required
@require_POST
def onboarding_start(request, staff_id):
    """Seed the default checklist for a hire (idempotent)."""
    school = _school_of(request)
    member = StaffMember.objects.filter(school=school, pk=staff_id).first()
    if member is None:
        return JsonResponse({"error": "Staff member not found."}, status=404)
    created = services.start_onboarding(school, member)
    AuditLog.record(
        school, _actor(request), "onboarding started", member.full_name,
        note=f"{created} task(s) added",
    )
    return JsonResponse({"created": created})


@login_required
@hr_required
@hr_write_required
@require_POST
def onboarding_toggle(request, task_id):
    """Tick / untick an onboarding task (done_at stamped on tick)."""
    school = _school_of(request)
    task = OnboardingChecklist.objects.filter(school=school, pk=task_id).first()
    if task is None:
        return JsonResponse({"error": "Task not found."}, status=404)
    task.is_done = not task.is_done
    task.done_at = timezone.now() if task.is_done else None
    task.save(update_fields=["is_done", "done_at"])
    AuditLog.record(
        school, _actor(request),
        "onboarding task done" if task.is_done else "onboarding task reopened",
        f"{task.title} — {task.staff.full_name}",
    )
    return JsonResponse({"task": task.as_dict()})


@login_required
@hr_required
@hr_write_required
@require_POST
def onboarding_add(request):
    """Add a custom task to a hire's checklist."""
    school = _school_of(request)
    body, error = _parse_body(request)
    if error:
        return error
    member = StaffMember.objects.filter(
        school=school, pk=body.get("staff_id")
    ).first()
    if member is None:
        return _bad("Pick a staff member.")
    title = str(body.get("title", "")).strip()
    if not title:
        return _bad("Task title is required.")
    task = OnboardingChecklist.objects.create(
        school=school,
        staff=member,
        title=title[:200],
        due_date=_parse_date(body.get("due_date")),
    )
    AuditLog.record(
        school, _actor(request), "onboarding task added",
        f"{task.title} — {member.full_name}",
    )
    return JsonResponse({"task": task.as_dict()}, status=201)


# ---------- payroll input (feeds Accountant payroll) ----------


@login_required
@hr_required
def payroll_input(request):
    """The payroll INPUT cockpit: attendance/leave roll-ups per staff for
    a period, plus the one-click feed into the accountant's draft run."""
    school = _school_of(request)
    period = request.GET.get("period") or services.current_period()
    rows = [
        r.as_dict()
        for r in PayrollInput.objects.filter(school=school, period=period)
        .select_related("staff")
    ]
    overview = metrics.payroll_input_overview(school, period)
    periods = (
        PayrollInput.objects.filter(school=school)
        .values_list("period", flat=True)
        .distinct()
    )
    from Accountant.models import PayrollPeriod

    run = PayrollPeriod.objects.filter(
        school=school, period=period
    ).first()
    return render(
        request,
        "HR/payroll_input.html",
        {
            "school": school,
            "period": period,
            "periods": sorted(set(periods) | {services.current_period()}),
            "rows": rows,
            "overview": overview,
            "run_status": run.status if run else None,
            "can_edit": can_mutate(request.user),
        },
    )


@login_required
@hr_required
@hr_write_required
@require_POST
def input_generate(request):
    """(Re)build the period's PayrollInput rows from attendance + approved
    leave (HR-entered bonus/advance survive the refresh)."""
    school = _school_of(request)
    body, error = _parse_body(request)
    if error:
        return error
    result = services.generate_inputs(
        school, str(body.get("period") or "").strip(), _actor(request)
    )
    AuditLog.record(
        school, _actor(request), "payroll input generated", result["period"],
        note=f"{result['created']} new, {result['updated']} refreshed",
    )
    return JsonResponse({"ok": True, **result})


@login_required
@hr_required
@hr_write_required
@require_POST
def input_update(request, input_id):
    """Adjust one row: bonus, advance, note (attendance numbers come from
    the grid — use Generate to refresh them)."""
    school = _school_of(request)
    row = PayrollInput.objects.filter(
        school=school, pk=input_id
    ).select_related("staff").first()
    if row is None:
        return JsonResponse({"error": "Payroll input not found."}, status=404)
    body, error = _parse_body(request)
    if error:
        return error
    bonus = _parse_amount(body.get("bonus"))
    advance = _parse_amount(body.get("advance"))
    if bonus is not None:
        row.bonus = bonus
    if advance is not None:
        row.advance = advance
    if "note" in body:
        row.note = str(body.get("note", "")).strip()[:300]
    row.save()
    AuditLog.record(
        school, _actor(request), "payroll input adjusted",
        f"{row.staff.full_name} — {row.period}",
        note=f"bonus Rs {row.bonus}, advance Rs {row.advance}",
    )
    return JsonResponse({"row": row.as_dict()})


@login_required
@hr_required
@hr_write_required
@require_POST
def input_feed(request):
    """THE bridge: push the period's inputs into the accountant's payroll
    run (auto-created as a DRAFT when missing; approved/paid runs refuse
    the feed — finance owns approval and payout)."""
    school = _school_of(request)
    body, error = _parse_body(request)
    if error:
        return error
    period = str(body.get("period") or "").strip() or services.current_period()
    try:
        result = services.feed_to_payroll(school, period, _actor(request))
    except services.PayrollRunLocked as exc:
        return _bad(str(exc))
    return JsonResponse({"ok": True, **result})


# ---------- performance appraisals ----------


@login_required
@hr_required
def appraisals(request):
    """Performance appraisals: drafts being written + finalized history."""
    school = _school_of(request)
    rows = [
        a.as_dict()
        for a in Appraisal.objects.filter(school=school)
        .select_related("staff")[:150]
    ]
    return render(
        request,
        "HR/appraisals.html",
        {
            "school": school,
            "appraisals": rows,
            "summary": metrics.appraisal_summary(school),
            "staff": [
                {"id": m.pk, "name": m.full_name}
                for m in StaffMember.objects.filter(school=school, is_active=True)
            ],
            "current_cycle": (
                f"{datetime.date.today().year - 1}-"
                f"{str(datetime.date.today().year)[2:]}"
            ),
            "can_edit": can_mutate(request.user),
        },
    )


@login_required
@hr_required
@hr_write_required
@require_POST
def appraisal_create(request):
    """Open an appraisal for a staff member for a cycle."""
    school = _school_of(request)
    body, error = _parse_body(request)
    if error:
        return error
    member = StaffMember.objects.filter(
        school=school, pk=body.get("staff_id")
    ).first()
    if member is None:
        return _bad("Pick a staff member.")
    period = str(body.get("period") or "").strip() or (
        f"{datetime.date.today().year - 1}-"
        f"{str(datetime.date.today().year)[2:]}"
    )
    if Appraisal.objects.filter(school=school, staff=member, period=period).exists():
        return _bad(f"An appraisal for {member.full_name} ({period}) already exists.")
    appraisal = Appraisal.objects.create(
        school=school,
        staff=member,
        period=period[:30],
        reviewer=str(body.get("reviewer", "")).strip() or _actor(request),
        strengths=str(body.get("strengths", "")).strip(),
        improvements=str(body.get("improvements", "")).strip(),
    )
    AuditLog.record(
        school, _actor(request), "appraisal opened",
        f"{member.full_name} — {period}",
    )
    return JsonResponse({"appraisal": appraisal.as_dict()}, status=201)


CRITERIA = ("teaching", "discipline", "teamwork", "punctuality", "growth")


@login_required
@hr_required
@hr_write_required
@require_POST
def appraisal_update(request, appraisal_id):
    """Edit a DRAFT appraisal: per-criterion 1-5 scores, rating,
    strengths/improvements. Finalized appraisals are frozen."""
    school = _school_of(request)
    appraisal = Appraisal.objects.filter(
        school=school, pk=appraisal_id
    ).select_related("staff").first()
    if appraisal is None:
        return JsonResponse({"error": "Appraisal not found."}, status=404)
    if appraisal.status == Appraisal.Status.FINALIZED:
        return _bad("Finalized appraisals are frozen.")
    body, error = _parse_body(request)
    if error:
        return error
    scores = {}
    for criterion in CRITERIA:
        value = body.get(f"score_{criterion}")
        if value in (None, ""):
            continue
        try:
            score = int(value)
        except (TypeError, ValueError):
            return _bad(f"Score for {criterion} must be 1-5.")
        if not 1 <= score <= 5:
            return _bad(f"Score for {criterion} must be 1-5.")
        scores[criterion] = score
    if scores:
        appraisal.scores = scores
        appraisal.rating = round(sum(scores.values()) / len(scores), 1)
    appraisal.reviewer = str(
        body.get("reviewer", appraisal.reviewer)
    ).strip() or appraisal.reviewer
    appraisal.strengths = str(body.get("strengths", appraisal.strengths)).strip()
    appraisal.improvements = str(
        body.get("improvements", appraisal.improvements)
    ).strip()
    appraisal.save()
    AuditLog.record(
        school, _actor(request), "appraisal updated",
        f"{appraisal.staff.full_name} — {appraisal.period}",
        note=f"rating {appraisal.rating}",
    )
    return JsonResponse({"appraisal": appraisal.as_dict()})


@login_required
@hr_required
@hr_write_required
@require_POST
def appraisal_finalize(request, appraisal_id):
    """Finalize (freeze) an appraisal — the recorded outcome of the cycle."""
    school = _school_of(request)
    appraisal = Appraisal.objects.filter(
        school=school, pk=appraisal_id
    ).select_related("staff").first()
    if appraisal is None:
        return JsonResponse({"error": "Appraisal not found."}, status=404)
    if appraisal.status == Appraisal.Status.FINALIZED:
        return _bad("Already finalized.")
    appraisal.status = Appraisal.Status.FINALIZED
    appraisal.finalized_by = _actor(request)
    appraisal.finalized_at = timezone.now()
    appraisal.save()
    AuditLog.record(
        school, _actor(request), "appraisal finalized",
        f"{appraisal.staff.full_name} — {appraisal.period}",
        note=f"rating {appraisal.rating}",
    )
    return JsonResponse({"appraisal": appraisal.as_dict()})


# ---------- staff documents & expiry alerts ----------


@login_required
@hr_required
def documents(request):
    """Staff document registry with expiry watch (expired first, then
    soonest-to-expire; 60-day warning window)."""
    school = _school_of(request)
    docs = [
        d.as_dict()
        for d in StaffDocument.objects.filter(school=school)
        .select_related("staff")
    ]
    rank = {"expired": 0, "expiring": 1, "none": 2, "ok": 3}
    docs.sort(key=lambda d: (rank.get(d["expiry_status"], 4),
                             d["expiry_date"] or "9999-12-31"))
    return render(
        request,
        "HR/documents.html",
        {
            "school": school,
            "documents": docs,
            "expired": sum(1 for d in docs if d["expiry_status"] == "expired"),
            "expiring": sum(1 for d in docs if d["expiry_status"] == "expiring"),
            "staff": [
                {"id": m.pk, "name": m.full_name}
                for m in StaffMember.objects.filter(school=school, is_active=True)
            ],
            "can_edit": can_mutate(request.user),
        },
    )


@login_required
@hr_required
@hr_write_required
@require_POST
def document_add(request):
    """Register a staff document (certification, CNIC, contract copy...)."""
    school = _school_of(request)
    body, error = _parse_body(request)
    if error:
        return error
    member = StaffMember.objects.filter(
        school=school, pk=body.get("staff_id")
    ).first()
    if member is None:
        return _bad("Pick a staff member.")
    title = str(body.get("title", "")).strip()
    if not title:
        return _bad("Document title is required.")
    doc = StaffDocument.objects.create(
        school=school,
        staff=member,
        kind=str(body.get("kind") or StaffDocument.Kind.CERTIFICATION),
        title=title[:200],
        number=str(body.get("number", "")).strip(),
        issued_on=_parse_date(body.get("issued_on")),
        expiry_date=_parse_date(body.get("expiry_date")),
        file_url=str(body.get("file_url", "")).strip()[:300],
    )
    AuditLog.record(
        school, _actor(request), "document added",
        f"{doc.title} — {member.full_name}",
        note=doc.expiry_status if doc.expiry_date else "no expiry",
    )
    return JsonResponse({"document": doc.as_dict()}, status=201)


# ---------- training / professional development ----------


@login_required
@hr_required
def training(request):
    """Training programs + staff enrollments (professional development)."""
    school = _school_of(request)
    return render(
        request,
        "HR/training.html",
        {
            "school": school,
            "programs": [p.as_dict() for p in school.training_programs.all()],
            "enrollments": [
                e.as_dict()
                for e in TrainingEnrollment.objects.filter(school=school)
                .select_related("program", "staff")[:150]
            ],
            "summary": metrics.training_summary(school),
            "staff": [
                {"id": m.pk, "name": m.full_name}
                for m in StaffMember.objects.filter(school=school, is_active=True)
            ],
            "can_edit": can_mutate(request.user),
        },
    )


@login_required
@hr_required
@hr_write_required
@require_POST
def program_create(request):
    """Add a training / development program."""
    school = _school_of(request)
    body, error = _parse_body(request)
    if error:
        return error
    title = str(body.get("title", "")).strip()
    if not title:
        return _bad("Program title is required.")
    start = _parse_date(body.get("start_date"))
    if start is None:
        return _bad("Pick a start date.")
    end = _parse_date(body.get("end_date"))
    if end and end < start:
        return _bad("End date can't be before the start date.")
    cost = _parse_amount(body.get("cost_per_head"))
    program = TrainingProgram.objects.create(
        school=school,
        title=title[:200],
        kind=str(body.get("kind") or TrainingProgram.Kind.WORKSHOP),
        provider=str(body.get("provider", "")).strip(),
        start_date=start,
        end_date=end,
        cost_per_head=cost or 0,
        status=str(body.get("status") or TrainingProgram.Status.PLANNED),
    )
    AuditLog.record(school, _actor(request), "program added", program.title)
    return JsonResponse({"program": program.as_dict()}, status=201)


@login_required
@hr_required
@hr_write_required
@require_POST
def program_status(request, program_id):
    """Move a program along: planned -> ongoing -> completed/cancelled."""
    school = _school_of(request)
    program = school.training_programs.filter(pk=program_id).first()
    if program is None:
        return JsonResponse({"error": "Program not found."}, status=404)
    body, error = _parse_body(request)
    if error:
        return error
    status = str(body.get("status") or "")
    if status not in TrainingProgram.Status.values:
        return _bad("Invalid status.")
    program.status = status
    program.save(update_fields=["status"])
    AuditLog.record(
        school, _actor(request), f"program {status}", program.title
    )
    return JsonResponse({"program": program.as_dict()})


@login_required
@hr_required
@hr_write_required
@require_POST
def enrollment_create(request):
    """Enroll a staff member in a program (unique per program+staff)."""
    school = _school_of(request)
    body, error = _parse_body(request)
    if error:
        return error
    program = school.training_programs.filter(pk=body.get("program_id")).first()
    if program is None:
        return _bad("Pick a training program.")
    member = StaffMember.objects.filter(
        school=school, pk=body.get("staff_id")
    ).first()
    if member is None:
        return _bad("Pick a staff member.")
    enrollment, created = TrainingEnrollment.objects.get_or_create(
        school=school, program=program, staff=member
    )
    if not created:
        return _bad(
            f"{member.full_name} is already enrolled in {program.title}."
        )
    if program.status == TrainingProgram.Status.PLANNED:
        program.status = TrainingProgram.Status.ONGOING
        program.save(update_fields=["status"])
    AuditLog.record(
        school, _actor(request), "staff enrolled",
        f"{member.full_name} — {program.title}",
    )
    return JsonResponse({"enrollment": enrollment.as_dict()}, status=201)


@login_required
@hr_required
@hr_write_required
@require_POST
def enrollment_update(request, enrollment_id):
    """Mark an enrollment completed (certificate ref optional) or dropped."""
    school = _school_of(request)
    enrollment = TrainingEnrollment.objects.filter(
        school=school, pk=enrollment_id
    ).select_related("program", "staff").first()
    if enrollment is None:
        return JsonResponse({"error": "Enrollment not found."}, status=404)
    body, error = _parse_body(request)
    if error:
        return error
    status = str(body.get("status") or "")
    if status not in TrainingEnrollment.Status.values:
        return _bad("Invalid status.")
    enrollment.status = status
    if status == TrainingEnrollment.Status.COMPLETED:
        enrollment.completed_on = (
            _parse_date(body.get("completed_on")) or datetime.date.today()
        )
        enrollment.certificate_ref = str(
            body.get("certificate_ref", "")
        ).strip()[:100]
    enrollment.save()
    AuditLog.record(
        school, _actor(request), f"training {status}",
        f"{enrollment.staff.full_name} — {enrollment.program.title}",
        note=enrollment.certificate_ref,
    )
    return JsonResponse({"enrollment": enrollment.as_dict()})


















