"""Per-branch metric computation for the chain dashboard.

Every metric reads the REAL school-side models in ``School_Admin`` — the
single source of truth the principal, teachers, accountant and portals all
write to:

- ``AttendanceSnapshot``  (kept live by ``Teachers.metrics.sync_attendance_snapshot``
  every time a teacher saves the register);
- ``ExamRecord``          (``average_pct`` recomputed on every marks-entry save);
- ``StudentFeeInvoice`` + ``FeePayment`` (invoices the principal issues and
  payments recorded by the accountant / parent / student portals);
- ``Student`` / ``StaffMember`` / ``ClassSection`` (enrolment, staffing, seats).

The returned dict shapes are the contract the dashboard UI is built on, so
keep the keys stable.
"""
import datetime

from django.db.models import Count, Sum

from School_Admin.models import (
    AttendanceSnapshot,
    ClassSection,
    ExamRecord,
    FeePayment,
    StaffMember,
    Student,
    StudentFeeInvoice,
)


def current_period(today=None):
    """Period label used across the dashboard, e.g. "September 2026"."""
    today = today or datetime.date.today()
    return today.strftime("%B %Y")


def attendance_pct(school, days=30, today=None):
    """Average attendance % across the last ``days`` days of snapshots.

    Per-section snapshots (the kind a teacher's register save upserts) are
    preferred; school-wide rows (no section set) are only used as a
    fallback, so a school with both shapes is never double-counted."""
    today = today or datetime.date.today()
    since = today - datetime.timedelta(days=days)
    rows = AttendanceSnapshot.objects.filter(
        school=school, class_section__isnull=False,
        date__gte=since, date__lte=today,
    )
    if not rows.exists():
        rows = AttendanceSnapshot.objects.filter(
            school=school, date__gte=since, date__lte=today,
        )
    agg = rows.aggregate(present=Sum("present"), absent=Sum("absent"))
    total = (agg["present"] or 0) + (agg["absent"] or 0)
    return round((agg["present"] or 0) / total * 100, 1) if total else None


def exam_average(school):
    """Most recent recorded exam average for the branch — the latest
    ``ExamRecord`` whose ``average_pct`` a teacher's marks entry filled in."""
    latest = (
        ExamRecord.objects.filter(school=school, average_pct__isnull=False)
        .order_by("-exam_date", "-pk")
        .first()
    )
    return float(latest.average_pct) if latest else None


def fee_metrics(school, today=None):
    """Collection stats for the current billing period plus overdue totals.

    ``invoiced``  = ``StudentFeeInvoice`` amounts for the current period
                    (issued by the principal, incl. the admission auto-invoice);
    ``collected`` = ``FeePayment`` amounts recorded against those invoices
                    (accountant receipts + parent/student online payments);
    ``overdue``   = UNPAID/PARTIAL invoices past their due date, any period
                    (the same defaulter definition the accountant uses).

    Returns a dict with: invoiced, collected, outstanding (unpaid in the
    current period), overdue_amount (any period, due date passed),
    overdue_count, collection_pct (None when nothing was invoiced yet).
    """
    today = today or datetime.date.today()
    period = current_period(today)

    period_agg = StudentFeeInvoice.objects.filter(
        school=school, period=period
    ).aggregate(invoiced=Sum("amount"))
    collected_agg = FeePayment.objects.filter(
        invoice__school=school, invoice__period=period
    ).aggregate(collected=Sum("amount"))
    overdue_agg = StudentFeeInvoice.objects.filter(
        school=school,
        status__in=[
            StudentFeeInvoice.Status.UNPAID, StudentFeeInvoice.Status.PARTIAL
        ],
        due_date__lt=today,
    ).aggregate(amount=Sum("amount"), count=Count("pk"))

    invoiced = float(period_agg["invoiced"] or 0)
    collected = float(collected_agg["collected"] or 0)
    return {
        "period": period,
        "invoiced": invoiced,
        "collected": collected,
        "outstanding": invoiced - collected,
        "overdue_amount": float(overdue_agg["amount"] or 0),
        "overdue_count": overdue_agg["count"] or 0,
        "collection_pct": round(collected / invoiced * 100, 1) if invoiced else None,
    }


def free_seats(school):
    """Total unfilled seats across the branch's class sections — each
    section's capacity minus the students actually enrolled in it."""
    enrolled = {
        row["class_section_id"]: row["n"]
        for row in (
            Student.objects.filter(
                school=school, status=Student.Status.ACTIVE,
                class_section__isnull=False,
            )
            .values("class_section_id")
            .annotate(n=Count("pk"))
        )
    }
    total = 0
    for section in ClassSection.objects.filter(school=school):
        total += max(0, section.capacity - enrolled.get(section.pk, 0))
    return total


def traffic_light(value, green_min, amber_min):
    """Map a metric value to green / yellow / red (None -> no data)."""
    if value is None:
        return "none"
    if value >= green_min:
        return "green"
    if value >= amber_min:
        return "yellow"
    return "red"


def scorecard(school, today=None):
    """Traffic-light per area: fees (collection %), attendance, exam results.

    Thresholds (kept in one place so they are easy to tune later):
      fees        green >= 85% collection, yellow >= 65%
      attendance  green >= 92%,             yellow >= 85%
      exams       green >= 70% average,     yellow >= 55%
    """
    fees = fee_metrics(school, today)
    lights = {
        "fees": traffic_light(fees["collection_pct"], 85, 65),
        "attendance": traffic_light(attendance_pct(school, today=today), 92, 85),
        "exams": traffic_light(exam_average(school), 70, 55),
    }
    overall = "green"
    for state in lights.values():
        if state == "red":
            overall = "red"
        elif state == "yellow" and overall != "red":
            overall = "yellow"
        elif state == "none" and overall == "green":
            overall = "none"
    return {"lights": lights, "overall": overall}


def branch_metrics(school, today=None):
    """Everything the side-by-side comparison table needs for one branch.

    Students/staff come from the school-side source of truth (the mirror
    rows in ``school_owner`` are only used by the transfers page)."""
    today = today or datetime.date.today()
    fees = fee_metrics(school, today)
    return {
        "id": school.pk,
        "name": school.name,
        "city": school.city,
        "students": Student.objects.filter(
            school=school, status=Student.Status.ACTIVE
        ).count(),
        "staff": StaffMember.objects.filter(school=school, is_active=True).count(),
        "attendance_pct": attendance_pct(school, today=today),
        "exam_avg": exam_average(school),
        "free_seats": free_seats(school),
        **fees,
        "scorecard": scorecard(school, today),
    }


def consolidated(branches):
    """Roll per-branch metric dicts up into one group-level dict."""
    total_invoiced = sum(b["invoiced"] for b in branches)
    total_collected = sum(b["collected"] for b in branches)
    att_values = [b["attendance_pct"] for b in branches if b["attendance_pct"] is not None]
    return {
        "period": branches[0]["period"] if branches else current_period(),
        "branches": len(branches),
        "students": sum(b["students"] for b in branches),
        "staff": sum(b["staff"] for b in branches),
        "free_seats": sum(b["free_seats"] for b in branches),
        "invoiced": total_invoiced,
        "collected": total_collected,
        "outstanding": total_invoiced - total_collected,
        "overdue_amount": sum(b["overdue_amount"] for b in branches),
        "collection_pct": (
            round(total_collected / total_invoiced * 100, 1) if total_invoiced else None
        ),
        "attendance_pct": (
            round(sum(att_values) / len(att_values), 1) if att_values else None
        ),
    }


def monthly_statement(schools, limit=6, today=None):
    """Consolidated invoiced vs collected per billing period (newest first),
    read from the school-side ``StudentFeeInvoice`` / ``FeePayment`` rows."""
    today = today or datetime.date.today()
    # NB: set() instead of .distinct() — the model's Meta.ordering can make
    # DISTINCT return duplicate rows on SQLite.
    periods = set(
        StudentFeeInvoice.objects.filter(school__in=schools)
        .values_list("period", flat=True)
    )

    def _key(row):
        try:
            return datetime.datetime.strptime(row, "%B %Y")
        except ValueError:
            return datetime.datetime.min

    rows = []
    for period in sorted(periods, key=_key, reverse=True):
        invoiced = float(
            StudentFeeInvoice.objects.filter(
                school__in=schools, period=period
            ).aggregate(invoiced=Sum("amount"))["invoiced"] or 0
        )
        collected = float(
            FeePayment.objects.filter(
                invoice__school__in=schools, invoice__period=period
            ).aggregate(collected=Sum("amount"))["collected"] or 0
        )
        rows.append({
            "period": period,
            "invoiced": invoiced,
            "collected": collected,
            "collection_pct": (
                round(collected / invoiced * 100, 1) if invoiced else None
            ),
            "current": period == current_period(today),
        })

    return rows[:limit]

