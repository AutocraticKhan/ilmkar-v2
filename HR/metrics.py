"""Snapshot + alert metrics for the HR dashboard.

Everything the dashboard and sidebar badges need is computed here so
the pages never disagree. Same philosophy as ``Accountant.metrics``:
cheap queries, one source of truth per number.
"""
import datetime

from django.db.models import Count, Q

from School_Admin.models import LeaveRequest, StaffMember

from .models import (
    Appraisal,
    AttendanceRecord,
    JobApplication,
    OnboardingChecklist,
    PayrollInput,
    StaffContract,
    StaffDocument,
    TrainingEnrollment,
)


def doc_alerts(school, today=None):
    """Staff documents expired / expiring within 60 days (the alert
    feed on the dashboard + sidebar badge), oldest expiry first."""
    today = today or datetime.date.today()
    horizon = today + datetime.timedelta(days=60)
    return [
        d.as_dict()
        for d in StaffDocument.objects.filter(
            school=school, expiry_date__isnull=False, expiry_date__lte=horizon
        ).select_related("staff")
    ]


def expired_contracts(school, today=None):
    """Active-flagged contracts whose end date already passed."""
    today = today or datetime.date.today()
    return [
        c.as_dict()
        for c in StaffContract.objects.filter(
            school=school,
            status=StaffContract.Status.ACTIVE,
            end_date__lt=today,
        ).select_related("staff")
    ]


def pending_leaves(school):
    """Leave requests awaiting a decision (HR or the principal)."""
    return LeaveRequest.objects.filter(
        school=school, status=LeaveRequest.Status.PENDING
    ).select_related("staff")


def attendance_month(school, year, month):
    """Attendance summary per staff for one month:
    [{staff, present, absent, late, half, leave, records:{iso_date: status}}]."""
    rows = []
    for member in StaffMember.objects.filter(school=school, is_active=True):
        records = AttendanceRecord.objects.filter(
            school=school, staff=member,
            date__year=year, date__month=month,
        )
        per_day = {r.date.isoformat(): r.status for r in records}
        rows.append({
            "staff_id": member.pk,
            "staff_name": member.full_name,
            "designation": member.designation or "—",
            "present": sum(
                1 for r in records if r.status == AttendanceRecord.Status.PRESENT
            ),
            "absent": sum(
                1 for r in records if r.status == AttendanceRecord.Status.ABSENT
            ),
            "late": sum(
                1 for r in records if r.status == AttendanceRecord.Status.LATE
            ),
            "half": sum(
                1 for r in records if r.status == AttendanceRecord.Status.HALF_DAY
            ),
            "leave": sum(
                1 for r in records if r.status == AttendanceRecord.Status.LEAVE
            ),
            "unpaid_absent": sum(
                1 for r in records
                if r.status == AttendanceRecord.Status.ABSENT and r.unpaid
            ),
            "records": per_day,
            "marked": len(per_day),
        })
    return rows


def onboarding_progress(school):
    """Per-staff onboarding progress for staff with open tasks:
    [{staff, open, done, total, pct}] ordered by lowest completion.
    Finished checklists drop off the work queue."""
    counts = (
        OnboardingChecklist.objects.filter(school=school)
        .values("staff_id", "staff__full_name")
        .annotate(
            total=Count("pk"),
            done=Count("pk", filter=Q(is_done=True)),
        )
    )
    rows = []
    for row in counts:
        if row["done"] == row["total"]:
            continue
        pct = int(round(100 * row["done"] / row["total"])) if row["total"] else 0
        rows.append({
            "staff_id": row["staff_id"],
            "staff_name": row["staff__full_name"],
            "open": row["total"] - row["done"],
            "done": row["done"],
            "total": row["total"],
            "pct": pct,
        })
    rows.sort(key=lambda r: (r["pct"], r["staff_name"]))
    return rows


def recruitment_pipeline(school):
    """Applicant counts per stage + open postings + totals."""
    stages = (
        JobApplication.objects.filter(school=school)
        .values("stage")
        .annotate(count=Count("pk"))
    )
    stage_counts = {row["stage"]: row["count"] for row in stages}
    return {
        "stage_counts": stage_counts,
        "total_applications": sum(stage_counts.values()),
        "open_postings": sum(
            1 for p in school.hr_job_postings.all() if p.status == "open"
        ),
    }


def appraisal_summary(school):
    """Average final rating + drafts awaiting finalization."""
    final = [
        a for a in Appraisal.objects.filter(
            school=school, status=Appraisal.Status.FINALIZED
        ) if a.rating
    ]
    avg = (
        round(sum(float(a.rating) for a in final) / len(final), 1)
        if final else None
    )
    return {
        "finalized": len(final),
        "avg_rating": avg,
        "drafts": Appraisal.objects.filter(
            school=school, status=Appraisal.Status.DRAFT
        ).count(),
    }


def training_summary(school):
    """Enrollments by status + non-cancelled programs this year."""
    year = datetime.date.today().year
    enrollments = TrainingEnrollment.objects.filter(school=school)
    return {
        "enrolled": enrollments.filter(
            status=TrainingEnrollment.Status.ENROLLED
        ).count(),
        "completed": enrollments.filter(
            status=TrainingEnrollment.Status.COMPLETED
        ).count(),
        "programs_this_year": school.training_programs.filter(
            start_date__year=year
        ).exclude(status="cancelled").count(),
    }


def payroll_input_overview(school, period):
    """Feed state for one payroll period: rows pending vs fed."""
    rows = PayrollInput.objects.filter(school=school, period=period)
    return {
        "period": period,
        "total": rows.count(),
        "pending": rows.filter(fed_to_payroll=False).count(),
        "fed": rows.filter(fed_to_payroll=True).count(),
    }

