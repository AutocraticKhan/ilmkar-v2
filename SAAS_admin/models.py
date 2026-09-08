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
        return {
            "id": self.pk,
            "name": self.name,
            "city": self.city,
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
