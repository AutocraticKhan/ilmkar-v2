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
        }
