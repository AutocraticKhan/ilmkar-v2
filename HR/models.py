"""Models for the HR / People dashboard.

``HR`` is the dedicated people cockpit for ONE school: the staff
directory with contracts, attendance + leave approvals, recruitment
(job postings -> applicants -> interviews), onboarding checklists, the
payroll INPUT bridge (attendance/leave feed payroll automatically),
performance appraisals, staff document expiry alerts, and training /
professional-development tracking.

Conventions followed (matching Accountant / School_Admin / Teachers):
- every model is scoped to a ``SAAS_admin.School`` so the tenant boundary
  is enforced in views via ``HR.utils.current_school``;
- staff-side rows FK to the placeholder ``School_Admin.StaffMember`` —
  HR never duplicates the directory, it enriches it;
- leave approvals REUSE ``School_Admin.LeaveRequest`` (single source of
  truth — HR and the principal decide on the same rows);
- the payroll bridge writes into ``Accountant.PayrollItem`` / the
  matching ``PayrollPeriod`` (draft runs only — see ``HR.services``);
- ``AuditLog`` is APPEND-ONLY: no view ever edits or deletes a row,
  which keeps the HR action trail (approvals, hires, contract changes)
  tamper-evident like the finance one.

TODO(integration): when the real staff module replaces the
``School_Admin.StaffMember`` placeholder, only the FK target changes —
period labels stay ``"%B %Y"`` so payroll rows line up.
"""
from django.db import models

from SAAS_admin.models import School
from School_Admin.models import StaffMember


class StaffContract(models.Model):
    """An employment contract for one staff member.

    The staff directory page pairs each ``StaffMember`` with their
    LATEST contract (type, dates, monthly salary). ``monthly_salary``
    is the payroll-bridge default: the per-day deduction for unpaid
    absence is derived from it (salary / working days of the month).
    """

    class Kind(models.TextChoices):
        PERMANENT = "permanent", "Permanent"
        PROBATION = "probation", "Probation"
        CONTRACT = "contract", "Fixed-term contract"
        PART_TIME = "part_time", "Part-time"
        VISITING = "visiting", "Visiting"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ENDED = "ended", "Ended"

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="staff_contracts"
    )
    staff = models.ForeignKey(
        StaffMember, on_delete=models.CASCADE, related_name="contracts"
    )
    kind = models.CharField(
        max_length=12, choices=Kind.choices, default=Kind.PERMANENT
    )
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    monthly_salary = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.ACTIVE
    )
    notes = models.CharField(max_length=300, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.staff.full_name} — {self.get_kind_display()} ({self.status})"

    @property
    def is_expired(self):
        """Contract end date already passed (expiry-alert feed)."""
        import datetime

        return self.end_date is not None and self.end_date < datetime.date.today()

    def as_dict(self):
        return {
            "id": self.pk,
            "staff_id": self.staff_id,
            "staff_name": self.staff.full_name,
            "kind": self.kind,
            "kind_display": self.get_kind_display(),
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "monthly_salary": float(self.monthly_salary),
            "status": self.status,
            "notes": self.notes or "—",
        }


class StaffDocument(models.Model):
    """A staff document with an expiry HR must watch (certifications,
    contracts, CNIC, degrees...).

    Expiry status drives the dashboard + sidebar alert: ``ok`` (no
    expiry or > 60 days out), ``expiring`` (<= 60 days), ``expired``.
    """

    class Kind(models.TextChoices):
        CERTIFICATION = "certification", "Certification"
        CONTRACT = "contract", "Contract"
        CNIC = "cnic", "CNIC / ID"
        DEGREE = "degree", "Degree / transcript"
        OTHER = "other", "Other"

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="staff_documents"
    )
    staff = models.ForeignKey(
        StaffMember, on_delete=models.CASCADE, related_name="hr_documents"
    )
    kind = models.CharField(
        max_length=15, choices=Kind.choices, default=Kind.CERTIFICATION
    )
    title = models.CharField(max_length=200)
    number = models.CharField(max_length=100, blank=True, default="")
    issued_on = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    file_url = models.CharField(max_length=300, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["expiry_date", "staff__full_name"]

    def __str__(self):
        return f"{self.title} — {self.staff.full_name}"

    @property
    def expiry_status(self):
        """ok / expiring (<= 60 days) / expired / none (no expiry date)."""
        import datetime

        if self.expiry_date is None:
            return "none"
        today = datetime.date.today()
        if self.expiry_date < today:
            return "expired"
        if (self.expiry_date - today).days <= 60:
            return "expiring"
        return "ok"

    def as_dict(self):
        return {
            "id": self.pk,
            "staff_id": self.staff_id,
            "staff_name": self.staff.full_name,
            "kind": self.kind,
            "kind_display": self.get_kind_display(),
            "title": self.title,
            "number": self.number or "—",
            "issued_on": self.issued_on.isoformat() if self.issued_on else None,
            "expiry_date": self.expiry_date.isoformat() if self.expiry_date else None,
            "expiry_status": self.expiry_status,
            "file_url": self.file_url or "",
        }


class AttendanceRecord(models.Model):
    """One staff member's attendance for one day.

    Unique per (staff, date). Absent days marked ``unpaid`` feed the
    payroll bridge as a per-day deduction; paid leave is NOT deducted
    (approved paid leave keeps the salary whole).
    """

    class Status(models.TextChoices):
        PRESENT = "present", "Present"
        ABSENT = "absent", "Absent"
        LATE = "late", "Late"
        HALF_DAY = "half_day", "Half day"
        LEAVE = "leave", "On leave"

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="hr_attendance"
    )
    staff = models.ForeignKey(
        StaffMember, on_delete=models.CASCADE, related_name="attendance_records"
    )
    date = models.DateField()
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PRESENT
    )
    # Absent + unpaid -> deducted in payroll input; absent while paid
    # (e.g. arranged cover) -> no deduction.
    unpaid = models.BooleanField(default=False)
    note = models.CharField(max_length=200, blank=True, default="")
    marked_by = models.CharField(max_length=120, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "staff__full_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["staff", "date"], name="unique_attendance_per_staff_day"
            )
        ]

    def __str__(self):
        return f"{self.staff.full_name} — {self.date} ({self.get_status_display()})"

    def as_dict(self):
        return {
            "id": self.pk,
            "staff_id": self.staff_id,
            "staff_name": self.staff.full_name,
            "date": self.date.isoformat(),
            "status": self.status,
            "status_display": self.get_status_display(),
            "unpaid": self.unpaid,
            "note": self.note or "",
            "marked_by": self.marked_by or "—",
        }


class LeaveBalance(models.Model):
    """Per-staff, per-year leave entitlement ledger.

    ``used_days`` is incremented when HR approves an unpaid or paid
    leave (``School_Admin.LeaveRequest``); annual entitlement + carried
    forward come from school policy and are editable from HR.
    """

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="leave_balances"
    )
    staff = models.ForeignKey(
        StaffMember, on_delete=models.CASCADE, related_name="leave_balances"
    )
    year = models.PositiveIntegerField()
    entitled = models.DecimalField(max_digits=5, decimal_places=1, default=20)
    carried_over = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    used = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    unpaid_used = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-year", "staff__full_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["staff", "year"], name="unique_leave_balance_per_staff_year"
            )
        ]

    def __str__(self):
        return f"{self.staff.full_name} — {self.year} ({self.used}/{self.remaining})"

    @property
    def remaining(self):
        return self.entitled + self.carried_over - self.used

    def as_dict(self):
        return {
            "id": self.pk,
            "staff_id": self.staff_id,
            "staff_name": self.staff.full_name,
            "year": self.year,
            "entitled": float(self.entitled),
            "carried_over": float(self.carried_over),
            "used": float(self.used),
            "unpaid_used": float(self.unpaid_used),
            "remaining": float(self.remaining),
        }


class JobPosting(models.Model):
    """An open vacancy advertised by the school (recruitment funnel)."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"
        FILLED = "filled", "Filled"

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="hr_job_postings"
    )
    title = models.CharField(max_length=200)
    department = models.CharField(max_length=100, blank=True, default="")
    openings = models.PositiveIntegerField(default=1)
    description = models.TextField(blank=True, default="")
    posted_on = models.DateField()
    closes_on = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.OPEN
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-posted_on"]

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"

    def as_dict(self):
        return {
            "id": self.pk,
            "title": self.title,
            "department": self.department or "—",
            "openings": self.openings,
            "description": self.description or "",
            "posted_on": self.posted_on.isoformat(),
            "closes_on": self.closes_on.isoformat() if self.closes_on else None,
            "status": self.status,
            "applicants": self.applications.count(),
        }


class JobApplication(models.Model):
    """An applicant against a ``JobPosting`` — the recruitment funnel
    stage: new -> shortlisted -> interviewed -> offered -> hired (or
    rejected at any stage)."""

    class Stage(models.TextChoices):
        NEW = "new", "New"
        SHORTLISTED = "shortlisted", "Shortlisted"
        INTERVIEWED = "interviewed", "Interviewed"
        OFFERED = "offered", "Offer made"
        HIRED = "hired", "Hired"
        REJECTED = "rejected", "Rejected"

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="job_applications"
    )
    posting = models.ForeignKey(
        JobPosting, on_delete=models.CASCADE, related_name="applications"
    )
    candidate_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=30, blank=True, default="")
    email = models.CharField(max_length=254, blank=True, default="")
    experience = models.CharField(max_length=200, blank=True, default="")
    stage = models.CharField(
        max_length=12, choices=Stage.choices, default=Stage.NEW
    )
    note = models.CharField(max_length=300, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.candidate_name} — {self.posting.title} ({self.get_stage_display()})"

    def as_dict(self):
        return {
            "id": self.pk,
            "posting_id": self.posting_id,
            "posting_title": self.posting.title,
            "candidate_name": self.candidate_name,
            "phone": self.phone or "—",
            "email": self.email or "—",
            "experience": self.experience or "—",
            "stage": self.stage,
            "stage_display": self.get_stage_display(),
            "note": self.note or "",
            "interviews": [i.as_dict() for i in self.interviews.all()],
        }


class Interview(models.Model):
    """A scheduled interview for a ``JobApplication`` — when, with whom,
    and the outcome/score after it happens."""

    class Outcome(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        PASSED = "passed", "Passed"
        FAILED = "failed", "Failed"
        NO_SHOW = "no_show", "No show"

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="interviews"
    )
    application = models.ForeignKey(
        JobApplication, on_delete=models.CASCADE, related_name="interviews"
    )
    round_no = models.PositiveIntegerField(default=1)
    scheduled_on = models.DateField()
    scheduled_at = models.CharField(max_length=10, blank=True, default="")
    interviewer = models.CharField(max_length=150, blank=True, default="")
    score = models.PositiveIntegerField(null=True, blank=True)
    outcome = models.CharField(
        max_length=10, choices=Outcome.choices, default=Outcome.SCHEDULED
    )
    note = models.CharField(max_length=300, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["scheduled_on", "round_no"]

    def __str__(self):
        return (
            f"R{self.round_no} — {self.application.candidate_name} "
            f"on {self.scheduled_on} ({self.get_outcome_display()})"
        )

    def as_dict(self):
        return {
            "id": self.pk,
            "application_id": self.application_id,
            "candidate_name": self.application.candidate_name,
            "round_no": self.round_no,
            "scheduled_on": self.scheduled_on.isoformat(),
            "scheduled_at": self.scheduled_at or "",
            "interviewer": self.interviewer or "—",
            "score": self.score,
            "outcome": self.outcome,
            "outcome_display": self.get_outcome_display(),
            "note": self.note or "",
        }


class OnboardingChecklist(models.Model):
    """One onboarding task for one new hire.

    Starting a checklist (``HR.services.start_onboarding``) seeds the
    DEFAULT_TASKS template so every hire gets the same baseline which
    HR then adapts.
    """

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="onboarding_tasks"
    )
    staff = models.ForeignKey(
        StaffMember, on_delete=models.CASCADE, related_name="onboarding_tasks"
    )
    title = models.CharField(max_length=200)
    due_date = models.DateField(null=True, blank=True)
    is_done = models.BooleanField(default=False)
    done_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["is_done", "due_date", "created_at"]

    def __str__(self):
        return f"{'✓' if self.is_done else '□'} {self.title} — {self.staff.full_name}"

    def as_dict(self):
        from django.utils import timezone

        return {
            "id": self.pk,
            "staff_id": self.staff_id,
            "staff_name": self.staff.full_name,
            "title": self.title,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "is_done": self.is_done,
            "done_at": (
                timezone.localtime(self.done_at).strftime("%b %d, %Y")
                if self.done_at
                else None
            ),
        }


class Appraisal(models.Model):
    """A performance appraisal for one staff member for one cycle.

    ``scores`` is a small {criterion: 1-5} dict (json) plus the overall
    rating; draft -> finalized (frozen, ``finalized_by/at`` recorded).
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        FINALIZED = "finalized", "Finalized"

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="appraisals"
    )
    staff = models.ForeignKey(
        StaffMember, on_delete=models.CASCADE, related_name="appraisals"
    )
    period = models.CharField(max_length=30)  # e.g. "2025-2026"
    reviewer = models.CharField(max_length=150, blank=True, default="")
    # {criterion: score 1-5}; criteria fixed per school policy.
    scores = models.JSONField(default=dict, blank=True)
    rating = models.DecimalField(max_digits=3, decimal_places=1, default=0)
    strengths = models.TextField(blank=True, default="")
    improvements = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.DRAFT
    )
    finalized_by = models.CharField(max_length=120, blank=True, default="")
    finalized_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["staff", "period"], name="unique_appraisal_per_staff_period"
            )
        ]

    def __str__(self):
        return f"{self.staff.full_name} — {self.period} ({self.get_status_display()})"

    def as_dict(self):
        from django.utils import timezone

        return {
            "id": self.pk,
            "staff_id": self.staff_id,
            "staff_name": self.staff.full_name,
            "designation": self.staff.designation or "—",
            "period": self.period,
            "reviewer": self.reviewer or "—",
            "scores": self.scores or {},
            "rating": float(self.rating),
            "strengths": self.strengths or "",
            "improvements": self.improvements or "",
            "status": self.status,
            "finalized_by": self.finalized_by or "—",
            "created_at": timezone.localtime(self.created_at).strftime("%b %d, %Y"),
        }


class TrainingProgram(models.Model):
    """A training / professional-development program the school runs or
    sends staff to (workshop, certification course, conference...)."""

    class Kind(models.TextChoices):
        WORKSHOP = "workshop", "Workshop"
        COURSE = "course", "Course"
        CERTIFICATION = "certification", "Certification"
        CONFERENCE = "conference", "Conference"

    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        ONGOING = "ongoing", "Ongoing"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="training_programs"
    )
    title = models.CharField(max_length=200)
    kind = models.CharField(
        max_length=15, choices=Kind.choices, default=Kind.WORKSHOP
    )
    provider = models.CharField(max_length=150, blank=True, default="")
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    cost_per_head = models.DecimalField(
        max_digits=10, decimal_places=2, default=0
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PLANNED
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"

    def as_dict(self):
        return {
            "id": self.pk,
            "title": self.title,
            "kind": self.kind,
            "kind_display": self.get_kind_display(),
            "provider": self.provider or "—",
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "cost_per_head": float(self.cost_per_head),
            "status": self.status,
            "enrolled": self.enrollments.count(),
            "completed": self.enrollments.filter(
                status=TrainingEnrollment.Status.COMPLETED
            ).count(),
        }


class TrainingEnrollment(models.Model):
    """One staff member's participation in a ``TrainingProgram``."""

    class Status(models.TextChoices):
        ENROLLED = "enrolled", "Enrolled"
        COMPLETED = "completed", "Completed"
        DROPPED = "dropped", "Dropped"

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="training_enrollments"
    )
    program = models.ForeignKey(
        TrainingProgram, on_delete=models.CASCADE, related_name="enrollments"
    )
    staff = models.ForeignKey(
        StaffMember, on_delete=models.CASCADE, related_name="trainings"
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.ENROLLED
    )
    completed_on = models.DateField(null=True, blank=True)
    certificate_ref = models.CharField(max_length=100, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["program", "staff"], name="unique_enrollment_per_program_staff"
            )
        ]

    def __str__(self):
        return f"{self.staff.full_name} — {self.program.title} ({self.get_status_display()})"

    def as_dict(self):
        return {
            "id": self.pk,
            "program_id": self.program_id,
            "program_title": self.program.title,
            "program_kind_display": self.program.get_kind_display(),
            "staff_id": self.staff_id,
            "staff_name": self.staff.full_name,
            "status": self.status,
            "status_display": self.get_status_display(),
            "completed_on": (
                self.completed_on.isoformat() if self.completed_on else None
            ),
            "certificate_ref": self.certificate_ref or "—",
        }


class PayrollInput(models.Model):
    """HR's payroll INPUT row: one staff member's attendance/leave roll-up
    for one billing period, plus HR-side adjustments (bonus, advance).

    Not money-out — this feeds the accountant's ``PayrollPeriod`` via
    ``HR.services.feed_to_payroll`` (draft runs only). ``fed_to_payroll``
    flips once the rows land so the dashboard shows what's still due.
    """

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="payroll_inputs"
    )
    staff = models.ForeignKey(
        StaffMember, on_delete=models.CASCADE, related_name="payroll_inputs"
    )
    period = models.CharField(max_length=30)  # e.g. "September 2026"
    present_days = models.DecimalField(max_digits=4, decimal_places=1, default=0)
    absent_unpaid_days = models.DecimalField(max_digits=4, decimal_places=1, default=0)
    paid_leave_days = models.DecimalField(max_digits=4, decimal_places=1, default=0)
    late_marks = models.PositiveIntegerField(default=0)
    bonus = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    advance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    note = models.CharField(max_length=300, blank=True, default="")
    fed_to_payroll = models.BooleanField(default=False)
    fed_by = models.CharField(max_length=120, blank=True, default="")
    fed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "staff__full_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["staff", "period"], name="unique_payroll_input_per_staff_period"
            )
        ]

    def __str__(self):
        return f"{self.staff.full_name} — {self.period} (fed: {self.fed_to_payroll})"

    def as_dict(self):
        from django.utils import timezone

        return {
            "id": self.pk,
            "staff_id": self.staff_id,
            "staff_name": self.staff.full_name,
            "designation": self.staff.designation or "—",
            "period": self.period,
            "present_days": float(self.present_days),
            "absent_unpaid_days": float(self.absent_unpaid_days),
            "paid_leave_days": float(self.paid_leave_days),
            "late_marks": self.late_marks,
            "bonus": float(self.bonus),
            "advance": float(self.advance),
            "note": self.note or "",
            "fed_to_payroll": self.fed_to_payroll,
            "fed_by": self.fed_by or "—",
            "fed_at": (
                timezone.localtime(self.fed_at).strftime("%b %d, %Y %H:%M")
                if self.fed_at
                else None
            ),
        }


class AuditLog(models.Model):
    """APPEND-ONLY action trail for the HR cockpit.

    Every mutation (hire, contract, attendance, approval, payroll feed,
    appraisal...) writes a row here with the acting username. There are
    deliberately NO update or delete paths for audit rows in this app —
    same tamper-evident guarantee as the finance trail.
    """

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="hr_audit_logs"
    )
    actor = models.CharField(max_length=120)
    action = models.CharField(max_length=40)
    target = models.CharField(max_length=200)
    note = models.CharField(max_length=300, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.actor} — {self.action} — {self.target}"

    def as_dict(self):
        from django.utils import timezone

        return {
            "id": self.pk,
            "actor": self.actor,
            "action": self.action,
            "target": self.target,
            "note": self.note or "—",
            "created_at": timezone.localtime(self.created_at).strftime(
                "%b %d, %Y %H:%M"
            ),
        }

    @classmethod
    def record(cls, school, actor, action, target, note=""):
        """Single append point used by every mutating view."""
        return cls.objects.create(
            school=school, actor=actor, action=action, target=target, note=note
        )









