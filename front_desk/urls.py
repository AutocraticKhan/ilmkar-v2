from django.urls import path

from . import views

app_name = "front_desk"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    # admissions enquiries / lead funnel
    path("enquiries/", views.enquiries, name="enquiries"),
    path("enquiries/create/", views.enquiry_create, name="enquiry-create"),
    path("enquiries/<int:enquiry_id>/update/", views.enquiry_update, name="enquiry-update"),
    path("enquiries/<int:enquiry_id>/stage/", views.enquiry_stage, name="enquiry-stage"),
    # visitor log
    path("visitors/", views.visitors, name="visitors"),
    path("visitors/checkin/", views.visitor_checkin, name="visitor-checkin"),
    path("visitors/<int:visitor_id>/checkout/", views.visitor_checkout, name="visitor-checkout"),
    # complaint / request register
    path("complaints/", views.complaints, name="complaints"),
    path("complaints/create/", views.complaint_create, name="complaint-create"),
    path("complaints/<int:complaint_id>/status/", views.complaint_status, name="complaint-status"),
    # gate passes
    path("gate-passes/", views.gate_passes, name="gate-passes"),
    path("gate-passes/create/", views.gatepass_create, name="gatepass-create"),
    path("gate-passes/<int:pass_id>/return/", views.gatepass_return, name="gatepass-return"),
    path("gate-passes/<int:pass_id>/cancel/", views.gatepass_cancel, name="gatepass-cancel"),
    # ID cards
    path("id-cards/", views.id_cards, name="id-cards"),
    path("id-cards/create/", views.idcard_create, name="idcard-create"),
    path("id-cards/<int:card_id>/printed/", views.idcard_mark_printed, name="idcard-printed"),
    path("id-cards/<int:card_id>/print/", views.idcard_print, name="idcard-print"),
]