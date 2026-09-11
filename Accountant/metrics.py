"""Snapshot + report metric computation for the Accountant dashboard.

Every money KPI is derived from the SAME sources the ledger sync uses
(``School_Admin.FeePayment``, ``Expense``, ``IncomeEntry``), so the
dashboard, the statement and the reconciliation page can never disagree.
Period labels use the platform-wide ``"%B %Y"`` format.
"""
import calendar
import datetime

from django.db.models import Count, Q, Sum

from School_Admin.models import ClassSection, FeePayment, StudentFeeInvoice

from .models import DefaulterFollowUp, Expense, IncomeEntry, LedgerEntry


def current_period(today=None):
    """Period label used across the dashboards, e.g. "September 2026"."""
    today = today or datetime.date.today()
    return today.strftime("%B %Y")


def month_starts(limit, today=None):
    """The first day of the last ``limit`` months, oldest first."""
    today = today or datetime.date.today()
    starts = []
    year, month = today.year, today.month
    for _ in range(limit):
        starts.append(datetime.date(year, month, 1))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return list(reversed(starts))


def month_label(day):
    """Human label for a month start date, e.g. "September 2026"."""
    return day.strftime("%B %Y")


def collections(school, since=None, until=None):
    """Total fees collected in a date window (defaults to all time)."""
    qs = FeePayment.objects.filter(invoice__school=school)
    if since is not None:
        qs = qs.filter(paid_on__gte=since)
    if until is not None:
        qs = qs.filter(paid_on__lte=until)
    return float(qs.aggregate(total=Sum("amount"))["total"] or 0)


def collection_kpis(school, today=None):
    """Collected today / this week / this month, plus the month's
    invoiced vs outstanding position and the overdue roll-up."""
    today = today or datetime.date.today()
    week_start = today - datetime.timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    collected_today = collections(school, since=today, until=today)
    collected_week = collections(school, since=week_start, until=today)
    collected_month = collections(school, since=month_start, until=today)
    invoiced_month = float(
        StudentFeeInvoice.objects.filter(
            school=school, period=current_period(today)
        ).aggregate(total=Sum("amount"))["total"] or 0
    )
    overdue = StudentFeeInvoice.objects.filter(
        school=school,
        status__in=[StudentFeeInvoice.Status.UNPAID, StudentFeeInvoice.Status.PARTIAL],
        due_date__lt=today,
    ).aggregate(amount=Sum("amount"), count=Count("pk"))

    return {
        "period": current_period(today),
        "collected_today": collected_today,
        "collected_week": collected_week,
        "collected_month": collected_month,
        "invoiced_month": invoiced_month,
        "outstanding_month": invoiced_month - collected_month,
        "overdue_amount": float(overdue["amount"] or 0),
        "overdue_count": overdue["count"] or 0,
        "collection_pct": (
            round(collected_month / invoiced_month * 100, 1)
            if invoiced_month else None
        ),
    }


def collections_by_class(school, since=None, until=None, today=None):
    """Collected vs invoiced per class section, in grade order.

    This is the "by class" cut of fee collections (the "by branch" cut is
    trivial for a single-school tenant: the whole statement IS the branch,
    so the class split is the drill-down that matters)."""
    today = today or datetime.date.today()
    month_start = since if since is not None else today.replace(day=1)
    month_end = until if until is not None else today

    rows = []
    for section in ClassSection.objects.filter(school=school).order_by(
        "grade", "section"
    ):
        invoiced = StudentFeeInvoice.objects.filter(
            school=school,
            student__class_section=section,
            period=current_period(today),
        ).aggregate(total=Sum("amount"))["total"] or 0
        collected = FeePayment.objects.filter(
            invoice__school=school,
            invoice__student__class_section=section,
            paid_on__gte=month_start,
            paid_on__lte=month_end,
        ).aggregate(total=Sum("amount"))["total"] or 0
        rows.append({
            "label": section.label,
            "invoiced": float(invoiced),
            "collected": float(collected),
            "collection_pct": (
                round(float(collected) / float(invoiced) * 100, 1)
                if invoiced else None
            ),
        })
    return rows


def expenses_by_category(school, since=None, until=None, today=None):
    """Expense totals grouped by category for a date window (the current
    month by default)."""
    today = today or datetime.date.today()
    since = since if since is not None else today.replace(day=1)
    until = until if until is not None else today
    qs = Expense.objects.filter(school=school, paid_on__gte=since, paid_on__lte=until)
    rows = []
    for category in Expense.Category:
        total = float(
            qs.filter(category=category).aggregate(total=Sum("amount"))["total"] or 0
        )
        if total:
            rows.append({
                "category": category,
                "label": category.label,
                "total": total,
            })
    return {"rows": rows, "total": float(qs.aggregate(total=Sum("amount"))["total"] or 0)}


def monthly_statement(school, limit=6, today=None):
    """Income & expense statement: per month (oldest first) the fees
    collected, other income received, expenses paid and the net result.

    Income side: ``FeePayment`` + ``IncomeEntry`` by their value dates.
    Expense side: ``Expense`` by ``paid_on`` (salaries enter here too —
    payroll "mark paid" books salary Expense rows, so nothing counts
    twice)."""
    today = today or datetime.date.today()
    rows = []
    for start in month_starts(limit, today):
        last_day = calendar.monthrange(start.year, start.month)[1]
        end = datetime.date(start.year, start.month, last_day)
        fees = collections(school, since=start, until=end)
        other_income = float(
            IncomeEntry.objects.filter(
                school=school, received_on__gte=start, received_on__lte=end
            ).aggregate(total=Sum("amount"))["total"] or 0
        )
        expenses = float(
            Expense.objects.filter(
                school=school, paid_on__gte=start, paid_on__lte=end
            ).aggregate(total=Sum("amount"))["total"] or 0
        )
        income = fees + other_income
        rows.append({
            "label": month_label(start),
            "fees": fees,
            "other_income": other_income,
            "income": income,
            "expenses": expenses,
            "net": income - expenses,
            "current": start == today.replace(day=1),
        })
    return rows


def payroll_totals(period):
    """Headline totals for one payroll run."""
    agg = period.items.aggregate(
        basic=Sum("basic"),
        allowances=Sum("allowances"),
        deductions=Sum("deductions"),
        count=Count("pk"),
    )
    basic = float(agg["basic"] or 0)
    allowances = float(agg["allowances"] or 0)
    deductions = float(agg["deductions"] or 0)
    return {
        "count": agg["count"] or 0,
        "basic": basic,
        "allowances": allowances,
        "deductions": deductions,
        "net": basic + allowances - deductions,
    }


def account_positions(school):
    """Per cash/bank account: book balance and the unreconciled backlog.

    Balance = opening_balance + IN - OUT over the account's ledger
    entries; the unreconciled part is what still needs to be matched
    against the real cash/bank position."""
    positions = []
    for account in school.cash_accounts.all():
        entries = account.ledger_entries.all()
        totals = entries.aggregate(
            inflow=Sum("amount", filter=Q(direction=LedgerEntry.Direction.IN)),
            outflow=Sum("amount", filter=Q(direction=LedgerEntry.Direction.OUT)),
        )
        inflow = float(totals["inflow"] or 0)
        outflow = float(totals["outflow"] or 0)
        pending = entries.filter(reconciled=False).aggregate(
            amount=Sum("amount"), count=Count("pk")
        )
        positions.append({
            "id": account.pk,
            "name": account.name,
            "kind": account.kind,
            "kind_display": account.get_kind_display(),
            "opening": float(account.opening_balance),
            "inflow": inflow,
            "outflow": outflow,
            "balance": float(account.opening_balance) + inflow - outflow,
            "unreconciled_amount": float(pending["amount"] or 0),
            "unreconciled_count": pending["count"] or 0,
        })
    return positions


def follow_up_index(school):
    """Latest follow-up per student id (for the defaulter list's status
    column). Returns {student_id: follow_up}."""
    latest = {}
    for fu in DefaulterFollowUp.objects.filter(school=school).select_related(
        "student"
    )[:500]:
        latest.setdefault(fu.student_id, fu)
    return latest


def defaulters(school, today=None):
    """Students with overdue (unpaid/partial, past-due) invoices, with
    the total owed and invoice count per student, biggest balance first."""
    today = today or datetime.date.today()
    overdue = StudentFeeInvoice.objects.filter(
        school=school,
        status__in=[StudentFeeInvoice.Status.UNPAID, StudentFeeInvoice.Status.PARTIAL],
        due_date__lt=today,
    )
    return (
        overdue.values(
            "student_id",
            "student__full_name",
            "student__class_section__grade",
            "student__class_section__section",
        )
        .annotate(owed=Sum("amount"), invoices=Count("pk"))
        .order_by("-owed")
    )


