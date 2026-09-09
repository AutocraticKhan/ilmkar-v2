from django.contrib import admin

from .models import (
    ApprovalRequest,
    BranchAnnouncement,
    Chain,
    ExamSummary,
    GroupPolicy,
    JobPosting,
    TransferLog,
)


@admin.register(Chain)
class ChainAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "created_at")
    search_fields = ("name", "owner__username")


admin.site.register((GroupPolicy, JobPosting, BranchAnnouncement, ApprovalRequest, TransferLog, ExamSummary))
