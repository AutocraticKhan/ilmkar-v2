from django.contrib import admin

from .models import Book, BookIssue, PortalSetting, Quiz, QuizAttempt, QuizQuestion, StudentProfile


@admin.register(BookIssue)
class BookIssueAdmin(admin.ModelAdmin):
    list_display = (
        "student", "book", "issued_on", "due_date", "returned_on", "is_overdue",
    )
    list_filter = ("school", "returned_on", "due_date")
    search_fields = ("student__full_name", "book__title")


@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = ("student", "quiz", "score", "total_marks", "submitted_at")
    list_filter = ("school", "quiz")


admin.site.register((
    Book, PortalSetting, Quiz, QuizQuestion, StudentProfile,
))