"""Snapshot + report metric computation for the school admin dashboard.

TODO(placeholder): every function reads from the placeholder models in
``School_Admin.models``. When the real school-side modules land (Student
Information, Fees, Attendance, Exams), swap the querysets inside these
helpers — the returned dict keys are the contract the dashboard UI (and,
soon, ``school_owner.metrics``) is built on, so keep them stable.
"""
import datetime

from django.db.models import Count, Q, Sum

from .models import (
    AdmissionApplication,
    AttendanceSnapshot,
    ClassSection,
    ExamRecord,
    FeePayment,
    StudentFeeInvoice,
)


def current_period(today=None):
    """Period label used across the dashboards, e.g. "September 2026"."""
    today = today or datetime.date.today()
    return today.strftime("%B %Y")


def attendance_pct(school, day=None, days=None, today=None):
    """School-wide attendance % for one day, or averaged over the last
    ``days`` days. Returns None when there is no data."""
    today = today or datetime.date.today()
    qs = AttendanceSnapshot.objects.filter(school=school)
    if day is not None:
        qs = qs.filter(date=day)
    elif days is not None:
        qs = qs.filter(date__gte=today - datetime.timedelta(days=days))
    agg = qs.aggregate(present=Sum("present"), absent=Sum("absent"))
    total = (agg["present"] or 0) + (agg["absent"] or 0)
    return round((agg["present"] or 0) / total * 100, 1) if total else None


def fee_kpis(school, today=None):
    """Fee collection KPIs for the snapshot home screen.

    Returns: collected_today, collected_month, invoiced_month,
    outstanding_month, overdue_amount, overdue_count, collection_pct
    (None when nothing was invoiced this month).
    """
    today = today or datetime.date.today()
    period = current_period(today)
    month_start = today.replace(day=1)

    collected_today = FeePayment.objects.filter(
        invoice__school=school, paid_on=today
    ).aggregate(total=Sum("amount"))["total"] or 0
    collected_month = FeePayment.objects.filter(
        invoice__school=school, paid_on__gte=month_start, paid_on__lte=today
    ).aggregate(total=Sum("amount"))["total"] or 0
    invoiced_month = StudentFeeInvoice.objects.filter(
        school=school, period=period
    ).aggregate(total=Sum("amount"))["total"] or 0
    overdue = StudentFeeInvoice.objects.filter(
        school=school,
        status__in=[StudentFeeInvoice.Status.UNPAID, StudentFeeInvoice.Status.PARTIAL],
        due_date__lt=today,
    ).aggregate(amount=Sum("amount"), count=Count("pk"))

    return {
        "period": period,
        "collected_today": float(collected_today),
        "collected_month": float(collected_month),
        "invoiced_month": float(invoiced_month),
        "outstanding_month": float(invoiced_month) - float(collected_month),
        "overdue_amount": float(overdue["amount"] or 0),
        "overdue_count": overdue["count"] or 0,
        "collection_pct": (
            round(float(collected_month) / float(invoiced_month) * 100, 1)
            if invoiced_month else None
        ),
    }


def pending_admissions(school):
    """Pending admission applications, newest first."""
    return AdmissionApplication.objects.filter(
        school=school, status=AdmissionApplication.Status.PENDING
    ).select_related("class_section")


def upcoming_exams(school, limit=5, today=None):
    """Next ``limit`` exams that have not been held yet (no average)."""
    today = today or datetime.date.today()
    return (
        ExamRecord.objects.filter(school=school, exam_date__gte=today)
        .order_by("exam_date")[:limit]
    )


def class_attendance_rows(school, days=30, class_section=None, today=None):
    """Attendance % per class section (or per day for one section).

    With no ``class_section``: one row per section averaged over the last
    ``days`` days. With one: one row per day for that section.
    """
    today = today or datetime.date.today()
    since = today - datetime.timedelta(days=days)
    if class_section is not None:
        qs = AttendanceSnapshot.objects.filter(
            school=school, class_section=class_section, date__gte=since
        ).order_by("-date")
        return [
            {
                "label": row.date.isoformat(),
                "present": row.present,
                "absent": row.absent,
                "pct": (
                    round(row.present / (row.present + row.absent) * 100, 1)
                    if (row.present + row.absent) else None
                ),
            }
            for row in qs
        ]
    rows = []
    for section in ClassSection.objects.filter(school=school):
        agg = AttendanceSnapshot.objects.filter(
            school=school, class_section=section, date__gte=since
        ).aggregate(present=Sum("present"), absent=Sum("absent"))
        total = (agg["present"] or 0) + (agg["absent"] or 0)
        rows.append({
            "label": section.label,
            "present": agg["present"] or 0,
            "absent": agg["absent"] or 0,
            "pct": round((agg["present"] or 0) / total * 100, 1) if total else None,
        })
    return rows


def exam_rows(school, class_section=None):
    """Academic report rows: most recent exams first, optional class filter."""
    qs = ExamRecord.objects.filter(school=school).select_related("class_section")
    if class_section is not None:
        qs = qs.filter(class_section=class_section)
    return list(qs[:50])


def monthly_financials(school, limit=6, today=None):
    """Invoiced vs collected per billing period, newest first.

    Same row shape as ``school_owner.metrics.monthly_statement`` so the
    owner dashboard can render school statements from this directly.
    """
    today = today or datetime.date.today()
    periods = (
        StudentFeeInvoice.objects.filter(school=school)
        .values_list("period", flat=True)
        .distinct()
    )
    rows = []
    for period in periods:
        invoiced = StudentFeeInvoice.objects.filter(
            school=school, period=period
        ).aggregate(total=Sum("amount"))["total"] or 0
        collected = FeePayment.objects.filter(
            invoice__school=school, invoice__period=period
        ).aggregate(total=Sum("amount"))["total"] or 0
        rows.append({
            "period": period,
            "invoiced": float(invoiced),
            "collected": float(collected),
            "outstanding": float(invoiced) - float(collected),
            "collection_pct": (
                round(float(collected) / float(invoiced) * 100, 1)
                if invoiced else None
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


def defaulters(school, today=None):
    """Students with overdue (unpaid/partial, past-due) invoices, with the
    total owed and invoice count per student."""
    today = today or datetime.date.today()
    overdue = StudentFeeInvoice.objects.filter(
        school=school,
        status__in=[StudentFeeInvoice.Status.UNPAID, StudentFeeInvoice.Status.PARTIAL],
        due_date__lt=today,
    )
    return (
        overdue.values(
            "student_id", "student__full_name",
            "student__class_section__grade", "student__class_section__section",
        )
        .annotate(owed=Sum("amount"), invoices=Count("pk"))
        .order_by("-owed")
    )
