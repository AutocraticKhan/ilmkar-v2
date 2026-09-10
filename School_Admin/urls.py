from django.urls import path

from . import views

app_name = "School_Admin"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    # students + admissions
    path("students/", views.students, name="students"),
    path("students/create/", views.student_create, name="student-create"),
    path("students/<int:student_id>/status/", views.student_status, name="student-status"),
    path("students/admissions/create/", views.admission_create, name="admission-create"),
    path("students/admissions/<int:application_id>/decide/", views.admission_decide, name="admission-decide"),
    # staff
    path("staff/", views.staff, name="staff"),
    path("staff/create/", views.staff_create, name="staff-create"),
    path("staff/<int:staff_id>/toggle/", views.staff_toggle, name="staff-toggle"),
    # fees
    path("fees/", views.fees, name="fees"),
    path("fees/heads/create/", views.fee_head_create, name="fee-head-create"),
    path("fees/heads/<int:head_id>/delete/", views.fee_head_delete, name="fee-head-delete"),
    path("fees/invoices/create/", views.invoice_create, name="invoice-create"),
    path("fees/invoices/<int:invoice_id>/pay/", views.invoice_pay, name="invoice-pay"),
    # approvals
    path("approvals/", views.approvals, name="approvals"),
    path("approvals/leave/create/", views.leave_create, name="leave-create"),
    path("approvals/leave/<int:leave_id>/decide/", views.leave_decide, name="leave-decide"),
    path("approvals/expenses/create/", views.expense_create, name="expense-create"),
    path("approvals/expenses/<int:expense_id>/decide/", views.expense_decide, name="expense-decide"),
    # reports
    path("reports/", views.reports, name="reports"),
    # notices
    path("notices/", views.notices, name="notices"),
    path("notices/create/", views.notice_create, name="notice-create"),
    path("notices/<int:notice_id>/delete/", views.notice_delete, name="notice-delete"),
    # front desk
    path("frontdesk/", views.frontdesk, name="frontdesk"),
    path("frontdesk/complaints/create/", views.complaint_create, name="complaint-create"),
    path("frontdesk/complaints/<int:complaint_id>/status/", views.complaint_status, name="complaint-status"),
    path("frontdesk/complaints/<int:complaint_id>/resolve/", views.complaint_resolve, name="complaint-resolve"),
    path("frontdesk/entries/create/", views.entry_create, name="entry-create"),
]
