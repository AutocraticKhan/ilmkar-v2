from django.urls import path

from . import views

app_name = "school_owner"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("financials/", views.financials, name="financials"),
    # transfers
    path("transfers/", views.transfers, name="transfers"),
    path("transfers/move/", views.transfer_person, name="transfer-person"),
    # group-wide policies
    path("policies/", views.policies, name="policies"),
    path("policies/create/", views.policy_create, name="policy-create"),
    path("policies/<int:policy_id>/override/", views.policy_override, name="policy-override"),
    path("policies/<int:policy_id>/override/delete/", views.policy_override_delete, name="policy-override-delete"),
    path("policies/<int:policy_id>/delete/", views.policy_delete, name="policy-delete"),
    # central hiring
    path("hiring/", views.hiring, name="hiring"),
    path("hiring/create/", views.job_create, name="job-create"),
    path("hiring/<int:job_id>/fill/", views.job_fill, name="job-fill"),
    path("hiring/<int:job_id>/reopen/", views.job_reopen, name="job-reopen"),
    path("hiring/<int:job_id>/delete/", views.job_delete, name="job-delete"),
    # central announcements
    path("announcements/", views.announcements, name="announcements"),
    path("announcements/create/", views.announcement_create, name="announcement-create"),
    path("announcements/<int:announcement_id>/delete/", views.announcement_delete, name="announcement-delete"),
    # approval workflows
    path("approvals/", views.approvals, name="approvals"),
    path("approvals/create/", views.approval_create, name="approval-create"),
    path("approvals/<int:request_id>/decide/", views.approval_decide, name="approval-decide"),
]
