from django.urls import path

from . import views

app_name = "Student"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    # weekly timetable for the student's class section
    path("timetable/", views.timetable, name="timetable"),
    # assignments & submission
    path("assignments/", views.assignments, name="assignments"),
    path(
        "assignments/<int:assignment_id>/submit/",
        views.assignment_submit,
        name="assignment-submit",
    ),
    # results & report card
    path("results/", views.results, name="results"),
    # attendance record
    path("attendance/", views.attendance, name="attendance"),
    # library (books issued, due dates)
    path("library/", views.library, name="library"),
    # fee status (view; pay when the school allows it)
    path("fees/", views.fees, name="fees"),
    path("fees/<int:invoice_id>/pay/", views.invoice_pay, name="invoice-pay"),
    # notices
    path("notices/", views.notices, name="notices"),
    # quizzes / online tests
    path("quizzes/", views.quizzes, name="quizzes"),
    path("quizzes/<int:quiz_id>/", views.quiz_take, name="quiz-take"),
]