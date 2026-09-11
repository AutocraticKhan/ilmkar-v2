from django.contrib import admin

from .models import (
    Appraisal,
    AttendanceRecord,
    AuditLog,
    JobApplication,
    JobPosting,
    LeaveBalance,
    OnboardingChecklist,
    PayrollInput,
    StaffContract,
    StaffDocument,
    TrainingEnrollment,
    TrainingProgram,
)


class ReadOnlyModelAdmin(admin.ModelAdmin):
    """System-of-record admin: view-only, so the Django admin can never
    quietly rewrite the HR trail (same guard as the Accountant app)."""

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


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(ReadOnlyModelAdmin):
    list_display = ("staff", "date", "status", "unpaid", "marked_by")
    list_filter = ("status", "unpaid", "date")


admin.site.register(StaffContract)
admin.site.register(StaffDocument)
admin.site.register(LeaveBalance)
admin.site.register(JobPosting)
admin.site.register(JobApplication)
admin.site.register(OnboardingChecklist)
admin.site.register(Appraisal)
admin.site.register(TrainingProgram)
admin.site.register(TrainingEnrollment)
admin.site.register(PayrollInput)
