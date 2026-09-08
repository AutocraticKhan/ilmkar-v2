from django.contrib import admin

from .models import School, SchoolUser


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "package", "status", "students", "renewal")
    list_filter = ("package", "status")
    search_fields = ("name", "city")


@admin.register(SchoolUser)
class SchoolUserAdmin(admin.ModelAdmin):
    list_display = ("user", "school", "role", "created_at")
    list_filter = ("role", "school")
    search_fields = ("user__username", "user__email")
