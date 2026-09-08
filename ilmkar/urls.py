"""
URL configuration for ilmkar project.

The home URL (/) is handled by the SAAS_admin app: anonymous visitors get the
login page, and authenticated superusers are redirected to the dashboard.
"""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("SAAS_admin.urls")),
]
