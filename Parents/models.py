"""Models for the Parent / Family dashboard.

``Parents`` is the family-facing cockpit for ONE guardian linked to ONE or
MORE children at ONE school: a "today at school" digest per child, attendance
& alerts, fee status + online payment, results, homework / assignments,
notices and a simple message thread per child/subject to that child's teacher.

Conventions followed here (matching Student / Teachers / School_Admin):
- every model is scoped to a ``SAAS_admin.School`` so the tenant boundary
  is enforced in views via ``Parents.utils.current_school``;
- the signed-in user links to their children via ``ParentProfile`` +
  ``ParentChildLink`` (mirroring ``Student.StudentProfile``). A child can be
  reachable from several guardians (mother + father), and one login can see
  several children;
- the read-only surfaces (digest, attendance, results, homework, fees,
  notices) read the existing ``Teachers`` / ``School_Admin`` models so the
  school stays the single source of truth — nothing is duplicated here. The
  only things a parent creates are ``Teachers.TeacherMessage`` rows
  (``sender_type=parent``) and, when the school allows it, online fee
  payments against ``School_Admin.StudentFeeInvoice``.

Security note: ``Teachers.TeacherNote`` rows are for TEACHERS/ADMIN ONLY and
must never be serialised onto any parent-facing surface — the digest's "note
from teacher" comes from the class diary and replied parent messages, never
from TeacherNote.
"""
from django.contrib.auth.models import User
from django.db import models

from SAAS_admin.models import School
from School_Admin.models import Student


class ParentPortalSetting(models.Model):
    """Per-school switches for what parents may do from their portal.

    TODO(integration): ``Student.PortalSetting`` carries the same
    ``allow_online_payment`` switch for the student portal — this row mirrors
    it for the parent portal (as that model's docstring suggests). If the
    settings ever grow, move both into a shared per-school settings model.
    """

    school = models.OneToOneField(
        School, on_delete=models.CASCADE, related_name="parent_portal_setting"
    )
    allow_online_payment = models.BooleanField(default=True)
    allow_messaging = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Parent portal settings @ {self.school.name}"


class ParentProfile(models.Model):
    """Links a platform ``User`` (a ``SchoolUser`` with role ``parent``)
    to their family at one school.

    ``guardian_name`` is a display snapshot used as the sender name on
    teacher messages. Children are linked explicitly through
    ``ParentChildLink`` (see ``Parents.utils.children_of`` for the fallback
    resolution used when links are missing).
    """

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="parent_profiles"
    )
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="parent_profile"
    )
    guardian_name = models.CharField(max_length=150, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["user__username"]

    def __str__(self):
        name = self.guardian_name or self.user.get_username()
        return f"{name} (parent profile @ {self.school.name})"


class ParentChildLink(models.Model):
    """One guardian ←→ child link.

    A parent may link several children (multiple children, one login) and a
    child may be linked from several parents (mother + father). ``is_primary``
    marks the default child the dashboard initially selects.
    """

    parent = models.ForeignKey(
        ParentProfile, on_delete=models.CASCADE, related_name="child_links"
    )
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="parent_links"
    )
    relationship = models.CharField(max_length=50, blank=True, default="Guardian")
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["student__full_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["parent", "student"], name="unique_parent_child_link"
            )
        ]

    def __str__(self):
        return f"{self.parent} → {self.student.full_name} ({self.relationship})"