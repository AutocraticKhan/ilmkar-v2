from django.urls import path

from . import views

app_name = "SAAS_admin"

urlpatterns = [
    path("", views.login_view, name="home"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("logout/", views.logout_view, name="logout"),
    path("schools/create/", views.school_create, name="school-create"),
    path("schools/<int:school_id>/package/", views.school_package, name="school-package"),
    path("schools/<int:school_id>/status/", views.school_status, name="school-status"),
    path("schools/<int:school_id>/delete/", views.school_delete, name="school-delete"),
]
