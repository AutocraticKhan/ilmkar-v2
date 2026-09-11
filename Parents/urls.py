from django.urls import path

from . import views

app_name = "Parents"

urlpatterns = [
    # family dashboard ("today at school" digest per child)
    path("", views.dashboard, name="dashboard"),
    # attendance & alerts
    path("attendance/", views.attendance, name="attendance"),
    # fee status (view; pay when the school allows it)
    path("fees/", views.fees, name="fees"),
    path("fees/<int:invoice_id>/pay/", views.invoice_pay, name="invoice-pay"),
    # results / report card
    path("results/", views.results, name="results"),
    # homework / assignments (read-only)
    path("homework/", views.homework, name="homework"),
    # notices from school
    path("notices/", views.notices, name="notices"),
    # message a teacher (one thread per child/subject)
    path("messages/", views.messages, name="messages"),
    path("messages/send/", views.message_send, name="message-send"),
]