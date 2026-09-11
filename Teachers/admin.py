from django.contrib import admin

from .models import (
    Assignment,
    AssignmentSubmission,
    ClassDiary,
    GradeEntry,
    LessonPlan,
    Payslip,
    ReportCardComment,
    SharedResource,
    StudentAttendance,
    SubstituteAssignment,
    TeacherMessage,
    TeacherNote,
    TeacherProfile,
    TimetableSlot,
)


@admin.register(StudentAttendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ("student", "class_section", "date", "mark", "marked_by")
    list_filter = ("school", "mark", "date")
    search_fields = ("student__full_name",)


@admin.register(GradeEntry)
class GradeEntryAdmin(admin.ModelAdmin):
    list_display = ("student", "exam", "marks_obtained", "total_marks")
    list_filter = ("school", "exam")


@admin.register(TeacherMessage)
class TeacherMessageAdmin(admin.ModelAdmin):
    """How admin/parents currently send a teacher a message — until the
    parent portal + principal compose UI land (TODO(placeholder))."""
    list_display = ("staff", "sender_type", "sender_name", "subject", "is_read", "created_at")
    list_filter = ("school", "sender_type", "is_read")


admin.site.register((
    Assignment, AssignmentSubmission, ClassDiary, LessonPlan, Payslip,
    ReportCardComment, SharedResource, SubstituteAssignment, TeacherNote,
    TeacherProfile, TimetableSlot,
))
