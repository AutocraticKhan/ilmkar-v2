from django.urls import path

from . import views

app_name = "SAAS_admin"

urlpatterns = [
    path("", views.login_view, name="home"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("users/", views.users, name="users"),
    path("logout/", views.logout_view, name="logout"),
    path("schools/create/", views.school_create, name="school-create"),
    path("schools/<int:school_id>/package/", views.school_package, name="school-package"),
    path("schools/<int:school_id>/status/", views.school_status, name="school-status"),
    path("schools/<int:school_id>/delete/", views.school_delete, name="school-delete"),
    path(
        "schools/<int:school_id>/owner/",
        views.school_owner_set,
        name="school-owner-set",
    ),
    path("schools/<int:school_id>/users/", views.school_users, name="school-users"),
    path("schools/<int:school_id>/users/create/", views.user_create, name="user-create"),
    path("schools/<int:school_id>/users/<int:user_id>/role/", views.user_role, name="user-role"),
    path("schools/<int:school_id>/users/<int:user_id>/delete/", views.user_delete, name="user-delete"),
    path("billing/", views.billing, name="billing"),
    path("invoices/<int:invoice_id>/paid/", views.invoice_paid, name="invoice-paid"),
    path("usage/", views.usage, name="usage"),
    path("support/", views.support, name="support"),
    path("tickets/<int:ticket_id>/", views.ticket_detail, name="ticket-detail"),
    path("tickets/<int:ticket_id>/reply/", views.ticket_reply, name="ticket-reply"),
    path("tickets/<int:ticket_id>/status/", views.ticket_status, name="ticket-status"),
    path("tickets/<int:ticket_id>/priority/", views.ticket_priority, name="ticket-priority"),
    path("announcements/", views.announcements, name="announcements"),
    path("announcements/create/", views.announcement_create, name="announcement-create"),
    path("announcements/<int:announcement_id>/delete/", views.announcement_delete, name="announcement-delete"),
    path("impersonate/<int:school_id>/start/", views.impersonate_start, name="impersonate-start"),
    path("impersonate/end/", views.impersonate_end, name="impersonate-end"),
    path("workspace/", views.workspace, name="workspace"),
    path("chains/", views.chains, name="chains"),
    path(
        "users/<int:user_id>/chain/",
        views.user_chain_set,
        name="user-chain-set",
    ),
    path(
        "chains/<int:chain_id>/owner/",
        views.chain_owner_set,
        name="chain-owner-set",
    ),
    path(
        "chains/create/",
        views.chain_create,
        name="chain-create",
    ),
    path("chains/<int:chain_id>/assign/", views.chain_assign, name="chain-assign"),
    path("schools/<int:school_id>/unassign/", views.chain_unassign, name="chain-unassign"),
    path("chains/<int:chain_id>/delete/", views.chain_delete, name="chain-delete"),
    path("chains/<int:chain_id>/owner-password/", views.chain_owner_password, name="chain-owner-password"),
]
