"""
URL configuration for ilmkar project.

The home URL (/) is handled by the SAAS_admin app: anonymous visitors get
the login page, and authenticated users are routed by account type —
superusers to the operator dashboard, chain/group owners to their group
dashboard at /chain/, school admins (principals) to their school dashboard at /school/.
"""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("chain/", include("school_owner.urls")),
    # School Admin / Principal dashboard (single school, day-to-day)
    path("school/", include("School_Admin.urls")),
    # Teacher / Staff dashboard (teacher + principal read-through)
    path("teacher/", include("Teachers.urls")),
    # Student dashboard (student role)
    path("student/", include("Student.urls")),
    # Parent / Family dashboard (parent role, multi-child)
    path("parent/", include("Parents.urls")),
    path("", include("SAAS_admin.urls")),
]
