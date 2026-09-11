from django.urls import path

from . import views

app_name = "Accountant"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    # fee collections + defaulters + follow-ups
    path("collections/", views.collections, name="collections"),
    path("followups/create/", views.followup_create, name="followup-create"),
    path("payments/record/", views.payment_record, name="payment-record"),
    # expenses (vendor payments, utility bills, salaries)
    path("expenses/", views.expenses, name="expenses"),
    path("expenses/create/", views.expense_create, name="expense-create"),
    # income & expense statement (P&L) + other income
    path("statement/", views.statement, name="statement"),
    path("income/create/", views.income_create, name="income-create"),
    # payroll processing
    path("payroll/", views.payroll, name="payroll"),
    path("payroll/periods/create/", views.period_create, name="period-create"),
    path("payroll/periods/<int:period_id>/calculate/", views.period_calculate, name="period-calculate"),
    path("payroll/items/<int:item_id>/update/", views.item_update, name="item-update"),
    path("payroll/periods/<int:period_id>/approve/", views.period_approve, name="period-approve"),
    path("payroll/periods/<int:period_id>/paid/", views.period_paid, name="period-paid"),
    path("payroll/items/<int:item_id>/payslip/", views.payslip, name="payslip"),
    # bank/cash reconciliation
    path("reconciliation/", views.reconciliation, name="reconciliation"),
    path("ledger/<int:entry_id>/reconcile/", views.entry_reconcile, name="entry-reconcile"),
    path("ledger/sync/", views.ledger_sync, name="ledger-sync"),
    # invoices & receipts (printing)
    path("receipts/", views.receipts, name="receipts"),
    path("receipts/print/", views.receipt_print, name="receipt-print"),
    # refunds & adjustments (approval trail)
    path("refunds/", views.refunds, name="refunds"),
    path("refunds/create/", views.refund_create, name="refund-create"),
    path("refunds/<int:refund_id>/approve/", views.refund_approve, name="refund-approve"),
    path("refunds/<int:refund_id>/reject/", views.refund_reject, name="refund-reject"),
    path("refunds/<int:refund_id>/paid/", views.refund_paid, name="refund-paid"),
]
