"""Accountant / Finance dashboard views.

Access model: every view is wrapped in ``accountant_required`` — the
signed-in user must hold a ``SchoolUser`` membership with the
``accountant`` role (principals are admitted too as a read-through /
approver, see ``utils``). All data is resolved through
``utils.current_school``, so a finance user can only ever see and affect
the ONE school their account belongs to.

Mutation endpoints follow the platform conventions: JSON body in, JSON
out, every write appends an ``AuditLog`` row (the approval trail) and
refreshes the ledger via ``LedgerEntry.sync_school``.
"""
import datetime
import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from School_Admin.models import (
    ClassSection,
    FeePayment,
    StaffMember,
    Student,
    StudentFeeInvoice,
)

from . import metrics
from .models import (
    AuditLog,
    CashAccount,
    DefaulterFollowUp,
    Expense,
    IncomeEntry,
    LedgerEntry,
    PayrollItem,
    PayrollPeriod,
    Refund,
)
from .utils import current_school, is_accountant


def _school_of(request):
    """The tenant scope of this finance user (their ONE school)."""
    return current_school(request.user)


def _is_accountant(user):
    return is_accountant(user)


accountant_required = user_passes_test(_is_accountant, login_url="/")


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
    return amount if amount > 0 else None


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
@accountant_required
def dashboard(request):
    """Finance snapshot: collections, expenses, net position and the
    open work queue (defaulters, pending refunds, payroll, reconciliation
    backlog)."""
    school = _school_of(request)
    today = datetime.date.today()
    LedgerEntry.sync_school(school)

    statement = metrics.monthly_statement(school, limit=6, today=today)
    this_month = statement[-1] if statement else {
        "label": metrics.month_label(today.replace(day=1)),
        "fees": 0, "other_income": 0, "income": 0, "expenses": 0, "net": 0,
        "current": True,
    }
    positions = metrics.account_positions(school)
    unreconciled_amount = sum(p["unreconciled_amount"] for p in positions)
    unreconciled_count = sum(p["unreconciled_count"] for p in positions)

    pending_refunds = Refund.objects.filter(
        school=school, status__in=[Refund.Status.REQUESTED, Refund.Status.APPROVED]
    )
    open_payroll = PayrollPeriod.objects.filter(
        school=school,
        status__in=[PayrollPeriod.Status.DRAFT, PayrollPeriod.Status.APPROVED],
    )

    return render(
        request,
        "Accountant/dashboard.html",
        {
            "school": school,
            "kpis": metrics.collection_kpis(school, today=today),
            "expenses_month": metrics.expenses_by_category(school, today=today),
            "this_month": this_month,
            "statement": statement,
            "positions": positions,
            "unreconciled_amount": unreconciled_amount,
            "unreconciled_count": unreconciled_count,
            "defaulters": list(metrics.defaulters(school, today=today))[:5],
            "pending_refunds": [r.as_dict() for r in pending_refunds[:5]],
            "pending_refunds_count": pending_refunds.count(),
            "open_payroll": [p.as_dict() for p in open_payroll],
            "open_payroll_count": open_payroll.count(),
            "recent_ledger": [
                e.as_dict()
                for e in LedgerEntry.objects.filter(school=school)
                .select_related("account")[:8]
            ],
            "recent_audit": [
                a.as_dict() for a in AuditLog.objects.filter(school=school)[:8]
            ],
        },
    )


# ---------- fee collections + defaulters ----------


def _defaulter_rows(school, today):
    """Overdue invoices grouped per student, with the latest follow-up
    status attached (the collections page's "status" column)."""
    follow_ups = metrics.follow_up_index(school)
    rows = []
    for row in metrics.defaulters(school, today=today):
        fu = follow_ups.get(row["student_id"])
        grade = row.get("student__class_section__grade")
        section = row.get("student__class_section__section")
        rows.append({
            "student_id": row["student_id"],
            "student_name": row["student__full_name"],
            "class_label": f"{grade}-{section}" if section else (grade or "—"),
            "invoices": row["invoices"],
            "owed": float(row["owed"]),
            "follow_up": fu.as_dict() if fu else None,
        })
    return rows


def _open_invoices(school):
    """Unpaid / partial invoices the accountant can record payments
    against, newest due first."""
    return [
        inv.as_dict()
        for inv in StudentFeeInvoice.objects.filter(
            school=school,
            status__in=[
                StudentFeeInvoice.Status.UNPAID,
                StudentFeeInvoice.Status.PARTIAL,
            ],
        ).select_related("student", "student__class_section")[:100]
    ]


@login_required
@accountant_required
def collections(request):
    """Fee collection cockpit: today/week/month KPIs, per-class split,
    the defaulter list with follow-up statuses, and the open invoices."""
    school = _school_of(request)
    today = datetime.date.today()
    return render(
        request,
        "Accountant/collections.html",
        {
            "school": school,
            "kpis": metrics.collection_kpis(school, today=today),
            "by_class": metrics.collections_by_class(school, today=today),
            "defaulters": _defaulter_rows(school, today),
            "open_invoices": _open_invoices(school),
            "follow_ups": [
                fu.as_dict()
                for fu in DefaulterFollowUp.objects.filter(school=school)
                .select_related("student")[:15]
            ],
        },
    )


@login_required
@accountant_required
@require_POST
def followup_create(request):
    """Log a defaulter follow-up (called / promised / visited ...)."""
    school = _school_of(request)
    body, error = _parse_body(request)
    if error:
        return error
    student = get_object_or_404(Student, school=school, pk=body.get("student_id"))
    outcome = body.get("outcome")
    if outcome not in DefaulterFollowUp.Outcome.values:
        return _bad("Choose a valid follow-up outcome.")
    promised_on = _parse_date(body.get("promised_on"))
    if outcome == DefaulterFollowUp.Outcome.PROMISED and promised_on is None:
        return _bad("A promised date is required for promised-to-pay outcomes.")
    fu = DefaulterFollowUp.objects.create(
        school=school,
        student=student,
        outcome=outcome,
        promised_on=promised_on,
        note=str(body.get("note", ""))[:2000],
        followed_up_by=_actor(request),
    )
    AuditLog.record(
        school, _actor(request), "follow-up logged",
        f"{student.full_name} — {fu.get_outcome_display()}",
    )
    return JsonResponse({"ok": True, "follow_up": fu.as_dict()})


@login_required
@accountant_required
@require_POST
def payment_record(request):
    """Record a fee payment against an invoice (full or partial).

    Mirrors ``School_Admin.views.invoice_pay``'s status rules and adds the
    finance-side bookkeeping: an audit row + a ledger entry (via sync)."""
    school = _school_of(request)
    body, error = _parse_body(request)
    if error:
        return error
    invoice = get_object_or_404(
        StudentFeeInvoice, school=school, pk=body.get("invoice_id")
    )
    if invoice.status == StudentFeeInvoice.Status.PAID:
        return _bad("This invoice is already fully paid.")
    amount = _parse_amount(body.get("amount"))
    if amount is None:
        return _bad("Enter a payment amount greater than zero.")
    method = body.get("method")
    if method not in FeePayment.Method.values:
        return _bad("Choose a valid payment method.")
    paid_on = _parse_date(body.get("paid_on")) or datetime.date.today()

    with transaction.atomic():
        payment = FeePayment.objects.create(
            invoice=invoice,
            amount=amount,
            paid_on=paid_on,
            method=method,
            received_by=_actor(request),
        )
        paid_total = sum(p.amount for p in invoice.payments.all())
        if paid_total >= invoice.amount:
            invoice.status = StudentFeeInvoice.Status.PAID
        elif paid_total > 0:
            invoice.status = StudentFeeInvoice.Status.PARTIAL
        invoice.save()

    LedgerEntry.sync_school(school)
    AuditLog.record(
        school, _actor(request), "fee payment recorded",
        f"{invoice.student.full_name} — {invoice.period}",
        note=f"Rs {amount} via {payment.get_method_display()}",
    )
    return JsonResponse({
        "ok": True,
        "payment": payment.as_dict(),
        "invoice": invoice.as_dict(),
    })


# ---------- expenses + other income ----------


@login_required
@accountant_required
def expenses(request):
    """Expense tracking: vendor payments, utility bills, salaries and
    rent, filterable by category."""
    school = _school_of(request)
    today = datetime.date.today()
    category = request.GET.get("category")
    qs = Expense.objects.filter(school=school)
    active_category = None
    if category in Expense.Category.values:
        qs = qs.filter(category=category)
        active_category = category
    return render(
        request,
        "Accountant/expenses.html",
        {
            "school": school,
            "expenses": [e.as_dict() for e in qs[:100]],
            "expenses_count": qs.count(),
            "by_category": metrics.expenses_by_category(school, today=today),
            "active_category": active_category,
            "categories": [
                {"value": c, "label": c.label} for c in Expense.Category
            ],
        },
    )


@login_required
@accountant_required
@require_POST
def expense_create(request):
    """Record an expense payment (vendor bill, utility, salary, rent)."""
    school = _school_of(request)
    body, error = _parse_body(request)
    if error:
        return error
    title = str(body.get("title", "")).strip()
    if not title:
        return _bad("Give the expense a title.")
    category = body.get("category")
    if category not in Expense.Category.values:
        return _bad("Choose a valid expense category.")
    amount = _parse_amount(body.get("amount"))
    if amount is None:
        return _bad("Enter an amount greater than zero.")
    method = body.get("method")
    if method not in Expense.Method.values:
        return _bad("Choose a valid payment method.")
    paid_on = _parse_date(body.get("paid_on"))
    if paid_on is None:
        return _bad("Enter the date the expense was paid.")
    expense = Expense.objects.create(
        school=school,
        title=title[:200],
        category=category,
        vendor=str(body.get("vendor", "")).strip()[:150],
        amount=amount,
        method=method,
        paid_on=paid_on,
        reference_no=str(body.get("reference_no", "")).strip()[:60],
        details=str(body.get("details", ""))[:2000],
        recorded_by=_actor(request),
    )
    LedgerEntry.sync_school(school)
    AuditLog.record(
        school, _actor(request), "expense recorded",
        f"{expense.title} ({expense.get_category_display()})",
        note=f"Rs {amount} via {expense.get_method_display()}",
    )
    return JsonResponse({"ok": True, "expense": expense.as_dict()})


# ---------- income & expense statement (P&L) ----------


@login_required
@accountant_required
def statement(request):
    """Income & expense statement: monthly P&L (fees + other income vs
    expenses), the current month's expense split, per-class collections
    (the single-school "branch" drill-down) and the other-income register
    with receipt numbers."""
    school = _school_of(request)
    today = datetime.date.today()
    try:
        months = max(1, min(12, int(request.GET.get("months", 6))))
    except (TypeError, ValueError):
        months = 6
    return render(
        request,
        "Accountant/statement.html",
        {
            "school": school,
            "statement": metrics.monthly_statement(school, limit=months, today=today),
            "months": months,
            "expenses_by_category": metrics.expenses_by_category(school, today=today),
            "by_class": metrics.collections_by_class(school, today=today),
            "income_entries": [
                i.as_dict() for i in IncomeEntry.objects.filter(school=school)[:50]
            ],
        },
    )


@login_required
@accountant_required
@require_POST
def income_create(request):
    """Record other income (rent, canteen, donations...) and get a
    receipt number for printing."""
    school = _school_of(request)
    body, error = _parse_body(request)
    if error:
        return error
    title = str(body.get("title", "")).strip()
    if not title:
        return _bad("Give the income a title.")
    source = body.get("source")
    if source not in IncomeEntry.Source.values:
        return _bad("Choose a valid income source.")
    amount = _parse_amount(body.get("amount"))
    if amount is None:
        return _bad("Enter an amount greater than zero.")
    method = body.get("method")
    if method not in IncomeEntry.Method.values:
        return _bad("Choose a valid payment method.")
    received_on = _parse_date(body.get("received_on"))
    if received_on is None:
        return _bad("Enter the date the income was received.")
    receipt_no = _next_receipt_no(school)
    income = IncomeEntry.objects.create(
        school=school,
        title=title[:200],
        source=source,
        amount=amount,
        method=method,
        received_on=received_on,
        receipt_no=receipt_no,
        details=str(body.get("details", ""))[:2000],
        recorded_by=_actor(request),
    )
    LedgerEntry.sync_school(school)
    AuditLog.record(
        school, _actor(request), "income recorded",
        f"{income.title} ({income.get_source_display()})",
        note=f"Rs {amount} — receipt {receipt_no}",
    )
    return JsonResponse({"ok": True, "income": income.as_dict()})


def _next_receipt_no(school):
    """Per-school sequential receipt number, e.g. RCPT-2026-0007."""
    year = timezone.now().year
    count = IncomeEntry.objects.filter(school=school).count() + 1
    receipt_no = f"RCPT-{year}-{count:04d}"
    while IncomeEntry.objects.filter(school=school, receipt_no=receipt_no).exists():
        count += 1
        receipt_no = f"RCPT-{year}-{count:04d}"
    return receipt_no


# ---------- payroll processing ----------


def _salary_defaults(school, staff, exclude_period=None):
    """Prefill (basic, allowances, deductions) for a payroll item.

    Source order: the staff member's latest ``Teachers.Payslip`` (their
    salary history), then their latest OTHER payroll item, then zeros for
    the accountant to fill in.
    """
    from Teachers.models import Payslip

    payslip = Payslip.objects.filter(school=school, staff=staff).first()
    if payslip is not None:
        return payslip.basic, payslip.allowances, payslip.deductions
    items = PayrollItem.objects.filter(school=school, staff=staff)
    if exclude_period is not None:
        items = items.exclude(period=exclude_period)
    previous = items.first()
    if previous is not None:
        return previous.basic, previous.allowances, previous.deductions
    return 0, 0, 0


def _period_or_404(school, period_id):
    return get_object_or_404(PayrollPeriod, school=school, pk=period_id)


@login_required
@accountant_required
def payroll(request):
    """Payroll processing: pick/create a period, calculate from salary
    history, edit items, then approve and mark as paid."""
    school = _school_of(request)
    today = datetime.date.today()

    periods = []
    for period in PayrollPeriod.objects.filter(school=school):
        row = period.as_dict()
        row.update(metrics.payroll_totals(period))
        periods.append(row)

    selected = None
    try:
        selected_id = int(request.GET.get("period", 0))
    except (TypeError, ValueError):
        selected_id = 0
    if selected_id:
        selected = PayrollPeriod.objects.filter(
            school=school, pk=selected_id
        ).first()
    if selected is None and periods:
        selected = PayrollPeriod.objects.get(school=school, pk=periods[0]["id"])

    items = [i.as_dict() for i in selected.items.select_related("staff")] if selected else []

    return render(
        request,
        "Accountant/payroll.html",
        {
            "school": school,
            "periods": periods,
            "selected": selected.as_dict() if selected else None,
            "totals": metrics.payroll_totals(selected) if selected else None,
            "items": items,
            "current_period": metrics.current_period(today),
            "active_staff": StaffMember.objects.filter(
                school=school, is_active=True
            ).count(),
        },
    )


@login_required
@accountant_required
@require_POST
def period_create(request):
    """Open a payroll run for a period (defaults to the current one)."""
    school = _school_of(request)
    body, error = _parse_body(request)
    if error:
        return error
    period_label = str(body.get("period", "")).strip() or metrics.current_period()
    if PayrollPeriod.objects.filter(school=school, period=period_label).exists():
        return _bad(f"A payroll run for {period_label} already exists.")
    period = PayrollPeriod.objects.create(
        school=school, period=period_label[:30], created_by=_actor(request)
    )
    AuditLog.record(school, _actor(request), "payroll opened", period_label)
    return JsonResponse({"ok": True, "period": period.as_dict()})


@login_required
@accountant_required
@require_POST
def period_calculate(request, period_id):
    """(Re)calculate the run: one item per active staff member, prefilled
    from salary history. Draft runs only."""
    school = _school_of(request)
    period = _period_or_404(school, period_id)
    if period.status != PayrollPeriod.Status.DRAFT:
        return _bad("Only draft payroll runs can be recalculated.")
    created = 0
    for staff in StaffMember.objects.filter(school=school, is_active=True):
        basic, allowances, deductions = _salary_defaults(school, staff)
        item, was_created = PayrollItem.objects.get_or_create(
            period=period,
            staff=staff,
            school=school,
            defaults={
                "basic": basic,
                "allowances": allowances,
                "deductions": deductions,
            },
        )
        if was_created:
            created += 1
    AuditLog.record(
        school, _actor(request), "payroll calculated",
        f"{period.period}",
        note=f"{created} new item(s); {period.items.count()} staff in the run",
    )
    return JsonResponse({"ok": True, "created": created})


@login_required
@accountant_required
@require_POST
def item_update(request, item_id):
    """Edit one staff member's pay lines while the run is still draft."""
    school = _school_of(request)
    item = get_object_or_404(PayrollItem, school=school, pk=item_id)
    if item.period.status != PayrollPeriod.Status.DRAFT:
        return _bad("Pay lines can only be edited while the run is draft.")
    body, error = _parse_body(request)
    if error:
        return error
    basic = _parse_amount(body.get("basic"))
    allowances = body.get("allowances")
    deductions = body.get("deductions")
    if basic is None:
        return _bad("Enter a basic salary of zero or more.")
    try:
        allowances = Decimal(str(allowances if allowances not in (None, "") else 0))
        deductions = Decimal(str(deductions if deductions not in (None, "") else 0))
    except (InvalidOperation, TypeError, ValueError):
        return _bad("Allowances and deductions must be numbers.")
    if allowances < 0 or deductions < 0:
        return _bad("Allowances and deductions cannot be negative.")
    item.basic = basic
    item.allowances = allowances
    item.deductions = deductions
    item.save()
    AuditLog.record(
        school, _actor(request), "pay line updated",
        f"{item.staff.full_name} — {item.period.period}",
        note=f"net Rs {item.net_pay}",
    )
    return JsonResponse({"ok": True, "item": item.as_dict()})


@login_required
@accountant_required
@require_POST
def period_approve(request, period_id):
    """Freeze a draft run for payout (who approved is stamped + audited)."""
    school = _school_of(request)
    period = _period_or_404(school, period_id)
    if period.status != PayrollPeriod.Status.DRAFT:
        return _bad("Only draft payroll runs can be approved.")
    if not period.items.exists():
        return _bad("Calculate the run first — there is nothing to approve.")
    period.status = PayrollPeriod.Status.APPROVED
    period.approved_by = _actor(request)
    period.approved_at = timezone.now()
    period.save()
    AuditLog.record(
        school, _actor(request), "payroll approved", period.period,
        note=f"Rs {metrics.payroll_totals(period)['net']} net",
    )
    return JsonResponse({"ok": True, "period": period.as_dict()})


@login_required
@accountant_required
@require_POST
def period_paid(request, period_id):
    """Mark an approved run as PAID.

    For every item this creates one salary ``Expense`` (which the ledger
    sync books as money out — so the P&L counts salaries exactly once)
    and mirrors a ``Teachers.Payslip`` row so the teacher's salary
    history keeps working."""
    school = _school_of(request)
    period = _period_or_404(school, period_id)
    if period.status != PayrollPeriod.Status.APPROVED:
        return _bad("Only approved payroll runs can be marked as paid.")
    body, error = _parse_body(request)
    if error:
        return error
    paid_on = _parse_date(body.get("paid_on")) or datetime.date.today()

    with transaction.atomic():
        items = list(period.items.select_related("staff"))
        for item in items:
            Expense.objects.create(
                school=school,
                title=f"Salary — {item.staff.full_name} ({period.period})",
                category=Expense.Category.SALARY,
                vendor=item.staff.full_name,
                amount=item.net_pay,
                method=Expense.Method.BANK,
                paid_on=paid_on,
                reference_no=f"PAYROLL-{period.pk}-{item.pk}",
                details=(
                    f"basic Rs {item.basic} + allowances Rs {item.allowances} "
                    f"- deductions Rs {item.deductions}"
                ),
                recorded_by=_actor(request),
            )
            # Mirror into the teacher dashboard's salary history
            # (unique per staff + period, so re-marks stay idempotent).
            from Teachers.models import Payslip

            Payslip.objects.get_or_create(
                school=school,
                staff=item.staff,
                period=period.period,
                defaults={
                    "basic": item.basic,
                    "allowances": item.allowances,
                    "deductions": item.deductions,
                    "paid_on": paid_on,
                },
            )
            item.paid_on = paid_on
            item.save()
        period.status = PayrollPeriod.Status.PAID
        period.save()

    LedgerEntry.sync_school(school)
    AuditLog.record(
        school, _actor(request), "payroll paid", period.period,
        note=f"Rs {metrics.payroll_totals(period)['net']} disbursed to "
             f"{len(items)} staff",
    )
    return JsonResponse({"ok": True, "period": period.as_dict()})


@login_required
@accountant_required
def payslip(request, item_id):
    """Printable payslip for one payroll item (tenant-scoped)."""
    school = _school_of(request)
    item = get_object_or_404(
        PayrollItem.objects.select_related("period", "staff"),
        school=school, pk=item_id,
    )
    return render(
        request,
        "Accountant/payslip_print.html",
        {
            "school": school,
            "item": item,
            "totals": metrics.payroll_totals(item.period),
            "today": datetime.date.today(),
        },
    )


# ---------- bank/cash reconciliation ----------


@login_required
@accountant_required
def reconciliation(request):
    """Bank/cash reconciliation: per account the book balance (opening +
    in - out) vs the reconciled position, plus the entry list with
    one-click "mark reconciled"."""
    school = _school_of(request)
    created = LedgerEntry.sync_school(school)

    account_id = request.GET.get("account")
    only_unreconciled = request.GET.get("only") == "unreconciled"
    entries_qs = LedgerEntry.objects.filter(school=school).select_related("account")
    try:
        account_id = int(account_id) if account_id else 0
    except (TypeError, ValueError):
        account_id = 0
    if account_id:
        entries_qs = entries_qs.filter(account_id=account_id)
    if only_unreconciled:
        entries_qs = entries_qs.filter(reconciled=False)
    return render(
        request,
        "Accountant/reconciliation.html",
        {
            "school": school,
            "positions": metrics.account_positions(school),
            "entries": [e.as_dict() for e in entries_qs[:150]],
            "selected_account": account_id or None,
            "only_unreconciled": only_unreconciled,
            "synced_count": created,
            "accounts": [
                {"id": a.pk, "name": a.name}
                for a in CashAccount.objects.filter(school=school)
            ],
        },
    )


@login_required
@accountant_required
@require_POST
def entry_reconcile(request, entry_id):
    """Flag one ledger entry as matched against the real cash/bank
    position (who reconciled it is stamped + audited)."""
    school = _school_of(request)
    entry = get_object_or_404(LedgerEntry, school=school, pk=entry_id)
    if entry.reconciled:
        return _bad("This entry is already reconciled.")
    entry.reconciled = True
    entry.reconciled_at = timezone.now()
    entry.reconciled_by = _actor(request)
    entry.save()
    AuditLog.record(
        school, _actor(request), "ledger reconciled",
        f"{entry.get_source_type_display()} — {entry.description}",
        note=f"Rs {entry.amount} on {entry.entry_date} ({entry.account.name})",
    )
    return JsonResponse({"ok": True, "entry": entry.as_dict()})


@login_required
@accountant_required
@require_POST
def ledger_sync(request):
    """Manual "pull recorded money movements into the ledger" run."""
    school = _school_of(request)
    created = LedgerEntry.sync_school(school)
    if created:
        AuditLog.record(
            school, _actor(request), "ledger synced", "ledger",
            note=f"{created} new entr(ies) pulled in",
        )
    return JsonResponse({"ok": True, "created": created})


# ---------- invoices & receipts (printing) ----------


@login_required
@accountant_required
def receipts(request):
    """Receipt register: fee payments (from the school-side invoices) and
    other-income entries, each printable."""
    school = _school_of(request)
    payments = FeePayment.objects.filter(
        invoice__school=school
    ).select_related("invoice__student", "invoice__student__class_section")[:100]
    payment_rows = []
    for p in payments:
        inv = p.invoice
        payment_rows.append({
            "id": p.pk,
            "student_name": inv.student.full_name,
            "class_label": inv.student.class_section.label
            if inv.student.class_section_id else "—",
            "period": inv.period,
            "fee_head": inv.fee_head.name if inv.fee_head_id else "Tuition",
            "amount": float(p.amount),
            "paid_on": p.paid_on.isoformat(),
            "method_display": p.get_method_display(),
            "received_by": p.received_by or "—",
        })
    return render(
        request,
        "Accountant/receipts.html",
        {
            "school": school,
            "payments": payment_rows,
            "income_entries": [
                i.as_dict() for i in IncomeEntry.objects.filter(school=school)[:50]
            ],
        },
    )


@login_required
@accountant_required
def receipt_print(request):
    """Printable receipt — ?source=fee|income&id=<pk>, always resolved
    inside the tenant scope."""
    school = _school_of(request)
    source = request.GET.get("source")
    try:
        object_id = int(request.GET.get("id", 0))
    except (TypeError, ValueError):
        object_id = 0
    context = {"school": school, "today": datetime.date.today()}

    if source == "fee" and object_id:
        payment = get_object_or_404(
            FeePayment.objects.select_related(
                "invoice__student", "invoice__student__class_section"
            ),
            pk=object_id, invoice__school=school,
        )
        invoice = payment.invoice
        context.update({
            "kind": "fee",
            "receipt_no": f"FC-{invoice.school_id}-{payment.pk:05d}",
            "payment": payment,
            "invoice": invoice,
            "student": invoice.student,
        })
    elif source == "income" and object_id:
        income = get_object_or_404(IncomeEntry, school=school, pk=object_id)
        context.update({"kind": "income", "income": income})
    else:
        raise Http404("Receipt not found.")
    return render(request, "Accountant/receipt_print.html", context)


# ---------- refunds & adjustments (approval trail) ----------


@login_required
@accountant_required
def refunds(request):
    """Refunds & adjustments log with the full approval trail and the
    recent audit feed (append-only)."""
    school = _school_of(request)
    status_filter = request.GET.get("status")
    qs = Refund.objects.filter(school=school).select_related(
        "student__class_section", "invoice"
    )
    if status_filter in Refund.Status.values:
        qs = qs.filter(status=status_filter)
    return render(
        request,
        "Accountant/refunds.html",
        {
            "school": school,
            "refunds": [r.as_dict() for r in qs[:100]],
            "refunds_count": qs.count(),
            "active_status": status_filter or None,
            "statuses": [
                {"value": s, "label": s.label} for s in Refund.Status
            ],
            "students": [
                {"id": s.pk, "name": s.full_name,
                 "class": s.class_section.label if s.class_section_id else "—"}
                for s in Student.objects.filter(
                    school=school, status=Student.Status.ACTIVE
                ).select_related("class_section")[:200]
            ],
            "audit": [a.as_dict() for a in AuditLog.objects.filter(school=school)[:30]],
        },
    )


@login_required
@accountant_required
@require_POST
def refund_create(request):
    """Log a refund/adjustment REQUEST. Money never moves here — only at
    the separate approve + mark-paid steps (and never by the same person
    who requested it)."""
    school = _school_of(request)
    body, error = _parse_body(request)
    if error:
        return error
    student = get_object_or_404(Student, school=school, pk=body.get("student_id"))
    kind = body.get("kind")
    if kind not in Refund.Kind.values:
        return _bad("Choose refund or adjustment.")
    amount = _parse_amount(body.get("amount"))
    if amount is None:
        return _bad("Enter an amount greater than zero.")
    reason = str(body.get("reason", "")).strip()
    if not reason:
        return _bad("A reason is required — it becomes part of the approval trail.")
    invoice = None
    invoice_id = body.get("invoice_id")
    if invoice_id:
        invoice = StudentFeeInvoice.objects.filter(
            school=school, student=student, pk=invoice_id
        ).first()
        if invoice is None:
            return _bad("That invoice does not belong to this student.")
    refund = Refund.objects.create(
        school=school,
        student=student,
        invoice=invoice,
        kind=kind,
        amount=amount,
        reason=reason[:2000],
        requested_by=_actor(request),
    )
    AuditLog.record(
        school, _actor(request), "refund requested",
        f"{refund.get_kind_display()} — {student.full_name}",
        note=f"Rs {amount}: {reason[:200]}",
    )
    return JsonResponse({"ok": True, "refund": refund.as_dict()})


@login_required
@accountant_required
@require_POST
def refund_approve(request, refund_id):
    """Approve a requested refund — REFUSES self-approval, so the person
    asking for money can never be the one waving it through."""
    school = _school_of(request)
    refund = get_object_or_404(
        Refund.objects.select_related("student"), school=school, pk=refund_id
    )
    if refund.status != Refund.Status.REQUESTED:
        return _bad("Only requested refunds can be approved.")
    if refund.requested_by == _actor(request):
        return _forbidden(
            "You requested this refund — a different user must approve it."
        )
    body, error = _parse_body(request)
    if error:
        return error
    refund.status = Refund.Status.APPROVED
    refund.approved_by = _actor(request)
    refund.decided_at = timezone.now()
    refund.decision_note = str(body.get("note", ""))[:300]
    refund.save()
    AuditLog.record(
        school, _actor(request), "refund approved",
        f"{refund.get_kind_display()} — {refund.student.full_name}",
        note=f"Rs {refund.amount}",
    )
    return JsonResponse({"ok": True, "refund": refund.as_dict()})


@login_required
@accountant_required
@require_POST
def refund_reject(request, refund_id):
    """Reject a requested refund (decision note required)."""
    school = _school_of(request)
    refund = get_object_or_404(
        Refund.objects.select_related("student"), school=school, pk=refund_id
    )
    if refund.status != Refund.Status.REQUESTED:
        return _bad("Only requested refunds can be rejected.")
    body, error = _parse_body(request)
    if error:
        return error
    note = str(body.get("note", "")).strip()
    if not note:
        return _bad("Give a short reason for the rejection.")
    refund.status = Refund.Status.REJECTED
    refund.decided_at = timezone.now()
    refund.decision_note = note[:300]
    refund.save()
    AuditLog.record(
        school, _actor(request), "refund rejected",
        f"{refund.get_kind_display()} — {refund.student.full_name}",
        note=note[:300],
    )
    return JsonResponse({"ok": True, "refund": refund.as_dict()})


@login_required
@accountant_required
@require_POST
def refund_paid(request, refund_id):
    """Mark an APPROVED refund as paid — this is the step money leaves,
    after which the ledger sync books it as money out."""
    school = _school_of(request)
    refund = get_object_or_404(
        Refund.objects.select_related("student"), school=school, pk=refund_id
    )
    if refund.status != Refund.Status.APPROVED:
        return _bad("Only approved refunds can be marked as paid.")
    body, error = _parse_body(request)
    if error:
        return error
    refund.status = Refund.Status.PAID
    refund.paid_on = _parse_date(body.get("paid_on")) or datetime.date.today()
    refund.save()
    LedgerEntry.sync_school(school)
    AuditLog.record(
        school, _actor(request), "refund paid",
        f"{refund.get_kind_display()} — {refund.student.full_name}",
        note=f"Rs {refund.amount} on {refund.paid_on}",
    )
    return JsonResponse({"ok": True, "refund": refund.as_dict()})










