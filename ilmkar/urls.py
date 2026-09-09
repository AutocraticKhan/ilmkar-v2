"""
URL configuration for ilmkar project.

The home URL (/) is handled by the SAAS_admin app: anonymous visitors get
the login page, and authenticated users are routed by account type —
superusers to the operator dashboard, chain/group owners to their group
dashboard at /chain/.
"""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("chain/", include("school_owner.urls")),
    path("", include("SAAS_admin.urls")),
]
