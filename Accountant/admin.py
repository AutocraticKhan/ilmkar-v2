from django.contrib import admin

from .models import (
    AuditLog,
    CashAccount,
    DefaulterFollowUp,
    Expense,
    IncomeEntry,
    LedgerEntry,
    PayrollItem,
    PayrollPeriod,
    Refund,
)


class ReadOnlyModelAdmin(admin.ModelAdmin):
    """System-of-record admin: view-only, so the Django admin can never
    quietly rewrite the books or the approval trail."""

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


@admin.register(LedgerEntry)
class LedgerEntryAdmin(ReadOnlyModelAdmin):
    list_display = ("direction", "amount", "entry_date", "source_type", "account", "reconciled")
    list_filter = ("direction", "source_type", "reconciled", "account")


admin.site.register(CashAccount)
admin.site.register(Expense)
admin.site.register(IncomeEntry)
admin.site.register(PayrollPeriod)
admin.site.register(PayrollItem)
admin.site.register(Refund)
admin.site.register(DefaulterFollowUp)
