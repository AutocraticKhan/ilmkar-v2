"""Models for the Front Desk / Admissions dashboard.

``front_desk`` is the school's front-of-house cockpit for ONE school: the
admissions lead funnel (enquiries tracked till they enroll or drop off),
the visitor log (who came in, why, when they left), the complaint/request
register, gate-pass issuing (students leaving early, visitor passes), and
ID-card printing.

Conventions followed (matching HR / Accountant / School_Admin):
- every model is scoped to a ``SAAS_admin.School`` so the tenant boundary
  is enforced in views via ``front_desk.utils.current_school``;
- the complaint/request register REUSES ``School_Admin.Complaint`` (the
  placeholder was built for the front desk — single source of truth,
  shared with the principal's dashboard); a ``request`` category has been
  added to the shared ``Category`` choices so one register holds both;
- enquiries that turn into formal applications link to
  ``School_Admin.AdmissionApplication`` (the principal decides there) and,
  once enrolled, to ``School_Admin.Student`` — the funnel stays one row
  the whole way;
- the older ``School_Admin.FrontDeskEntry`` activity log remains the
  principal's brief timeline; this app owns the detailed records;
- ``AuditLog`` is APPEND-ONLY: no view ever edits or deletes a row, which
  keeps the front-desk action trail tamper-evident like the HR one.

TODO(integration): when the real student/staff modules replace the
``School_Admin.Student`` / ``School_Admin.StaffMember`` placeholders, only
the FK targets change — the ``as_dict`` shapes stay.
"""
from django.db import models
from django.utils import timezone

from SAAS_admin.models import School
from School_Admin.models import AdmissionApplication, StaffMember, Student


class AdmissionEnquiry(models.Model):
    """An admission lead — \"someone asked about admission\".

    The funnel is explicit: ``new -> contacted -> site_visit -> applied ->
    enrolled`` with ``dropped`` as the explicit lifecycle end (a lead that
    went cold / withdrew). ``applied`` links to the shared
    ``School_Admin.AdmissionApplication`` the principal decides on;
    ``enrolled`` links to the ``School_Admin.Student`` row created on
    admission. Until the principal approves, the lead lives here.
    """

    class Source(models.TextChoices):
        WALK_IN = "walk_in", "Walk-in"
        PHONE = "phone", "Phone"
        ONLINE = "online", "Online"
        REFERRAL = "referral", "Referral"
        OTHER = "other", "Other"

    class Stage(models.TextChoices):
        NEW = "new", "New"
        CONTACTED = "contacted", "Contacted"
        SITE_VISIT = "site_visit", "Site visit"
        APPLIED = "applied", "Applied"
        ENROLLED = "enrolled", "Enrolled"
        DROPPED = "dropped", "Dropped"

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="fd_enquiries"
    )
    applicant_name = models.CharField(max_length=150)
    guardian_name = models.CharField(max_length=150, blank=True, default="")
    guardian_phone = models.CharField(max_length=30, blank=True, default="")
    interested_grade = models.CharField(max_length=50, blank=True, default="")
    source = models.CharField(
        max_length=12, choices=Source.choices, default=Source.WALK_IN
    )
    stage = models.CharField(
        max_length=12, choices=Stage.choices, default=Stage.NEW
    )
    # Link to the official admission application when the lead applies
    # (single source of truth — the principal decides on that row).
    application = models.ForeignKey(
        AdmissionApplication, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="fd_enquiry",
    )
    # Link to the student row once admitted/enrolled.
    student = models.ForeignKey(
        Student, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="fd_enquiries",
    )
    follow_up_date = models.DateField(null=True, blank=True)
    follow_up_note = models.CharField(max_length=300, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    assigned_to = models.CharField(max_length=120, blank=True, default="")
    created_by = models.CharField(max_length=120, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.get_stage_display()}] {self.applicant_name} @ {self.school.name}"

    @property
    def is_open(self):
        """Still in the funnel (not enrolled, not dropped)."""
        return self.stage not in (
            self.Stage.ENROLLED, self.Stage.DROPPED
        )

    def as_dict(self):
        return {
            "id": self.pk,
            "applicant_name": self.applicant_name,
            "guardian_name": self.guardian_name or "—",
            "guardian_phone": self.guardian_phone or "—",
            "interested_grade": self.interested_grade or "—",
            "source": self.source,
            "stage": self.stage,
            "application_id": self.application_id,
            "application_status": (
                self.application.get_status_display()
                if self.application_id else None
            ),
            "student_id": self.student_id,
            "student_name": self.student.full_name if self.student_id else None,
            "follow_up_date": (
                self.follow_up_date.isoformat() if self.follow_up_date else None
            ),
            "follow_up_note": self.follow_up_note,
            "notes": self.notes,
            "assigned_to": self.assigned_to or "—",
            "created_by": self.created_by or "—",
            "created_at": timezone.localtime(self.created_at).strftime(
                "%b %d, %Y %H:%M"
            ),
            "updated_at": timezone.localtime(self.updated_at).strftime(
                "%b %d, %Y %H:%M"
            ),
        }
class VisitorLog(models.Model):
    """Visitor registry — who came in, why, when they left.

    ``entered_at`` is required (auto defaulted to now when the row is
    created) and ``exited_at`` is filled at check-out, so the log answers
    “who is inside right now?” with a single filter.
    """

    class Purpose(models.TextChoices):
        ADMISSION = "admission", "Admission enquiry"
        MEETING = "meeting", "Meeting staff"
        PARENT = "parent", "Parent / guardian"
        DELIVERY = "delivery", "Delivery"
        MAINTENANCE = "maintenance", "Maintenance"
        OTHER = "other", "Other"

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="fd_visitor_logs"
    )
    visitor_name = models.CharField(max_length=150)
    contact = models.CharField(max_length=30, blank=True, default="")
    id_number = models.CharField(max_length=60, blank=True, default="")
    purpose = models.CharField(
        max_length=12, choices=Purpose.choices, default=Purpose.OTHER
    )
    whom_to_meet = models.CharField(max_length=120, blank=True, default="")
    badge_no = models.CharField(max_length=30, blank=True, default="")
    entered_at = models.DateTimeField(default=timezone.now)
    exited_at = models.DateTimeField(null=True, blank=True)
    notes = models.CharField(max_length=300, blank=True, default="")
    handled_by = models.CharField(max_length=120, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-entered_at"]

    def __str__(self):
        return f"{self.visitor_name} ({self.get_purpose_display()}) @ {self.school.name}"

    @property
    def is_inside(self):
        return self.exited_at is None

    def as_dict(self):
        return {
            "id": self.pk,
            "visitor_name": self.visitor_name,
            "contact": self.contact or "—",
            "id_number": self.id_number or "—",
            "purpose": self.purpose,
            "whom_to_meet": self.whom_to_meet or "—",
            "badge_no": self.badge_no or "—",
            "entered_at": timezone.localtime(self.entered_at).strftime(
                "%b %d, %Y %H:%M"
            ),
            "entered_iso": self.entered_at.isoformat(),
            "exited_at": (
                timezone.localtime(self.exited_at).strftime("%b %d, %Y %H:%M")
                if self.exited_at else None
            ),
            "notes": self.notes,
            "handled_by": self.handled_by or "—",
            "is_inside": self.is_inside,
        }

class GatePass(models.Model):
    """A gate pass — student leaving early, visitor, vehicle or goods.

    ``pass_no`` is the per-school human reference printed on the pass
    (e.g. ``GP-2026-0001``). For students the row links to the Student
    record so the pass grid can show class/section; for visitors the
    free-text name/contact fields back the printed pass.
    """

    class PassType(models.TextChoices):
        STUDENT_EARLY = "student_early", "Student early leave"
        VISITOR = "visitor", "Visitor pass"
        VEHICLE = "vehicle", "Vehicle"
        GOODS = "goods", "Goods"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        RETURNED = "returned", "Returned"
        CANCELLED = "cancelled", "Cancelled"

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="fd_gate_passes"
    )
    pass_no = models.CharField(max_length=30)
    pass_type = models.CharField(
        max_length=15, choices=PassType.choices, default=PassType.STUDENT_EARLY
    )
    student = models.ForeignKey(
        Student, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="fd_gate_passes",
    )
    visitor_name = models.CharField(max_length=150, blank=True, default="")
    contact = models.CharField(max_length=30, blank=True, default="")
    reason = models.CharField(max_length=300)
    issued_to = models.CharField(max_length=150, blank=True, default="")
    issued_by = models.CharField(max_length=120, blank=True, default="")
    issued_at = models.DateTimeField(default=timezone.now)
    expected_return = models.DateTimeField(null=True, blank=True)
    returned_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.ACTIVE
    )
    remarks = models.CharField(max_length=300, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-issued_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "pass_no"], name="unique_gate_pass_no_per_school"
            )
        ]

    def __str__(self):
        return f"{self.pass_no} — {self.reason} ({self.status}) @ {self.school.name}"

    @property
    def is_outstanding(self):
        return self.status == self.Status.ACTIVE

    @property
    def holder_name(self):
        if self.student_id:
            return self.student.full_name
        return self.visitor_name or "—"

    def as_dict(self):
        return {
            "id": self.pk,
            "pass_no": self.pass_no,
            "pass_type": self.pass_type,
            "student_id": self.student_id,
            "student_name": self.student.full_name if self.student_id else None,
            "student_section": (
                self.student.class_section.label
                if self.student_id and self.student.class_section_id else None
            ),
            "holder_name": self.holder_name,
            "contact": self.contact or "—",
            "reason": self.reason,
            "issued_to": self.issued_to or "—",
            "issued_by": self.issued_by or "—",
            "issued_at": timezone.localtime(self.issued_at).strftime(
                "%b %d, %Y %H:%M"
            ),
            "expected_return": (
                timezone.localtime(self.expected_return).strftime(
                    "%b %d, %Y %H:%M"
                )
                if self.expected_return else None
            ),
            "returned_at": (
                timezone.localtime(self.returned_at).strftime(
                    "%b %d, %Y %H:%M"
                )
                if self.returned_at else None
            ),
            "status": self.status,
            "remarks": self.remarks,
            "is_outstanding": self.is_outstanding,
        }


class IDCard(models.Model):
    """A student/staff identity card for printing at the front desk.

    The card grid shows the card state (draft -> printed); the print page
    renders a printable front/back layout from the denormalized snapshot
    columns (holder name, section/designation, card no, validity) so
    printing never depends on live record edits.
    """

    class HolderType(models.TextChoices):
        STUDENT = "student", "Student"
        STAFF = "staff", "Staff"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PRINTED = "printed", "Printed"

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="fd_id_cards"
    )
    card_no = models.CharField(max_length=30)
    holder_type = models.CharField(
        max_length=10, choices=HolderType.choices, default=HolderType.STUDENT
    )
    student = models.ForeignKey(
        Student, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="fd_id_cards",
    )
    staff = models.ForeignKey(
        StaffMember, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="fd_id_cards",
    )
    # Denormalized snapshot used by the print layout.
    holder_name = models.CharField(max_length=150)
    holder_line = models.CharField(max_length=120, blank=True, default="")
    admission_no = models.CharField(max_length=40, blank=True, default="")
    guardian_phone = models.CharField(max_length=30, blank=True, default="")
    issued_on = models.DateField(null=True, blank=True)
    expires_on = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.DRAFT
    )
    remarks = models.CharField(max_length=300, blank=True, default="")
    created_by = models.CharField(max_length=120, blank=True, default="")
    printed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "card_no"], name="unique_id_card_no_per_school"
            )
        ]

    def __str__(self):
        return f"{self.card_no} — {self.holder_name} ({self.status})"

    @property
    def initials(self):
        parts = [p for p in self.holder_name.split() if p]
        init = "".join(part[0].upper() for part in parts[:2]) or "?"
        return init

    def as_dict(self):
        return {
            "id": self.pk,
            "card_no": self.card_no,
            "holder_type": self.holder_type,
            "student_id": self.student_id,
            "staff_id": self.staff_id,
            "holder_name": self.holder_name,
            "holder_line": self.holder_line or "—",
            "admission_no": self.admission_no or "—",
            "guardian_phone": self.guardian_phone or "—",
            "issued_on": self.issued_on.isoformat() if self.issued_on else None,
            "expires_on": self.expires_on.isoformat() if self.expires_on else None,
            "status": self.status,
            "remarks": self.remarks,
            "created_by": self.created_by or "—",
            "printed_at": (
                timezone.localtime(self.printed_at).strftime("%b %d, %Y %H:%M")
                if self.printed_at else None
            ),
            "created_at": timezone.localtime(self.created_at).strftime(
                "%b %d, %Y"
            ),
        }


class AuditLog(models.Model):
    """APPEND-ONLY action trail for the front desk.

    Every mutation (enquiry staged, visitor checked out, complaint logged
    or resolved, gate pass issued/returned, ID card printed...) writes a
    row here with the acting username. There are deliberately NO update or
    delete paths for audit rows — same tamper-evident guarantee as the HR
    and finance trails.
    """

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="fd_audit_logs"
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