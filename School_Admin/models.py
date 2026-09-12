"""Models for the School Admin / Principal dashboard (single school).

``School_Admin`` is the day-to-day cockpit for ONE school: admissions,
student records, staff, fees, approvals, reports, notices and the front
desk. Two kinds of models live here:

1. Placeholder school-side records — ``ClassSection``, ``Student``,
   ``AdmissionApplication``, ``StaffMember``, ``LeaveRequest``,
   ``ExpenseRequest``, ``FeeHead``, ``StudentFeeInvoice``, ``FeePayment``,
   ``AttendanceSnapshot``, ``ExamRecord`` — plus the communication records
   ``Notice``, ``Complaint`` and ``FrontDeskEntry``. Each carries a
   ``TODO(placeholder):`` / ``TODO(integration):`` comment describing the
   real backend module it will be replaced by and which other app it must
   be connected to (the chain-owner dashboard in ``school_owner`` already
   aggregates per-school numbers and expects these shapes).

Security note: the principal only ever sees the ONE school attached to
their account (``SAAS_admin.SchoolUser``, role ``principal``). Every view
must resolve data through ``School_Admin.utils.current_school`` — never
query a School by a raw id from the request.
"""
from django.contrib.auth.models import User
from django.db import models

from SAAS_admin.models import School


class StaffMember(models.Model):
    """PLACEHOLDER — TODO(placeholder): replace with the real HR / Staff
    module. Mirroring is LIVE: creates/status toggles are pushed into
    ``school_owner.StaffMember`` by ``school_owner.services`` so the owner
    dashboard's staff counts / transfers keep working; when the real HR
    module lands only the FK targets change."""

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="school_staff"
    )
    full_name = models.CharField(max_length=150)
    designation = models.CharField(max_length=100, blank=True, default="")
    department = models.CharField(max_length=100, blank=True, default="")
    phone = models.CharField(max_length=30, blank=True, default="")
    email = models.CharField(max_length=254, blank=True, default="")
    join_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["full_name"]

    def __str__(self):
        return f"{self.full_name} ({self.designation}) @ {self.school.name}"

    def as_dict(self):
        from django.utils import timezone

        return {
            "id": self.pk,
            "full_name": self.full_name,
            "designation": self.designation or "\u2014",
            "department": self.department or "\u2014",
            "phone": self.phone or "\u2014",
            "email": self.email or "\u2014",
            "join_date": self.join_date.isoformat() if self.join_date else None,
            "is_active": self.is_active,
            "created_at": timezone.localtime(self.created_at).strftime(
                "%b %d, %Y"
            ),
        }


class ClassSection(models.Model):
    """PLACEHOLDER — TODO(placeholder): replace with the real Timetable /
    Sections module. TODO(integration): when the real module lands, link
    each section to a ``school_owner.Classroom`` so the owner dashboard's
    free-seat metric reads live capacity instead of a snapshot."""

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="sections"
    )
    grade = models.CharField(max_length=50)
    section = models.CharField(max_length=10, default="A")
    capacity = models.PositiveIntegerField(default=35)
    class_teacher = models.ForeignKey(
        StaffMember, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="class_sections",
    )

    class Meta:
        ordering = ["grade", "section"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "grade", "section"],
                name="unique_class_section_per_school",
            )
        ]

    def __str__(self):
        return f"{self.school.name} \u00b7 {self.grade}-{self.section}"

    @property
    def label(self):
        return f"{self.grade}-{self.section}"

    def as_dict(self):
        return {
            "id": self.pk,
            "grade": self.grade,
            "section": self.section,
            "label": self.label,
            "capacity": self.capacity,
            "class_teacher": (
                self.class_teacher.full_name if self.class_teacher_id else None
            ),
        }


class Student(models.Model):
    """PLACEHOLDER — TODO(placeholder): replace with the real Student
    Information module (core model: profiles, documents, guardian contacts).
    ``school_owner.Student`` is the owner-dashboard mirror of this row and
    the sync is LIVE (create/status changes push through
    ``school_owner.services.mirror_student_to_owner``; the chain
    aggregations can be pointed at this model when the real module lands).
    Note: a single student can live in exactly one section here;
    the owner dashboard's cross-branch transfers will move this FK."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        LEFT = "left", "Left school"
        GRADUATED = "graduated", "Graduated"

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="school_students"
    )
    class_section = models.ForeignKey(
        ClassSection, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="students",
    )
    admission_no = models.CharField(max_length=40)
    full_name = models.CharField(max_length=150)
    guardian_name = models.CharField(max_length=150, blank=True, default="")
    guardian_phone = models.CharField(max_length=30, blank=True, default="")
    # Monthly tuition amount used to auto-generate invoices on admission.
    # TODO(placeholder): replace with per-FeeHead assignment when the real
    # fee module links students to FeeHeads instead of a flat number.
    monthly_fee = models.DecimalField(
        max_digits=10, decimal_places=2, default=0
    )
    admission_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.ACTIVE
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["full_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "admission_no"],
                name="unique_admission_no_per_school",
            )
        ]

    def __str__(self):
        return f"{self.admission_no} \u00b7 {self.full_name} @ {self.school.name}"

    def as_dict(self):
        from django.utils import timezone

        return {
            "id": self.pk,
            "class_section_id": self.class_section_id,
            "class_section": (
                self.class_section.label if self.class_section_id else "\u2014"
            ),
            "admission_no": self.admission_no,
            "full_name": self.full_name,
            "guardian_name": self.guardian_name or "\u2014",
            "guardian_phone": self.guardian_phone or "\u2014",
            "monthly_fee": float(self.monthly_fee),
            "admission_date": (
                self.admission_date.isoformat() if self.admission_date else None
            ),
            "status": self.status,
            "status_display": self.get_status_display(),
            "created_at": timezone.localtime(self.created_at).strftime(
                "%b %d, %Y"
            ),
        }


class AdmissionApplication(models.Model):
    """A parent's admission request awaiting the principal's decision.

    Approving an application creates the ``Student`` record (see
    ``views.admission_decide``) and their first fee invoice.

    TODO(integration): the owner dashboard's "pending approvals" badge and
    the future parent portal both hang off this model — keep the Status
    values in sync with any external intake form."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        WAITLISTED = "waitlisted", "Waitlisted"

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="admission_applications"
    )
    applicant_name = models.CharField(max_length=150)
    guardian_name = models.CharField(max_length=150, blank=True, default="")
    guardian_phone = models.CharField(max_length=30, blank=True, default="")
    class_section = models.ForeignKey(
        ClassSection, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="admission_applications",
    )
    note = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PENDING
    )
    decision_note = models.CharField(max_length=300, blank=True, default="")
    decided_by = models.CharField(max_length=120, blank=True, default="")
    decided_at = models.DateTimeField(null=True, blank=True)
    created_student = models.ForeignKey(
        Student, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="source_applications",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.get_status_display()}] {self.applicant_name} @ {self.school.name}"

    def as_dict(self):
        from django.utils import timezone

        return {
            "id": self.pk,
            "applicant_name": self.applicant_name,
            "guardian_name": self.guardian_name or "\u2014",
            "guardian_phone": self.guardian_phone or "\u2014",
            "class_section_id": self.class_section_id,
            "class_section": (
                self.class_section.label if self.class_section_id else "\u2014"
            ),
            "note": self.note,
            "status": self.status,
            "decision_note": self.decision_note,
            "decided_by": self.decided_by or "\u2014",
            "decided_at": (
                self.decided_at.strftime("%b %d, %Y %H:%M") if self.decided_at else None
            ),
            "created_student_id": self.created_student_id,
            "created_at": timezone.localtime(self.created_at).strftime("%b %d, %Y"),
        }


class LeaveRequest(models.Model):
    """A staff leave request awaiting the principal's decision.

    TODO(integration): the future teacher/staff app will submit these from
    the staff side; today the principal records them manually. The owner
    dashboard's approval feed may later roll these up per branch."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="leave_requests"
    )
    staff = models.ForeignKey(
        StaffMember, on_delete=models.CASCADE, related_name="leave_requests"
    )
    from_date = models.DateField()
    to_date = models.DateField()
    reason = models.CharField(max_length=300, blank=True, default="")
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    decision_note = models.CharField(max_length=300, blank=True, default="")
    decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.get_status_display()}] leave: {self.staff.full_name}"

    def as_dict(self):
        from django.utils import timezone

        return {
            "id": self.pk,
            "staff_id": self.staff_id,
            "staff_name": self.staff.full_name,
            "from_date": self.from_date.isoformat(),
            "to_date": self.to_date.isoformat(),
            "reason": self.reason or "\u2014",
            "status": self.status,
            "decision_note": self.decision_note,
            "decided_at": (
                self.decided_at.strftime("%b %d, %Y") if self.decided_at else None
            ),
            "created_at": timezone.localtime(self.created_at).strftime("%b %d, %Y"),
        }


class ExpenseRequest(models.Model):
    """A school expense the principal approves (or escalates to the owner).

    Escalation is LIVE: approving an expense submits a ``budget``
    ``school_owner.ApprovalRequest`` for the group owner (standalone
    schools — no chain — simply settle locally)."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="expense_requests"
    )
    title = models.CharField(max_length=200)
    details = models.TextField(blank=True, default="")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    requested_by = models.CharField(max_length=120, blank=True, default="")
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    decision_note = models.CharField(max_length=300, blank=True, default="")
    decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.get_status_display()}] {self.title} @ {self.school.name}"

    def as_dict(self):
        from django.utils import timezone

        return {
            "id": self.pk,
            "title": self.title,
            "details": self.details,
            "amount": float(self.amount),
            "requested_by": self.requested_by or "\u2014",
            "status": self.status,
            "decision_note": self.decision_note,
            "decided_at": (
                self.decided_at.strftime("%b %d, %Y") if self.decided_at else None
            ),
            "created_at": timezone.localtime(self.created_at).strftime("%b %d, %Y"),
        }


class FeeHead(models.Model):
    """Fee structure setup: one row per chargeable head (tuition, admission,
    transport, exam fee, ...), optionally scoped to a class section.

    TODO(integration): the real fees module will generate invoices from
    these heads on a schedule; today invoices are created from a student's
    ``monthly_fee`` or from a head chosen by the principal."""

    class Frequency(models.TextChoices):
        MONTHLY = "monthly", "Monthly"
        ONE_TIME = "one_time", "One time"
        ANNUAL = "annual", "Annual"

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="fee_heads"
    )
    name = models.CharField(max_length=120)
    class_section = models.ForeignKey(
        ClassSection, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="fee_heads",
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    frequency = models.CharField(
        max_length=10, choices=Frequency.choices, default=Frequency.MONTHLY
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.get_frequency_display()}) @ {self.school.name}"

    def as_dict(self):
        from django.utils import timezone

        return {
            "id": self.pk,
            "name": self.name,
            "class_section_id": self.class_section_id,
            "class_section": (
                self.class_section.label if self.class_section_id else "All classes"
            ),
            "amount": float(self.amount),
            "frequency": self.frequency,
            "frequency_display": self.get_frequency_display(),
            "is_active": self.is_active,
            "created_at": timezone.localtime(self.created_at).strftime("%b %d, %Y"),
        }


class StudentFeeInvoice(models.Model):
    """A fee invoice issued to one student for one billing period.

    The defaulter list = UNPAID/PARTIAL invoices past their due date.

    TODO(placeholder): the period label uses the same ``%B %Y`` format as
    ``school_owner.FeeInvoice`` so monthly statements line up. When the
    real fees module lands, point ``school_owner.metrics.fee_metrics`` at
    this model (or sync both) and keep the period format stable."""

    class Status(models.TextChoices):
        UNPAID = "unpaid", "Unpaid"
        PARTIAL = "partial", "Partially paid"
        PAID = "paid", "Paid"

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="fee_invoices"
    )
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="fee_invoices"
    )
    fee_head = models.ForeignKey(
        FeeHead, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="invoices",
    )
    period = models.CharField(max_length=20)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    due_date = models.DateField()
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.UNPAID
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-due_date", "student__full_name"]

    def __str__(self):
        return f"{self.period} invoice for {self.student.full_name}"

    @property
    def paid_amount(self):
        return sum(float(p.amount) for p in self.payments.all())

    def as_dict(self):
        from django.utils import timezone

        return {
            "id": self.pk,
            "student_id": self.student_id,
            "student_name": self.student.full_name,
            "class_section": (
                self.student.class_section.label
                if self.student.class_section_id else "\u2014"
            ),
            "fee_head": self.fee_head.name if self.fee_head_id else "Tuition",
            "period": self.period,
            "amount": float(self.amount),
            "paid_amount": self.paid_amount,
            "due_date": self.due_date.isoformat(),
            "status": self.status,
            "status_display": self.get_status_display(),
            "created_at": timezone.localtime(self.created_at).strftime("%b %d, %Y"),
        }


class FeePayment(models.Model):
    """A payment received against an invoice (full or partial).

    Recording a payment updates the invoice status automatically (see
    ``views.invoice_pay``). The "fee collected today / this month" KPI on
    the home screen aggregates this model."""

    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        BANK = "bank", "Bank transfer"
        ONLINE = "online", "Online"
        CHEQUE = "cheque", "Cheque"

    invoice = models.ForeignKey(
        StudentFeeInvoice, on_delete=models.CASCADE, related_name="payments"
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    paid_on = models.DateField()
    method = models.CharField(
        max_length=10, choices=Method.choices, default=Method.CASH
    )
    received_by = models.CharField(max_length=120, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-paid_on"]

    def __str__(self):
        return f"{self.amount} on {self.paid_on} ({self.get_method_display()})"

    def as_dict(self):
        return {
            "id": self.pk,
            "invoice_id": self.invoice_id,
            "student_name": self.invoice.student.full_name,
            "amount": float(self.amount),
            "paid_on": self.paid_on.isoformat(),
            "method": self.method,
            "method_display": self.get_method_display(),
            "received_by": self.received_by or "\u2014",
        }


class AttendanceSnapshot(models.Model):
    """Daily attendance totals for one class section.

    TODO(placeholder): replace with the real Attendance module (per-student
    marks + excused/late states). TODO(integration): keep the school/date
    shape compatible with ``school_owner.AttendanceSnapshot`` so the owner
    dashboard's attendance % reads from here without a rewrite; the class
    breakdown is what powers the school-side "by class/section" reports."""

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="attendance_records"
    )
    class_section = models.ForeignKey(
        ClassSection, on_delete=models.CASCADE, null=True, blank=True,
        related_name="attendance_records",
    )
    date = models.DateField()
    present = models.PositiveIntegerField(default=0)
    absent = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "class_section", "date"],
                name="unique_attendance_per_section_day",
            )
        ]

    def __str__(self):
        section = self.class_section.label if self.class_section_id else "All"
        return f"{self.school.name} \u00b7 {section} \u00b7 {self.date}"

    def as_dict(self):
        return {
            "id": self.pk,
            "class_section_id": self.class_section_id,
            "class_section": (
                self.class_section.label if self.class_section_id else "All"
            ),
            "date": self.date.isoformat(),
            "present": self.present,
            "absent": self.absent,
        }


class ExamRecord(models.Model):
    """An exam — either upcoming (average not yet recorded) or held.

    Powers the "upcoming exams" snapshot card and the academic report.
    TODO(placeholder): replace with the real Exams module (marks per
    student, subject paper level). TODO(integration): roll published rows
    into ``school_owner.ExamSummary`` (school + class label + average_pct)
    so the owner dashboard's exam metric keeps working."""

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="exam_records"
    )
    class_section = models.ForeignKey(
        ClassSection, on_delete=models.CASCADE, null=True, blank=True,
        related_name="exam_records",
    )
    exam_name = models.CharField(max_length=150)
    subject = models.CharField(max_length=100, blank=True, default="")
    exam_date = models.DateField()
    average_pct = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["-exam_date"]

    def __str__(self):
        return f"{self.exam_name} \u00b7 {self.subject} @ {self.school.name}"

    def as_dict(self):
        return {
            "id": self.pk,
            "class_section_id": self.class_section_id,
            "class_section": (
                self.class_section.label if self.class_section_id else "All"
            ),
            "exam_name": self.exam_name,
            "subject": self.subject or "\u2014",
            "exam_date": self.exam_date.isoformat(),
            "average_pct": self.average_pct,
            "is_upcoming": self.average_pct is None,
        }


class Notice(models.Model):
    """A circular sent to staff, students, or parents.

    TODO(integration): delivery is in-app only for now. When the teacher,
    student and parent portals land, their notification inboxes should
    read from this model filtered by ``audience`` (or fan-out rows should
    be created there on save via a post_save hook)."""

    class Audience(models.TextChoices):
        STAFF = "staff", "Staff"
        STUDENTS = "students", "Students"
        PARENTS = "parents", "Parents"
        ALL = "all", "Everyone"

    class Priority(models.TextChoices):
        INFO = "info", "Info"
        IMPORTANT = "important", "Important"
        URGENT = "urgent", "Urgent"

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="notices"
    )
    title = models.CharField(max_length=200)
    body = models.TextField()
    audience = models.CharField(
        max_length=10, choices=Audience.choices, default=Audience.ALL
    )
    priority = models.CharField(
        max_length=10, choices=Priority.choices, default=Priority.INFO
    )
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="school_notices",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.get_audience_display()}) @ {self.school.name}"

    def as_dict(self):
        from django.utils import timezone

        return {
            "id": self.pk,
            "title": self.title,
            "body": self.body,
            "audience": self.audience,
            "audience_display": self.get_audience_display(),
            "priority": self.priority,
            "author": (
                self.created_by.get_username() if self.created_by_id else "\u2014"
            ),
            "created_at": timezone.localtime(self.created_at).strftime(
                "%b %d, %Y %H:%M"
            ),
        }


class Complaint(models.Model):
    """A complaint logged at the front desk (walk-in, phone, online, letter).

    TODO(integration): the future parent portal / SMS gateway will create
    rows here directly; the ``source`` field already distinguishes intake
    channels. The operator console's ``SupportTicket`` is a *platform*
    ticket — keep them separate."""

    class Source(models.TextChoices):
        WALK_IN = "walk_in", "Walk-in"
        PHONE = "phone", "Phone"
        ONLINE = "online", "Online"
        LETTER = "letter", "Letter"

    class Category(models.TextChoices):
        ACADEMIC = "academic", "Academic"
        TRANSPORT = "transport", "Transport"
        FACILITIES = "facilities", "Facilities"
        FEES = "fees", "Fees"
        REQUEST = "request", "Request"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        IN_PROGRESS = "in_progress", "In progress"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="complaints"
    )
    complainant_name = models.CharField(max_length=150)
    contact = models.CharField(max_length=120, blank=True, default="")
    source = models.CharField(
        max_length=10, choices=Source.choices, default=Source.WALK_IN
    )
    category = models.CharField(
        max_length=12, choices=Category.choices, default=Category.OTHER
    )
    subject = models.CharField(max_length=200)
    details = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.OPEN
    )
    assigned_to = models.CharField(max_length=120, blank=True, default="")
    resolution_note = models.TextField(blank=True, default="")
    resolved_at = models.DateTimeField(null=True, blank=True)
    logged_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-logged_at"]

    def __str__(self):
        return f"[{self.get_status_display()}] {self.subject} @ {self.school.name}"

    def as_dict(self):
        from django.utils import timezone

        return {
            "id": self.pk,
            "complainant_name": self.complainant_name,
            "contact": self.contact or "\u2014",
            "source": self.source,
            "source_display": self.get_source_display(),
            "category": self.category,
            "category_display": self.get_category_display(),
            "subject": self.subject,
            "details": self.details,
            "status": self.status,
            "assigned_to": self.assigned_to or "\u2014",
            "resolution_note": self.resolution_note,
            "resolved_at": (
                self.resolved_at.strftime("%b %d, %Y %H:%M") if self.resolved_at else None
            ),
            "logged_at": timezone.localtime(self.logged_at).strftime("%b %d, %Y %H:%M"),
        }


class FrontDeskEntry(models.Model):
    """Front-desk activity log: visitors, enquiries, calls, deliveries.

    TODO(placeholder): replace with the real visitor-management module
    (badges, check-out times). TODO(integration): complaints escalated by
    the front desk become ``Complaint`` rows; this log keeps the timeline."""

    class EntryType(models.TextChoices):
        VISITOR = "visitor", "Visitor"
        ENQUIRY = "enquiry", "Enquiry"
        PHONE_CALL = "phone_call", "Phone call"
        DELIVERY = "delivery", "Delivery"
        OTHER = "other", "Other"

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="front_desk_entries"
    )
    entry_type = models.CharField(
        max_length=12, choices=EntryType.choices, default=EntryType.VISITOR
    )
    person = models.CharField(max_length=150)
    summary = models.CharField(max_length=300)
    handled_by = models.CharField(max_length=120, blank=True, default="")
    follow_up_needed = models.BooleanField(default=False)
    occurred_at = models.DateTimeField()

    class Meta:
        ordering = ["-occurred_at"]

    def __str__(self):
        return f"{self.get_entry_type_display()}: {self.person} @ {self.school.name}"

    def as_dict(self):
        from django.utils import timezone

        return {
            "id": self.pk,
            "entry_type": self.entry_type,
            "entry_type_display": self.get_entry_type_display(),
            "person": self.person,
            "summary": self.summary,
            "handled_by": self.handled_by or "\u2014",
            "follow_up_needed": self.follow_up_needed,
            "occurred_at": timezone.localtime(self.occurred_at).strftime(
                "%b %d, %Y %H:%M"
            ),
        }
