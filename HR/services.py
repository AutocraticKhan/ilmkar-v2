"""Cross-app services for the HR dashboard.

Two responsibilities:
- the ONBOARDING template (start a checklist for a new hire);
- the PAYROLL BRIDGE: roll attendance + approved leave up into
  ``PayrollInput`` rows and feed them into the accountant's
  ``Accountant.PayrollPeriod`` (DRAFT runs only — approval/payout stays
  with finance). Period labels use the platform-wide ``"%B %Y"``
  format so HR rows and payroll rows always match.

Per-day deduction logic: contract salary / working days of the month x
unpaid-absent days. Paid leave and approved paid absence never deduct.
Bonuses are added as allowances; salary advances are added to
deductions. Everything is re-derivable from HR data, so re-running
"generate" is safe (rows upsert, never duplicate).
"""
import calendar
import datetime

from django.utils import timezone

from School_Admin.models import LeaveRequest, StaffMember

from .models import (
    AttendanceRecord,
    OnboardingChecklist,
    PayrollInput,
    StaffContract,
)

# Default onboarding template applied to every new hire.
DEFAULT_TASKS = (
    "Collect CNIC copy & attested degrees",
    "Signed contract on file",
    "Create staff ID card + platform account",
    "Add to payroll (salary & bank details)",
    "Assign timetable / duties",
    "Staff handbook walkthrough",
)


def current_period(today=None):
    """Platform-wide period label, e.g. "September 2026"."""
    today = today or datetime.date.today()
    return today.strftime("%B %Y")


def start_onboarding(school, staff, due_date=None):
    """Seed the default onboarding checklist for a new hire (idempotent:
    tasks that already exist by title are kept, missing ones added).
    Returns the number of tasks created."""
    existing = set(staff.onboarding_tasks.values_list("title", flat=True))
    created = 0
    for title in DEFAULT_TASKS:
        if title in existing:
            continue
        OnboardingChecklist.objects.create(
            school=school, staff=staff, title=title, due_date=due_date
        )
        created += 1
    return created


def _month_bounds(period_label):
    """(first_day, last_day, working_days) for a "%B %Y" period label."""
    first = datetime.datetime.strptime(period_label, "%B %Y").date()
    last = datetime.date(
        first.year, first.month, calendar.monthrange(first.year, first.month)[1]
    )
    working_days = sum(
        1
        for offset in range((last - first).days + 1)
        if (first + datetime.timedelta(days=offset)).weekday() < 5
    ) or (last - first).days + 1
    return first, last, working_days


def generate_inputs(school, period, actor=""):
    """Build/refresh one ``PayrollInput`` per active staff member for the
    period from attendance records + approved leave. Upsert semantics:
    existing rows are overwritten with the fresh roll-up (fed rows are
    NOT regenerated — re-feeding is the explicit payroll action)."""
    label = period or current_period()
    first, last, working_days = _month_bounds(label)

    staff_qs = StaffMember.objects.filter(school=school, is_active=True)
    attendance = list(
        AttendanceRecord.objects.filter(
            school=school, date__gte=first, date__lte=last
        )
    )
    by_staff = {}
    for record in attendance:
        by_staff.setdefault(record.staff_id, []).append(record)

    # Approved leaves overlapping the month -> paid leave day count.
    leave_days = {}
    for leave in LeaveRequest.objects.filter(
        school=school, status=LeaveRequest.Status.APPROVED,
        from_date__lte=last, to_date__gte=first,
    ):
        overlap_start = max(leave.from_date, first)
        overlap_end = min(leave.to_date, last)
        days = (overlap_end - overlap_start).days + 1
        leave_days[leave.staff_id] = leave_days.get(leave.staff_id, 0) + days

    created, updated = 0, 0
    for member in staff_qs:
        records = by_staff.get(member.pk, [])
        present = sum(
            1 for r in records if r.status == AttendanceRecord.Status.PRESENT
        )
        late = sum(1 for r in records if r.status == AttendanceRecord.Status.LATE)
        absent_unpaid = sum(
            1
            for r in records
            if r.status == AttendanceRecord.Status.ABSENT and r.unpaid
        )
        half_days = sum(
            1 for r in records if r.status == AttendanceRecord.Status.HALF_DAY
        )

        row = PayrollInput.objects.filter(
            school=school, staff=member, period=label
        ).first()
        if row is None:
            row = PayrollInput(school=school, staff=member, period=label)
            created += 1
        else:
            updated += 1
        row.present_days = present + 0.5 * half_days
        row.absent_unpaid_days = absent_unpaid + 0.5 * half_days
        row.paid_leave_days = leave_days.get(member.pk, 0)
        row.late_marks = late
        # Bonus/advance/note stay HR-entered — a refresh never wipes them.
        row.save()
    return {"created": created, "updated": updated, "period": label}


def _salary_base(school, staff):
    """Default (basic, allowances) for the payroll item: latest active
    contract's monthly salary, else the latest payslip, else zeros."""
    from Teachers.models import Payslip

    contract = StaffContract.objects.filter(
        school=school, staff=staff, status=StaffContract.Status.ACTIVE
    ).first() or StaffContract.objects.filter(school=school, staff=staff).first()
    if contract is not None:
        return float(contract.monthly_salary), 0
    payslip = Payslip.objects.filter(school=school, staff=staff).first()
    if payslip is not None:
        return float(payslip.basic), float(payslip.allowances)
    return 0, 0


class PayrollRunLocked(Exception):
    """Raised when the target payroll run is not in draft."""


def feed_to_payroll(school, period_label, actor):
    """Feed the period's ``PayrollInput`` rows into the accountant's
    payroll run.

    - auto-creates the ``PayrollPeriod`` (DRAFT) when missing;
    - upserts one ``PayrollItem`` per HR input row: basic from the
      contract/payslip, deductions = unpaid days x per-day rate +
      salary advance, allowances = HR bonus;
    - draft runs ONLY (approved/paid runs are finance's frozen truth);
    - appends to BOTH the HR audit log and the finance audit log.
    Returns a dict summary for the JSON response.
    """
    from Accountant.models import AuditLog as FinanceAudit
    from Accountant.models import PayrollItem, PayrollPeriod

    from .models import AuditLog

    period_obj = PayrollPeriod.objects.filter(
        school=school, period=period_label
    ).first()
    if period_obj is None:
        period_obj = PayrollPeriod.objects.create(
            school=school, period=period_label, created_by=actor
        )
        FinanceAudit.record(
            school, actor, "payroll opened", period_label,
            note=f"auto-created by HR feed ({actor})",
        )
    if period_obj.status != PayrollPeriod.Status.DRAFT:
        raise PayrollRunLocked(
            f"Payroll run '{period_label}' is "
            f"{period_obj.get_status_display()} — only draft runs can "
            "be fed from HR."
        )

    first, last, working_days = _month_bounds(period_label)
    inputs = list(
        PayrollInput.objects.filter(school=school, period=period_label)
        .select_related("staff")
    )
    fed = 0
    for row in inputs:
        basic, allowances = _salary_base(school, row.staff)
        per_day = (basic / working_days) if working_days and basic else 0
        absence_deduction = round(per_day * float(row.absent_unpaid_days), 2)
        deductions = absence_deduction + float(row.advance)
        PayrollItem.objects.update_or_create(
            period=period_obj,
            staff=row.staff,
            defaults={
                "school": school,
                "basic": basic,
                "allowances": allowances + float(row.bonus),
                "deductions": deductions,
            },
        )
        row.fed_to_payroll = True
        row.fed_by = actor
        row.fed_at = timezone.now()
        row.save()
        fed += 1

    AuditLog.record(
        school, actor, "payroll fed", period_label,
        note=f"{fed} staff fed to draft payroll run",
    )
    FinanceAudit.record(
        school, actor, "payroll fed from HR", period_label,
        note=f"{fed} pay line(s) from HR attendance/leave",
    )
    return {
        "fed": fed,
        "period": period_label,
        "payroll_period_id": period_obj.pk,
        "status": period_obj.status,
    }

