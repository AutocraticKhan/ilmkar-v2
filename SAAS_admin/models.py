from django.contrib.auth.models import User
from django.db import models


class School(models.Model):
    """A school registered on the platform."""

    class Package(models.TextChoices):
        STARTER = "Starter", "Starter"
        GROWTH = "Growth", "Growth"
        ENTERPRISE = "Enterprise", "Enterprise"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        TRIAL = "trial", "Trial"
        SUSPENDED = "suspended", "Suspended"

    PACKAGE_MRR = {
        Package.STARTER: 99,
        Package.GROWTH: 499,
        Package.ENTERPRISE: 1899,
    }

    name = models.CharField(max_length=200)
    city = models.CharField(max_length=200)
    # The account that owns this school — one account can own many schools,
    # and a school can have several owners (the console warns before a
    # second owner is added). The owner dashboard shows exactly these
    # schools (plus anything in their chain/group). Assigned by the
    # superuser from the Users / Chains pages.
    owners = models.ManyToManyField(
        User, blank=True, related_name="owned_schools",
    )
    # Optional chain/group membership: several schools owned by one owner
    # account (managed from the operator console, used by school_owner).
    chain = models.ForeignKey(
        "school_owner.Chain", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="schools",
    )
    package = models.CharField(
        max_length=20, choices=Package.choices, default=Package.STARTER
    )
    students = models.PositiveIntegerField(default=0)
    renewal = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.TRIAL
    )
    contact = models.CharField(max_length=120, blank=True, default="\u2014")
    email = models.CharField(max_length=254, blank=True, default="\u2014")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def mrr(self):
        return self.PACKAGE_MRR.get(self.package, 0)

    def user_count(self):
        """Number of user accounts linked to this school.

        Uses a ``_user_count`` annotation when the queryset was annotated with
        one, otherwise falls back to a per-instance query.
        """
        annotated = getattr(self, "_user_count", None)
        return annotated if annotated is not None else self.memberships.count()

    def as_dict(self):
        owners = list(self.owners.all())
        return {
            "id": self.pk,
            "name": self.name,
            "city": self.city,
            "owner_ids": [u.pk for u in owners],
            "owner_usernames": [u.get_username() for u in owners],
            # First owner kept for compatibility with older UI text.
            "owner_id": owners[0].pk if owners else None,
            "owner_username": owners[0].get_username() if owners else None,
            "chain_id": self.chain_id,
            "chain_name": self.chain.name if self.chain_id else None,
            "package": self.package,
            "students": self.students,
            "mrr": self.mrr,
            "renewal": self.renewal.isoformat() if self.renewal else None,
            "status": self.status,
            "contact": self.contact or "\u2014",
            "email": self.email or "\u2014",
            "users": self.user_count(),
        }


class SchoolUser(models.Model):
    """A user account belonging to a school, with a platform role.

    Deleting a school cascades to its memberships, and deleting the underlying
    ``User`` cascades here as well (each user belongs to exactly one school).
    """

    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        PRINCIPAL = "principal", "School Admin / Principal"
        TEACHER = "teacher", "Teacher"
        STUDENT = "student", "Student"
        HR = "hr", "HR"
        FRONT_DESK = "front_desk", "Front Desk / Admissions"
        ACCOUNTANT = "accountant", "Accountant"
        PARENT = "parent", "Parent/Family"

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="memberships"
    )
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="school_membership"
    )
    role = models.CharField(max_length=20, choices=Role.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["user__username"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "user"], name="unique_school_user"
            )
        ]

    def __str__(self):
        return (
            f"{self.user.get_username()} @ {self.school.name} "
            f"({self.get_role_display()})"
        )

    def as_dict(self):
        return {
            "id": self.pk,
            "user_id": self.user_id,
            "username": self.user.get_username(),
            "full_name": self.user.get_full_name(),
            "email": self.user.email or "\u2014",
            "role": self.role,
            "role_display": self.get_role_display(),
            "created_at": self.created_at.date().isoformat(),
        }


class Invoice(models.Model):
    """A billing period invoice issued to a school."""

    class Status(models.TextChoices):
        PAID = "paid", "Paid"
        UNPAID = "unpaid", "Unpaid"
        OVERDUE = "overdue", "Overdue"

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="invoices"
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
        return f"{self.school.name} \u00b7 {self.period} \u00b7 {self.get_status_display()}"

    def as_dict(self):
        return {
            "id": self.pk,
            "school_id": self.school_id,
            "school_name": self.school.name,
            "period": self.period,
            "amount": float(self.amount),
            "due_date": self.due_date.isoformat(),
            "status": self.status,
            "paid_at": self.paid_at.isoformat() if self.paid_at else None,
        }


class UsageSnapshot(models.Model):
    """Periodic usage metrics captured for a school.

    Computed from live data by ``SAAS_admin.services.refresh_snapshots``
    (management command ``refresh_usage_snapshots``; also refreshed on the
    operator console's Usage page load). Logins = member logins that day,
    active_students = ACTIVE student count, storage_mb = 0 until the
    content module adds file uploads.
    """

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="usage_snapshots"
    )
    date = models.DateField()
    logins = models.PositiveIntegerField(default=0)
    storage_mb = models.PositiveIntegerField(default=0)
    active_students = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["date"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "date"], name="unique_school_usage_date"
            )
        ]

    def __str__(self):
        return f"{self.school.name} \u00b7 {self.date}"

class SupportTicket(models.Model):
    """A support request opened by a school."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        PENDING = "pending", "Pending"
        CLOSED = "closed", "Closed"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        NORMAL = "normal", "Normal"
        HIGH = "high", "High"

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="tickets"
    )
    subject = models.CharField(max_length=200)
    body = models.TextField()
    requester = models.CharField(max_length=120)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    priority = models.CharField(
        max_length=10, choices=Priority.choices, default=Priority.NORMAL
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"[{self.get_status_display()}] {self.subject}"

    def as_dict(self):
        return {
            "id": self.pk,
            "school_id": self.school_id,
            "school_name": self.school.name,
            "subject": self.subject,
            "body": self.body,
            "requester": self.requester,
            "status": self.status,
            "priority": self.priority,
            "created_at": self.created_at.date().isoformat(),
            "updated_at": self.updated_at.date().isoformat(),
            "replies": self.replies.count(),
        }


class SupportReply(models.Model):
    """A message on a support ticket (from the school or the operator)."""

    ticket = models.ForeignKey(
        SupportTicket, on_delete=models.CASCADE, related_name="replies"
    )
    is_staff = models.BooleanField(default=False)
    author = models.CharField(max_length=120)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Reply by {self.author} on {self.ticket.subject}"

    def as_dict(self):
        return {
            "id": self.pk,
            "is_staff": self.is_staff,
            "author": self.author,
            "body": self.body,
            "created_at": self.created_at.strftime("%b %d, %Y %H:%M"),
        }

class Announcement(models.Model):
    """A system-wide update posted by the platform operator."""

    class Severity(models.TextChoices):
        INFO = "info", "Info"
        UPDATE = "update", "Update"
        CRITICAL = "critical", "Critical"

    title = models.CharField(max_length=200)
    body = models.TextField()
    severity = models.CharField(
        max_length=10, choices=Severity.choices, default=Severity.INFO
    )
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="announcements"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def as_dict(self):
        return {
            "id": self.pk,
            "title": self.title,
            "body": self.body,
            "severity": self.severity,
            "author": self.created_by.get_username() if self.created_by else "\u2014",
            "created_at": self.created_at.date().isoformat(),
        }


class ImpersonationLog(models.Model):
    """Audit trail for operator 'log in as school' support sessions."""

    operator = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="impersonations_given"
    )
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="impersonations"
    )
    # SET_NULL so the audit trail survives the impersonated account being
    # deleted; user_display keeps a readable snapshot either way.
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="impersonations_of"
    )
    user_display = models.CharField(max_length=120, blank=True, default="")
    note = models.CharField(max_length=200, blank=True, default="")
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return (
            f"{self.operator.get_username()} as {self.user_display} "
            f"@ {self.school.name}"
        )

    def as_dict(self):
        return {
            "id": self.pk,
            "operator": self.operator.get_username(),
            "school_name": self.school.name,
            "user_display": self.user_display or "\u2014",
            "note": self.note or "\u2014",
            "started_at": self.started_at.strftime("%b %d, %Y %H:%M"),
            "ended_at": (
                self.ended_at.strftime("%b %d, %Y %H:%M") if self.ended_at else None
            ),
            "active": self.ended_at is None,
        }
