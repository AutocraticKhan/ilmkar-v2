from django.contrib import admin

from .models import (
    AdmissionApplication,
    AttendanceSnapshot,
    ClassSection,
    Complaint,
    ExamRecord,
    ExpenseRequest,
    FeeHead,
    FeePayment,
    FrontDeskEntry,
    LeaveRequest,
    Notice,
    Student,
    StudentFeeInvoice,
    StaffMember,
)


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("full_name", "admission_no", "school", "class_section", "status")
    list_filter = ("school", "status")
    search_fields = ("full_name", "admission_no", "guardian_name")


@admin.register(StudentFeeInvoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("student", "school", "period", "amount", "due_date", "status")
    list_filter = ("school", "status", "period")


admin.site.register((
    AdmissionApplication, AttendanceSnapshot, ClassSection, Complaint,
    ExamRecord, ExpenseRequest, FeeHead, FeePayment, FrontDeskEntry,
    LeaveRequest, Notice, StaffMember,
))
