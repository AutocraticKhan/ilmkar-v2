from django.contrib import admin

from .models import (
    AdmissionEnquiry,
    AuditLog,
    GatePass,
    IDCard,
    VisitorLog,
)


class ReadOnlyModelAdmin(admin.ModelAdmin):
    """System-of-record admin: view-only, so the Django admin can never
    quietly rewrite the front-desk trail (same guard as the HR app)."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]


@admin.register(AuditLog)
class AuditLogAdmin(ReadOnlyModelAdmin):
    list_display = ("actor", "action", "target", "created_at")
    search_fields = ("actor", "action", "target")


@admin.register(AdmissionEnquiry)
class AdmissionEnquiryAdmin(ReadOnlyModelAdmin):
    list_display = ("applicant_name", "stage", "guardian_phone", "created_at")
    list_filter = ("stage", "source")


@admin.register(VisitorLog)
class VisitorLogAdmin(ReadOnlyModelAdmin):
    list_display = ("visitor_name", "purpose", "entered_at", "exited_at")
    list_filter = ("purpose",)


@admin.register(GatePass)
class GatePassAdmin(ReadOnlyModelAdmin):
    list_display = ("pass_no", "pass_type", "holder_name", "status", "issued_at")
    list_filter = ("pass_type", "status")


admin.site.register(IDCard)
