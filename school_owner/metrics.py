"""Per-branch metric computation for the chain dashboard.

TODO(placeholder): every function here reads from the placeholder models in
``school_owner.models`` (Classroom/Student/StaffMember/FeeInvoice/
AttendanceSnapshot/ExamSummary). When the real school-side modules land
(Student Information, Fees, Attendance, Exams), swap the querysets inside
these helpers — the shapes they return are the contract the dashboard UI
is built on, so keep the returned dict keys stable.
"""
import datetime

from django.db.models import Count, Q, Sum

from .models import (
    AttendanceSnapshot,
    Classroom,
    ExamSummary,
    FeeInvoice,
    Student,
    StaffMember,
)


def current_period(today=None):
    """Period label used across the dashboard, e.g. "September 2026"."""
    today = today or datetime.date.today()
    return today.strftime("%B %Y")


def attendance_pct(school, days=30, today=None):
    """Average attendance % across the last ``days`` days of snapshots."""
    today = today or datetime.date.today()
    qs = AttendanceSnapshot.objects.filter(
        school=school, date__gte=today - datetime.timedelta(days=days)
    ).aggregate(present=Sum("present"), absent=Sum("absent"))
    total = (qs["present"] or 0) + (qs["absent"] or 0)
    return round((qs["present"] or 0) / total * 100, 1) if total else None


def exam_average(school):
    """Most recent recorded exam average for the branch."""
    latest = ExamSummary.objects.filter(school=school).first()
    return float(latest.average_pct) if latest else None


def fee_metrics(school, today=None):
    """Collection stats for the current billing period plus overdue totals.

    Returns a dict with: invoiced, collected, outstanding (unpaid in the
    current period), overdue_amount (any period, due date passed),
    collection_pct (None when nothing was invoiced yet).
    """
    today = today or datetime.date.today()
    period = current_period(today)

    period_agg = FeeInvoice.objects.filter(school=school, period=period).aggregate(
        invoiced=Sum("amount"),
        collected=Sum("amount", filter=Q(status=FeeInvoice.Status.PAID)),
    )
    overdue_agg = FeeInvoice.objects.filter(
        school=school,
        status=FeeInvoice.Status.UNPAID,
        due_date__lt=today,
    ).aggregate(amount=Sum("amount"), count=Count("pk"))

    invoiced = float(period_agg["invoiced"] or 0)
    collected = float(period_agg["collected"] or 0)
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
    """Total unfilled seats across the branch's classrooms."""
    total = 0
    for room in Classroom.objects.filter(school=school):
        enrolled = Student.objects.filter(
            school=school, classroom=room, status=Student.Status.ACTIVE
        ).count()
        total += max(0, room.capacity - enrolled)
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
    """Everything the side-by-side comparison table needs for one branch."""
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
    """Consolidated invoiced vs collected per billing period (newest first)."""
    today = today or datetime.date.today()
    periods = (
        FeeInvoice.objects.filter(school__in=schools)
        .values_list("period", flat=True)
        .distinct()
    )
    rows = []
    for period in periods:
        agg = FeeInvoice.objects.filter(
            school__in=schools, period=period
        ).aggregate(
            invoiced=Sum("amount"),
            collected=Sum("amount", filter=Q(status=FeeInvoice.Status.PAID)),
        )
        invoiced = float(agg["invoiced"] or 0)
        collected = float(agg["collected"] or 0)
        rows.append({
            "period": period,
            "invoiced": invoiced,
            "collected": collected,
            "collection_pct": (
                round(collected / invoiced * 100, 1) if invoiced else None
            ),
            "current": period == current_period(today),
        })

    def _key(row):
        try:
            return datetime.datetime.strptime(row["period"], "%B %Y")
        except ValueError:
            return datetime.datetime.min

    rows.sort(key=_key, reverse=True)
    return rows[:limit]

