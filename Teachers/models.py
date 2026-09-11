"""Models for the Teacher / Staff dashboard.

``Teachers`` is the day-to-day cockpit for ONE teacher at ONE school: a
fast attendance + marks flow, assignments, the class diary, leave,
payslips, lesson plans, messages and the teacher-only extras (private
student notes, auto-drafted report-card comments, a shared resource
library, the substitute finder and the early-warning analytics).

Conventions followed here (matching School_Admin / school_owner):
- every model is scoped to a ``SAAS_admin.School`` so the tenant boundary
  is enforced in views via ``Teachers.utils.current_school``;
- teacher-facing rows FK to the placeholder ``School_Admin`` models
  (``StaffMember``, ``ClassSection``, ``Student``, ``ExamRecord``);
- every placeholder carries a ``TODO(placeholder):`` comment describing
  the real backend module that will replace it and a ``TODO(integration):``
  comment naming the other dashboards it must stay in sync with.

Security note: ``TeacherNote`` rows are for TEACHERS/ADMIN ONLY and must
never be serialised onto any parent-facing surface — see the model
docstring and the views that read them.
"""
from django.contrib.auth.models import User
from django.db import models

from SAAS_admin.models import School
from School_Admin.models import ClassSection, ExamRecord, StaffMember, Student


class TeacherProfile(models.Model):
    """Links a platform ``User`` (a ``SchoolUser`` with role ``teacher``)
    to their HR record (``School_Admin.StaffMember``) and their subjects.

    TODO(integration): the long-term fix is a ``user`` FK on
    ``School_Admin.StaffMember`` itself — when that lands, migrate this
    link into it and keep ``Teachers.utils.current_staff_member`` as a thin
    wrapper. Until then this row is optional; resolution falls back to
    email / full-name matching (see utils.py).
    """

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="teacher_profiles"
    )
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="teacher_profile"
    )
    staff_member = models.OneToOneField(
        StaffMember, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="teacher_profile",
    )
    subjects = models.CharField(max_length=300, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["user__username"]

    def __str__(self):
        staff = (
            self.staff_member.full_name if self.staff_member_id
            else self.user.get_username()
        )
        return f"{staff} (teacher profile)"

    def as_dict(self):
        return {
            "id": self.pk,
            "school_id": self.school_id,
            "user_id": self.user_id,
            "username": self.user.get_username(),
            "staff_member_id": self.staff_member_id,
            "staff_name": self.staff_member.full_name if self.staff_member_id else None,
            "subjects": self.subjects,
        }


class TimetableSlot(models.Model):
    """One teaching period in the weekly timetable: a section, a subject
    and a teacher at a day + period number.

    Powers "today's classes at a glance" on the teacher home screen and the
    substitute-teacher finder (which needs to know who is busy in which
    period).

    TODO(placeholder): replace with the real Timetable module (room
    allocation, conflicts, breaks, assembly periods). TODO(integration):
    ``School_Admin.ClassSection`` stays the section source; the substitute
    finder in ``Teachers.metrics`` reads approved ``School_Admin.LeaveRequest``
    rows to know who is away — keep both shapes stable.
    """

    class Day(models.TextChoices):
        MON = "Mon", "Monday"
        TUE = "Tue", "Tuesday"
        WED = "Wed", "Wednesday"
        THU = "Thu", "Thursday"
        FRI = "Fri", "Friday"
        SAT = "Sat", "Saturday"
        SUN = "Sun", "Sunday"

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="timetable_slots"
    )
    class_section = models.ForeignKey(
        ClassSection, on_delete=models.CASCADE, related_name="timetable_slots"
    )
    subject = models.CharField(max_length=100)
    teacher = models.ForeignKey(
        StaffMember, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="timetable_slots",
    )
    day = models.CharField(max_length=3, choices=Day.choices)
    period = models.PositiveSmallIntegerField()  # 1..8 within the day
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)

    class Meta:
        ordering = ["day", "period", "class_section__grade", "class_section__section"]
        constraints = [
            models.UniqueConstraint(
                fields=["class_section", "day", "period"],
                name="unique_slot_per_section_day_period",
            )
        ]

    def __str__(self):
        return (
            f"{self.class_section.label} · {self.subject} · "
            f"{self.get_day_display()} P{self.period}"
        )

    @property
    def label(self):
        return f"P{self.period} · {self.subject} · {self.class_section.label}"

    def as_dict(self):
        return {
            "id": self.pk,
            "class_section_id": self.class_section_id,
            "class_section": self.class_section.label,
            "subject": self.subject,
            "teacher": self.teacher.full_name if self.teacher_id else "—",
            "day": self.day,
            "day_display": self.get_day_display(),
            "period": self.period,
            "start_time": self.start_time.strftime("%H:%M") if self.start_time else "—",
            "end_time": self.end_time.strftime("%H:%M") if self.end_time else "—",
        }


class StudentAttendance(models.Model):
    """The per-student daily attendance mark a teacher taps in one go.

    TODO(integration): saving marks upserts the aggregate
    ``School_Admin.AttendanceSnapshot`` for the section (see
    ``Teachers.metrics.sync_attendance_snapshot``) so the principal's home
    screen stays live, and the chain dashboard keeps reading the same
    snapshot shape. When the real Attendance module lands, keep that sync
    (or point the snapshot views at this model directly).
    """

    class Mark(models.TextChoices):
        PRESENT = "present", "Present"
        ABSENT = "absent", "Absent"
        LATE = "late", "Late"
        EXCUSED = "excused", "Excused"

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="student_attendance"
    )
    class_section = models.ForeignKey(
        ClassSection, on_delete=models.CASCADE, related_name="student_attendance"
    )
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="attendance_records"
    )
    date = models.DateField()
    mark = models.CharField(
        max_length=10, choices=Mark.choices, default=Mark.PRESENT
    )
    marked_by = models.ForeignKey(
        StaffMember, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="attendance_marked",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "student__full_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "date"], name="unique_attendance_per_student_day"
            )
        ]

    def __str__(self):
        return f"{self.student.full_name} · {self.date} · {self.mark}"

    def as_dict(self):
        return {
            "id": self.pk,
            "student_id": self.student_id,
            "student_name": self.student.full_name,
            "class_section": self.class_section.label,
            "date": self.date.isoformat(),
            "mark": self.mark,
            "mark_display": self.get_mark_display(),
        }


class GradeEntry(models.Model):
    """Marks for ONE student on ONE exam — the cell of the simple marks
    grid teachers fill in.

    TODO(integration): saving entries recomputes
    ``School_Admin.ExamRecord.average_pct`` (see
    ``Teachers.metrics.update_exam_average``) so the principal's dashboard
    and reports stay live. When the real Exams module splits papers per
    subject/term, keep the exam FK and add the paper link.
    """

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="grade_entries"
    )
    exam = models.ForeignKey(
        ExamRecord, on_delete=models.CASCADE, related_name="grade_entries"
    )
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="grade_entries"
    )
    marks_obtained = models.DecimalField(max_digits=6, decimal_places=2)
    total_marks = models.PositiveIntegerField(default=100)
    remarks = models.CharField(max_length=200, blank=True, default="")
    entered_by = models.ForeignKey(
        StaffMember, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="grade_entries_entered",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["exam", "student__full_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["exam", "student"], name="unique_grade_per_exam_student"
            )
        ]

    def __str__(self):
        return f"{self.student.full_name} · {self.exam.exam_name}: {self.marks_obtained}"

    @property
    def percentage(self):
        try:
            return round(float(self.marks_obtained) / self.total_marks * 100, 1)
        except (ZeroDivisionError, TypeError):
            return None

    def as_dict(self):
        return {
            "id": self.pk,
            "exam_id": self.exam_id,
            "student_id": self.student_id,
            "student_name": self.student.full_name,
            "marks_obtained": float(self.marks_obtained),
            "total_marks": self.total_marks,
            "percentage": self.percentage,
            "remarks": self.remarks,
        }


class Assignment(models.Model):
    """Homework / assignment a teacher posts for a class section.

    TODO(placeholder): attachments and rich descriptions land with the
    content module. TODO(integration): when the student/parent portals
    launch they read this model to see homework; submissions arrive as
    ``AssignmentSubmission`` rows created from those portals (today the
    teacher records them manually).
    """

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="assignments"
    )
    posted_by = models.ForeignKey(
        StaffMember, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="assignments_posted",
    )
    class_section = models.ForeignKey(
        ClassSection, on_delete=models.CASCADE, related_name="assignments"
    )
    subject = models.CharField(max_length=100)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    assigned_on = models.DateField()
    due_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-due_date", "-created_at"]

    def __str__(self):
        return f"{self.title} ({self.class_section.label} · {self.subject})"

    def as_dict(self):
        return {
            "id": self.pk,
            "class_section_id": self.class_section_id,
            "class_section": self.class_section.label,
            "subject": self.subject,
            "title": self.title,
            "description": self.description,
            "assigned_on": self.assigned_on.isoformat(),
            "due_date": self.due_date.isoformat(),
            "posted_by": self.posted_by.full_name if self.posted_by_id else "—",
        }


class AssignmentSubmission(models.Model):
    """One student's submission state for an assignment: who has submitted,
    when, and (optionally) a grade + feedback.

    TODO(integration): when the student/parent portals launch they flip
    these rows to ``submitted`` themselves; until then the teacher records
    receipt manually. ``School_Admin`` reports can later aggregate these.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUBMITTED = "submitted", "Submitted"
        GRADED = "graded", "Graded"

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="assignment_submissions"
    )
    assignment = models.ForeignKey(
        Assignment, on_delete=models.CASCADE, related_name="submissions"
    )
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="assignment_submissions"
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    grade = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )
    feedback = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["assignment", "student__full_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["assignment", "student"],
                name="unique_submission_per_assignment_student",
            )
        ]

    def __str__(self):
        return f"{self.student.full_name} · {self.assignment.title} ({self.status})"

    def as_dict(self):
        from django.utils import timezone

        return {
            "id": self.pk,
            "student_id": self.student_id,
            "student_name": self.student.full_name,
            "status": self.status,
            "submitted_at": (
                timezone.localtime(self.submitted_at).strftime("%b %d, %Y %H:%M")
                if self.submitted_at else None
            ),
            "grade": float(self.grade) if self.grade is not None else None,
            "feedback": self.feedback,
        }


class ClassDiary(models.Model):
    """What was taught in a section + subject on a given day — the entry
    parents and the principal read to follow the class.

    TODO(integration): when the parent portal lands it reads this model
    (read-only) for their child's section; the principal dashboard can
    surface a "today in classes" feed from the same rows.
    """

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="class_diary"
    )
    class_section = models.ForeignKey(
        ClassSection, on_delete=models.CASCADE, related_name="diary_entries"
    )
    subject = models.CharField(max_length=100)
    date = models.DateField()
    taught = models.TextField()  # what was covered
    homework = models.TextField(blank=True, default="")
    recorded_by = models.ForeignKey(
        StaffMember, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="diary_entries",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["class_section", "subject", "date"],
                name="unique_diary_per_section_subject_day",
            )
        ]

    def __str__(self):
        return f"{self.class_section.label} · {self.subject} · {self.date}"

    def as_dict(self):
        return {
            "id": self.pk,
            "class_section": self.class_section.label,
            "subject": self.subject,
            "date": self.date.isoformat(),
            "taught": self.taught,
            "homework": self.homework,
            "recorded_by": (
                self.recorded_by.full_name if self.recorded_by_id else "—"
            ),
        }


class LessonPlan(models.Model):
    """Curriculum tracker: a topic planned for a section + subject in a
    week/term, and how far it has progressed.

    TODO(integration): when the curriculum/syllabus module lands, FK the
    topic to it; the owner dashboard can later roll completion % per branch.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="lesson_plans"
    )
    teacher = models.ForeignKey(
        StaffMember, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="lesson_plans",
    )
    class_section = models.ForeignKey(
        ClassSection, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="lesson_plans",
    )
    subject = models.CharField(max_length=100)
    week_label = models.CharField(max_length=60, default="Week 1")  # e.g. "Week 4 / Term 1"
    topic = models.CharField(max_length=200)
    objectives = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.DRAFT
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.topic} ({self.subject} · {self.week_label})"

    def as_dict(self):
        return {
            "id": self.pk,
            "class_section": (
                self.class_section.label if self.class_section_id else "—"
            ),
            "subject": self.subject,
            "week_label": self.week_label,
            "topic": self.topic,
            "objectives": self.objectives,
            "status": self.status,
            "status_display": self.get_status_display(),
            "teacher": self.teacher.full_name if self.teacher_id else "—",
        }


class TeacherNote(models.Model):
    """PRIVATE per-student notes: behaviour, strengths, concerns.

    SECURITY: visible to TEACHERS and the school ADMIN ONLY — never to
    parents. There is deliberately NO ``as_dict`` parent-safe serialization
    here and the views refuse to expose these rows to non-staff roles;
    TODO(integration): when the parent portal lands, DO NOT add these rows
    to any parent-facing queryset — they exist to prepare teachers for
    parent meetings. If a parent-facing summary is ever needed, generate a
    sanitized ``ReportCardComment`` instead.
    """

    class Category(models.TextChoices):
        BEHAVIOR = "behavior", "Behaviour"
        STRENGTH = "strength", "Strength"
        CONCERN = "concern", "Concern"
        GENERAL = "general", "General"

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="teacher_notes"
    )
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="teacher_notes"
    )
    author = models.ForeignKey(
        StaffMember, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="teacher_notes_written",
    )
    category = models.CharField(
        max_length=10, choices=Category.choices, default=Category.GENERAL
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_category_display()} note on {self.student.full_name}"

    def as_dict(self):
        """STAFF-ONLY serialization — never use on parent-facing surfaces
        (see class docstring)."""
        from django.utils import timezone

        return {
            "id": self.pk,
            "student_id": self.student_id,
            "student_name": self.student.full_name,
            "author": self.author.full_name if self.author_id else "—",
            "category": self.category,
            "category_display": self.get_category_display(),
            "body": self.body,
            "created_at": timezone.localtime(self.created_at).strftime(
                "%b %d, %Y %H:%M"
            ),
        }


class ReportCardComment(models.Model):
    """An auto-DRAFTED report-card comment (from marks + teacher notes)
    that the teacher edits and marks final.

    TODO(integration): when the report-card module lands, FK it to the
    generated report row; for now ``term`` is a free label matching the
    report cycle. Once final, this text is what parents see — the private
    ``TeacherNote`` rows that seeded it stay teacher-only.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        FINAL = "final", "Final"

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="report_card_comments"
    )
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="report_card_comments"
    )
    term = models.CharField(max_length=60)  # e.g. "Term 1 2026"
    draft = models.TextField()
    final = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.DRAFT
    )
    notes_used = models.PositiveSmallIntegerField(default=0)
    overall_pct = models.FloatField(null=True, blank=True)
    created_by = models.ForeignKey(
        StaffMember, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="report_comments",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "term"], name="unique_comment_per_student_term"
            )
        ]

    def __str__(self):
        return f"{self.student.full_name} · {self.term} ({self.status})"

    def as_dict(self):
        return {
            "id": self.pk,
            "student_id": self.student_id,
            "student_name": self.student.full_name,
            "class_section": (
                self.student.class_section.label
                if self.student.class_section_id else "—"
            ),
            "term": self.term,
            "draft": self.draft,
            "final": self.final,
            "status": self.status,
            "notes_used": self.notes_used,
            "overall_pct": self.overall_pct,
            "updated_at": self.updated_at.strftime("%b %d, %Y %H:%M"),
        }


class SharedResource(models.Model):
    """A lesson material shared between teachers of the same subject at
    the school (worksheets, slides, question banks, past papers) so
    materials get reused, not rebuilt every term.

    TODO(placeholder): ``link`` is a URL/paste field for now — file uploads
    (``FileField`` + storage backend) land with the content/file module.
    TODO(integration): the resource library is scoped to the school;
    chain-level sharing across branches is a natural next step (FK the
    chain when the owner console exposes it).
    """

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="shared_resources"
    )
    subject = models.CharField(max_length=100)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    link = models.URLField(blank=True, default="")
    # TODO(placeholder): file = models.FileField(...) — will fix later.
    shared_by = models.ForeignKey(
        StaffMember, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="resources_shared",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["subject", "-created_at"]

    def __str__(self):
        return f"{self.title} ({self.subject})"

    def as_dict(self):
        return {
            "id": self.pk,
            "subject": self.subject,
            "title": self.title,
            "description": self.description,
            "link": self.link,
            "shared_by": self.shared_by.full_name if self.shared_by_id else "—",
            "created_at": self.created_at.strftime("%b %d, %Y"),
        }


class TeacherMessage(models.Model):
    """A message in the teacher's one inbox — from the school admin or a
    parent — plus the teacher's reply.

    TODO(placeholder): admin/parents currently send messages from the
    Django admin console (see TeacherMessageAdmin). TODO(integration):
    when the parent portal lands, parents compose here directly; when the
    principal app grows a compose UI, it creates rows with
    ``sender_type=ADMIN``. ``School_Admin.Notice`` rows with audience
    staff/all are surfaced in the inbox as read-only notices.
    """

    class SenderType(models.TextChoices):
        ADMIN = "admin", "School admin"
        PARENT = "parent", "Parent"
        TEACHER = "teacher", "Teacher"

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="teacher_messages"
    )
    staff = models.ForeignKey(
        StaffMember, on_delete=models.CASCADE, related_name="inbox_messages"
    )
    # TODO(integration): the student this is about, when parents message
    # about a specific child — kept nullable until the parent portal links.
    about_student = models.ForeignKey(
        Student, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="teacher_messages",
    )
    sender_type = models.CharField(
        max_length=10, choices=SenderType.choices, default=SenderType.ADMIN
    )
    sender_name = models.CharField(max_length=150)
    subject = models.CharField(max_length=200)
    body = models.TextField()
    is_read = models.BooleanField(default=False)
    reply = models.TextField(blank=True, default="")
    replied_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["is_read", "-created_at"]

    def __str__(self):
        return f"{self.get_sender_type_display()} → {self.staff.full_name}: {self.subject}"

    def as_dict(self):
        from django.utils import timezone

        return {
            "id": self.pk,
            "staff_id": self.staff_id,
            "sender_type": self.sender_type,
            "sender_type_display": self.get_sender_type_display(),
            "sender_name": self.sender_name,
            "about_student": (
                self.about_student.full_name if self.about_student_id else None
            ),
            "subject": self.subject,
            "body": self.body,
            "is_read": self.is_read,
            "reply": self.reply,
            "replied_at": (
                timezone.localtime(self.replied_at).strftime("%b %d, %Y %H:%M")
                if self.replied_at else None
            ),
            "created_at": timezone.localtime(self.created_at).strftime(
                "%b %d, %Y %H:%M"
            ),
        }


class Payslip(models.Model):
    """A teacher's payslip / salary-history row (one per staff per period).

    TODO(placeholder): replace with the real Payroll module (salary
    structure, allowances, deductions, PF/tax, payslip PDF, disbursement
    records). Until payroll lands, rows are created from the Django admin
    console and the teacher sees a read-only salary history here.
    TODO(integration): the school admin's expenses / the owner dashboard's
    payroll roll-up should read (or mirror) these rows — keep the period
    format ``"%B %Y"`` identical to the fee invoices.
    """

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="payslips"
    )
    staff = models.ForeignKey(
        StaffMember, on_delete=models.CASCADE, related_name="payslips"
    )
    period = models.CharField(max_length=30)  # e.g. "September 2026"
    basic = models.DecimalField(max_digits=10, decimal_places=2)
    allowances = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    deductions = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    paid_on = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["staff", "period"], name="unique_payslip_per_staff_period"
            )
        ]

    def __str__(self):
        return f"{self.staff.full_name} · {self.period}"

    @property
    def net_pay(self):
        return self.basic + self.allowances - self.deductions

    def as_dict(self):
        return {
            "id": self.pk,
            "staff_id": self.staff_id,
            "staff_name": self.staff.full_name,
            "period": self.period,
            "basic": float(self.basic),
            "allowances": float(self.allowances),
            "deductions": float(self.deductions),
            "net_pay": float(self.net_pay),
            "paid_on": self.paid_on.isoformat() if self.paid_on else None,
        }


class SubstituteAssignment(models.Model):
    """A substitute teacher arranged for one slot on one date while the
    regular teacher is away.

    Powers the substitute-finder page (suggestions come from
    ``metrics.substitute_candidates``) and keeps the timetable honest: the
    assigned teacher is marked busy for that period on that date.

    TODO(integration): the principal's approvals page approves the leave
    (``School_Admin.LeaveRequest``) — an approved leave covering a date is
    what surfaces slots here. Notify the substitute (SMS/push) when the
    notification module lands.
    """

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="substitute_assignments"
    )
    slot = models.ForeignKey(
        TimetableSlot, on_delete=models.CASCADE, related_name="substitute_assignments"
    )
    date = models.DateField()
    original_teacher = models.ForeignKey(
        StaffMember, on_delete=models.CASCADE, related_name="absence_assignments"
    )
    substitute = models.ForeignKey(
        StaffMember, on_delete=models.CASCADE, related_name="substitute_assignments"
    )
    arranged_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="substitute_assignments_arranged",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "slot__period"]
        constraints = [
            models.UniqueConstraint(
                fields=["slot", "date"], name="unique_substitute_per_slot_day"
            )
        ]

    def __str__(self):
        return (
            f"{self.substitute.full_name} covers {self.slot.label} on {self.date}"
        )

    def as_dict(self):
        return {
            "id": self.pk,
            "slot_id": self.slot_id,
            "slot": self.slot.label,
            "date": self.date.isoformat(),
            "original_teacher": self.original_teacher.full_name,
            "substitute_id": self.substitute_id,
            "substitute": self.substitute.full_name,
            "arranged_by": (
                self.arranged_by.get_username() if self.arranged_by_id else "—"
            ),
        }







