from django.contrib import admin

from .models import ParentChildLink, ParentPortalSetting, ParentProfile


@admin.register(ParentProfile)
class ParentProfileAdmin(admin.ModelAdmin):
    """``ParentProfile`` + ``ParentChildLink`` live together in the admin:
    link a user to the school, then attach their children in the inline."""

    list_display = ("user", "guardian_name", "school", "child_count", "created_at")
    list_filter = ("school",)
    search_fields = ("user__username", "guardian_name")
    inlines = []

    @admin.display(description="Children")
    def child_count(self, obj):
        return obj.child_links.count()


class ParentChildLinkInline(admin.TabularInline):
    model = ParentChildLink
    extra = 0
    autocomplete_fields = ["student"]


ParentProfileAdmin.inlines = [ParentChildLinkInline]


@admin.register(ParentChildLink)
class ParentChildLinkAdmin(admin.ModelAdmin):
    list_display = ("parent", "student", "relationship", "is_primary", "created_at")
    list_filter = ("is_primary", "parent__school")
    search_fields = ("parent__user__username", "student__full_name")


admin.site.register(ParentPortalSetting)