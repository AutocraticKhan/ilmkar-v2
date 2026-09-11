from django.urls import path

from . import views

app_name = "Teachers"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    # one-tap attendance per class
    path("attendance/", views.attendance, name="attendance"),
    # marks / grades grid
    path("marks/", views.marks, name="marks"),
    # assignments / homework
    path("assignments/", views.assignments, name="assignments"),
    path("assignments/<int:assignment_id>/", views.assignment_submissions, name="assignment-submissions"),
    # class diary (what was taught today)
    path("diary/", views.diary, name="diary"),
    # lesson plan / curriculum tracker
    path("lesson-plans/", views.lesson_plans, name="lesson-plans"),
    path("lesson-plans/<int:plan_id>/status/", views.lesson_plan_status, name="lesson-plan-status"),
    # shared subject resource library
    path("resources/", views.resources, name="resources"),
    # inbox (admin/parents) + school notices
    path("inbox/", views.inbox, name="inbox"),
    # leave request + leave balance
    path("leave/", views.leave, name="leave"),
    # own payslip / salary history
    path("payslips/", views.payslips, name="payslips"),
    # private teacher notes per student (teachers/admin only)
    path("notes/", views.notes, name="notes"),
    # auto-generated report card comments
    path("report-comments/", views.report_comments, name="report-comments"),
    path("report-comments/<int:comment_id>/save/", views.report_comment_save, name="report-comment-save"),
    # substitute-teacher finder
    path("substitute/", views.substitute, name="substitute"),
    # early-warning analytics (attendance + marks trend)
    path("analytics/", views.analytics, name="analytics"),
]
