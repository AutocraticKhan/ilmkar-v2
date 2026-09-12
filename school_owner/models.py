"""Models for the Chain / Group Owner dashboard.

Two kinds of models live here:

1. ``Chain`` — the permanent multi-tenancy link between an owner account and
   the schools they own. This stays; everything else hangs off it.
2. ``Classroom`` + the mirror rows ``Student`` / ``StaffMember`` — light
   chain-side copies of ``School_Admin`` rows kept in sync by
   ``school_owner.services`` (admissions/status changes push updates). They
   power the transfers page and cross-branch moves only.
3. ``FeeInvoice`` / ``AttendanceSnapshot`` / ``ExamSummary`` — LEGACY
   placeholder metric tables: the dashboard no longer reads them (the
   metrics in ``school_owner.metrics`` read the real ``School_Admin``
   models directly). They are kept only for admin/history until removed.

Security note: the owner only ever sees schools attached to their own chain.
Every view must resolve data through ``chain.schools`` — never query a
School by raw id without confirming it belongs to the owner's chain.
"""
from django.contrib.auth.models import User
from django.db import models

from SAAS_admin.models import School


class Chain(models.Model):
    """A group of schools owned by a single owner account.

    The owner is a regular Django ``User`` — NOT a superuser (they cannot
    reach the operator console) and NOT a ``SchoolUser`` (they are not a
    member of any single school). They sign in at ``/`` and are redirected
    to their chain dashboard at ``/chain/``.

    Nullable owner: chains are now created with just a name; the superuser
    picks an existing account as the owner afterwards (Users / Chains pages).

    TODO(later): the platform currently assumes one User owns exactly one
    chain (OneToOne). If an owner ever runs two separate groups, relax this
    to a ForeignKey/ManyToMany and move the role checks accordingly.
    """

    name = models.CharField(max_length=200)
    owner = models.OneToOneField(
        User, on_delete=models.CASCADE, null=True, blank=True,
        related_name="owned_chain",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        if self.owner_id is None:
            return f"{self.name} (no owner yet)"
        return f"{self.name} (owner: {self.owner.get_username()})"

    @property
    def branches(self):
        return self.schools.all()

    def as_dict(self):
        return {
            "id": self.pk,
            "name": self.name,
            "owner_id": self.owner_id,
            "owner_username": self.owner.get_username() if self.owner_id else None,
            "owner_email": (self.owner.email or "\u2014") if self.owner_id else "\u2014",
            "school_count": self.schools.count(),
            "school_ids": [s.pk for s in self.schools.all()],
            "created_at": self.created_at.date().isoformat(),
        }


# ---------------------------------------------------------------------------
# PLACEHOLDER metric models (school-side data the chain dashboard aggregates)
# ---------------------------------------------------------------------------


class Classroom(models.Model):
    """PLACEHOLDER — TODO(placeholder): replace with the real Timetable /
    Sections module. Only name + capacity are needed today to compute the
    "free classroom seats" comparison metric."""

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="chain_classrooms"
    )
    name = models.CharField(max_length=120)
    capacity = models.PositiveIntegerField(default=30)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.school.name} \u00b7 {self.name} ({self.capacity})"


class Student(models.Model):
    """PLACEHOLDER — TODO(placeholder): replace with the real Student
    Information module (core module #1 in the architecture plan). It keeps
    only what the chain dashboard needs: branch, classroom, name, status and
    the monthly fee used by the placeholder fee invoices."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="chain_students"
    )
    classroom = models.ForeignKey(
        Classroom, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="students",
    )
    full_name = models.CharField(max_length=200)
    admission_no = models.CharField(max_length=60, blank=True, default="")
    monthly_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.ACTIVE
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["full_name"]

    def __str__(self):
        return f"{self.full_name} @ {self.school.name}"

    def as_dict(self):
        return {
            "id": self.pk,
            "school_id": self.school_id,
            "school_name": self.school.name,
            "classroom_id": self.classroom_id,
            "classroom_name": self.classroom.name if self.classroom else "\u2014",
            "full_name": self.full_name,
            "admission_no": self.admission_no or "\u2014",
            "status": self.status,
        }


class StaffMember(models.Model):
    """PLACEHOLDER — TODO(placeholder): replace with the real HR & Staff
    Records module. Only branch + name + designation are shown today
    (staff count per branch, transfer between branches)."""

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="chain_staff"
    )
    full_name = models.CharField(max_length=200)
    designation = models.CharField(max_length=120, blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["full_name"]

    def __str__(self):
        return f"{self.full_name} @ {self.school.name}"

    def as_dict(self):
        return {
            "id": self.pk,
            "school_id": self.school_id,
            "school_name": self.school.name,
            "full_name": self.full_name,
            "designation": self.designation or "\u2014",
            "is_active": self.is_active,
        }


class FeeInvoice(models.Model):
    """PLACEHOLDER — TODO(placeholder): replace with the real Fees & Billing
    module (fee heads, structures, discounts, instalments, online payments).
    Today this is a flat per-student invoice row used to compute collection
    rate, outstanding and "collects fees late" metrics per branch."""

    class Status(models.TextChoices):
        UNPAID = "unpaid", "Unpaid"
        PAID = "paid", "Paid"

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="chain_fee_invoices"
    )
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="invoices"
    )
    period = models.CharField(max_length=30)  # e.g. "September 2026"
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    due_date = models.DateField()
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.UNPAID
    )
    paid_at = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-due_date"]

    def __str__(self):
        return (
            f"{self.student.full_name} \u00b7 {self.period} \u00b7 "
            f"{self.get_status_display()}"
        )

    @property
    def is_overdue(self):
        """Unpaid with the due date passed — feeds the 'late collection' view."""
        import datetime

        return (
            self.status == self.Status.UNPAID
            and self.due_date < datetime.date.today()
        )


class AttendanceSnapshot(models.Model):
    """PLACEHOLDER — TODO(placeholder): replace with the real Attendance
    module (per-student daily/subject marking). The chain dashboard only
    needs a branch-level present/absent count per day for the attendance %
    metric and its 30-day trend."""

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="chain_attendance"
    )
    date = models.DateField()
    present = models.PositiveIntegerField(default=0)
    absent = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "date"], name="unique_chain_attendance_date"
            )
        ]

    def __str__(self):
        return f"{self.school.name} \u00b7 {self.date}"

    @property
    def pct(self):
        total = self.present + self.absent
        return round(self.present / total * 100, 1) if total else None


class ExamSummary(models.Model):
    """PLACEHOLDER — TODO(placeholder): replace with the real Examinations &
    Results module (datesheets, marks entry, report cards). Today a single
    branch-level average percentage per term feeds the scorecard."""

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="chain_exams"
    )
    term = models.CharField(max_length=60)  # e.g. "Mid Term 2026"
    average_pct = models.DecimalField(max_digits=5, decimal_places=2)
    recorded_at = models.DateField()

    class Meta:
        ordering = ["-recorded_at"]

    def __str__(self):
        return f"{self.school.name} \u00b7 {self.term} \u00b7 {self.average_pct}%"


# ---------------------------------------------------------------------------
# Chain feature models (real functionality of this dashboard)
# ---------------------------------------------------------------------------


class GroupPolicy(models.Model):
    """A group-wide policy (fee structure, leave policy, \u2026) applied to
    every branch at once. A branch can override it with a
    ``GroupPolicyOverride`` without touching the group default.

    TODO(later): once the real Fees/HR modules exist, ``default_value`` /
    ``override.value`` (free text) should become structured FKs to those
    module objects instead of human-readable text.
    """

    class Category(models.TextChoices):
        FEE_STRUCTURE = "fee_structure", "Fee structure"
        LEAVE_POLICY = "leave_policy", "Leave policy"
        OTHER = "other", "Other"

    chain = models.ForeignKey(
        Chain, on_delete=models.CASCADE, related_name="policies"
    )
    name = models.CharField(max_length=200)
    category = models.CharField(
        max_length=20, choices=Category.choices, default=Category.OTHER
    )
    default_value = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="group_policies_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.chain.name})"

    def as_dict(self):
        return {
            "id": self.pk,
            "name": self.name,
            "category": self.category,
            "category_display": self.get_category_display(),
            "default_value": self.default_value,
            "created_at": self.created_at.date().isoformat(),
            "overrides": [
                o.as_dict() for o in self.overrides.select_related("school")
            ],
        }


class GroupPolicyOverride(models.Model):
    """A per-branch exception to a group-wide policy."""

    policy = models.ForeignKey(
        GroupPolicy, on_delete=models.CASCADE, related_name="overrides"
    )
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="policy_overrides"
    )
    value = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["school__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["policy", "school"], name="unique_policy_branch_override"
            )
        ]

    def __str__(self):
        return f"{self.policy.name} override @ {self.school.name}"

    def as_dict(self):
        return {
            "id": self.pk,
            "policy_id": self.policy_id,
            "school_id": self.school_id,
            "school_name": self.school.name,
            "value": self.value,
            "created_at": self.created_at.date().isoformat(),
        }


class JobPosting(models.Model):
    """Central hiring: post a job once for the group; the placed branch is
    recorded when it is filled.

    TODO(later): applicants/interviews will belong to the HR module; add a
    ``JobApplication`` model there and FK it to this posting.
    """

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        FILLED = "filled", "Filled"

    chain = models.ForeignKey(
        Chain, on_delete=models.CASCADE, related_name="job_postings"
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    # null = "any branch that needs them"
    preferred_branch = models.ForeignKey(
        School, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="job_postings",
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    filled_branch = models.ForeignKey(
        School, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="jobs_filled",
    )
    filled_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="job_postings_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.chain.name})"

    def as_dict(self):
        from django.utils import timezone

        return {
            "id": self.pk,
            "title": self.title,
            "description": self.description,
            "preferred_branch_id": self.preferred_branch_id,
            "preferred_branch": (
                self.preferred_branch.name if self.preferred_branch else None
            ),
            "status": self.status,
            "filled_branch_id": self.filled_branch_id,
            "filled_branch": self.filled_branch.name if self.filled_branch else None,
            "filled_at": self.filled_at.strftime("%b %d, %Y") if self.filled_at else None,
            "created_at": timezone.localtime(self.created_at).strftime("%b %d, %Y"),
        }


class BranchAnnouncement(models.Model):
    """A notice from the group owner to all branches (``school`` null) or a
    single branch."""

    chain = models.ForeignKey(
        Chain, on_delete=models.CASCADE, related_name="branch_announcements"
    )
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, null=True, blank=True,
        related_name="branch_announcements",
    )
    title = models.CharField(max_length=200)
    body = models.TextField()
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="branch_announcements_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.chain.name})"

    def as_dict(self):
        from django.utils import timezone

        return {
            "id": self.pk,
            "school_id": self.school_id,
            "scope": "branch" if self.school_id else "all",
            "school_name": self.school.name if self.school_id else None,
            "title": self.title,
            "body": self.body,
            "created_at": timezone.localtime(self.created_at).strftime(
                "%b %d, %Y %H:%M"
            ),
        }


class ApprovalRequest(models.Model):
    """Approval workflow: a branch principal requests a budget / new hire /
    other exception; the group owner approves or rejects centrally.

    ``requested_by`` is still free text (School_Admin submissions fill it
    with the principal's display name via ``school_owner.services``).
    TODO(placeholder): swap it for a FK to the requesting ``SchoolUser``
    once a migration window is acceptable. The decide flow itself is final.
    """

    class Type(models.TextChoices):
        BUDGET = "budget", "Budget"
        NEW_HIRE = "new_hire", "New hire"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    chain = models.ForeignKey(
        Chain, on_delete=models.CASCADE, related_name="approval_requests"
    )
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="approval_requests"
    )
    request_type = models.CharField(
        max_length=20, choices=Type.choices, default=Type.OTHER
    )
    title = models.CharField(max_length=200)
    details = models.TextField(blank=True, default="")
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    requested_by = models.CharField(max_length=120, blank=True, default="")
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
            "school_id": self.school_id,
            "school_name": self.school.name,
            "request_type": self.request_type,
            "request_type_display": self.get_request_type_display(),
            "title": self.title,
            "details": self.details,
            "amount": float(self.amount) if self.amount is not None else None,
            "status": self.status,
            "requested_by": self.requested_by or "\u2014",
            "decision_note": self.decision_note,
            "decided_at": (
                self.decided_at.strftime("%b %d, %Y") if self.decided_at else None
            ),
            "created_at": timezone.localtime(self.created_at).strftime("%b %d, %Y"),
        }


class TransferLog(models.Model):
    """Audit trail for students / staff moved between branches of the group.

    The move itself updates the ``school`` FK on the placeholder
    ``Student`` / ``StaffMember`` row without re-entering any data.
    """

    class PersonType(models.TextChoices):
        STUDENT = "student", "Student"
        STAFF = "staff", "Staff member"

    chain = models.ForeignKey(
        Chain, on_delete=models.CASCADE, related_name="transfers"
    )
    person_type = models.CharField(max_length=10, choices=PersonType.choices)
    person_display = models.CharField(max_length=200)
    from_school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="transfers_out"
    )
    to_school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="transfers_in"
    )
    note = models.CharField(max_length=300, blank=True, default="")
    moved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="chain_transfers_moved",
    )
    moved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-moved_at"]

    def __str__(self):
        return (
            f"{self.person_display}: {self.from_school.name} \u2192 "
            f"{self.to_school.name}"
        )

    def as_dict(self):
        from django.utils import timezone

        return {
            "id": self.pk,
            "person_type": self.person_type,
            "person_type_display": self.get_person_type_display(),
            "person_display": self.person_display,
            "from_school_name": self.from_school.name,
            "to_school_name": self.to_school.name,
            "note": self.note or "\u2014",
            "moved_at": timezone.localtime(self.moved_at).strftime("%b %d, %Y %H:%M"),
        }





