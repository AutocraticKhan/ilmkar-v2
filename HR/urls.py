from django.urls import path

from . import views

app_name = "HR"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    # staff directory & contracts
    path("staff/", views.staff, name="staff"),
    path("staff/create/", views.staff_create, name="staff-create"),
    path("staff/<int:staff_id>/toggle/", views.staff_toggle, name="staff-toggle"),
    path("contracts/create/", views.contract_create, name="contract-create"),
    path("contracts/<int:contract_id>/end/", views.contract_end, name="contract-end"),
    # attendance (monthly grid)
    path("attendance/", views.attendance, name="attendance"),
    path("attendance/mark/", views.attendance_mark, name="attendance-mark"),
    # leave approvals + balances
    path("leaves/", views.leaves, name="leaves"),
    path("leaves/create/", views.leave_create, name="leave-create"),
    path("leaves/<int:leave_id>/approve/", views.leave_approve, name="leave-approve"),
    path("leaves/<int:leave_id>/reject/", views.leave_reject, name="leave-reject"),
    path("balances/create/", views.balance_create, name="balance-create"),
    # recruitment
    path("recruitment/", views.recruitment, name="recruitment"),
    path("postings/create/", views.posting_create, name="posting-create"),
    path("postings/<int:posting_id>/close/", views.posting_close, name="posting-close"),
    path("applications/create/", views.application_create, name="application-create"),
    path("applications/<int:application_id>/stage/", views.application_stage, name="application-stage"),
    path("applications/<int:application_id>/hire/", views.application_hire, name="application-hire"),
    path("interviews/create/", views.interview_create, name="interview-create"),
    path("interviews/<int:interview_id>/outcome/", views.interview_outcome, name="interview-outcome"),
    # onboarding checklists
    path("onboarding/", views.onboarding, name="onboarding"),
    path("onboarding/start/<int:staff_id>/", views.onboarding_start, name="onboarding-start"),
    path("onboarding/<int:task_id>/toggle/", views.onboarding_toggle, name="onboarding-toggle"),
    path("onboarding/add/", views.onboarding_add, name="onboarding-add"),
    # payroll input (feeds Accountant payroll)
    path("payroll-input/", views.payroll_input, name="payroll-input"),
    path("payroll-input/generate/", views.input_generate, name="input-generate"),
    path("payroll-input/<int:input_id>/update/", views.input_update, name="input-update"),
    path("payroll-input/feed/", views.input_feed, name="input-feed"),
    # performance appraisals
    path("appraisals/", views.appraisals, name="appraisals"),
    path("appraisals/create/", views.appraisal_create, name="appraisal-create"),
    path("appraisals/<int:appraisal_id>/update/", views.appraisal_update, name="appraisal-update"),
    path("appraisals/<int:appraisal_id>/finalize/", views.appraisal_finalize, name="appraisal-finalize"),
    # staff documents + expiry alerts
    path("documents/", views.documents, name="documents"),
    path("documents/add/", views.document_add, name="document-add"),
    # training / professional development
    path("training/", views.training, name="training"),
    path("training/programs/create/", views.program_create, name="program-create"),
    path("training/programs/<int:program_id>/status/", views.program_status, name="program-status"),
    path("training/enroll/", views.enrollment_create, name="enrollment-create"),
    path("training/enrollments/<int:enrollment_id>/update/", views.enrollment_update, name="enrollment-update"),
]
