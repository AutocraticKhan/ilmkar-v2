"""Cross-app wiring for the chain (owner) dashboard.

``School_Admin`` is the single source of truth for school-side staff and
students; the owner dashboard keeps light MIRROR rows (``chain_staff`` /
``chain_students``) so its branch aggregations and cross-branch transfers
keep working without touching school data directly. The helpers here keep
those mirrors in sync — school-side create/status views call them lazily
(imported inside the view), matching the lazy-import decoupling pattern
used across the apps.

- ``mirror_student_to_owner`` — upsert the chain mirror of a
  ``School_Admin.Student`` (matched per school + admission_no) and refresh
  the operator console's registry count;
- ``mirror_staff_to_owner`` — same for ``School_Admin.StaffMember``;
- ``sync_registry_count`` — keep ``School.students`` aligned with the
  active mirror rows;
- ``escalate_to_owner`` / ``principal_request_to_owner`` — create
  ``school_owner.ApprovalRequest`` rows in the owner's approval feed
  (only possible while the school belongs to a chain — a standalone
  school has no owner to approve anything).
"""
from SAAS_admin.models import School
from school_owner.models import ApprovalRequest, Student, StaffMember


def mirror_student_to_owner(student):
    """Upsert the owner-dashboard mirror of one ``School_Admin.Student``.

    Matched on (school, admission_no) so re-admissions / edits update the
    same chain row instead of duplicating it. The chain ``Classroom`` FK is
    left empty — sections and classrooms are not yet mapped across apps.
    """
    status = (
        Student.Status.ACTIVE
        if student.status == student.Status.ACTIVE
        else Student.Status.INACTIVE
    )
    chain_student, _ = Student.objects.update_or_create(
        school=student.school,
        admission_no=student.admission_no,
        defaults={
            "full_name": student.full_name,
            "monthly_fee": student.monthly_fee,
            "status": status,
        },
    )
    sync_registry_count(student.school)
    return chain_student


def mirror_staff_to_owner(staff_member):
    """Upsert the owner-dashboard mirror of one ``School_Admin.StaffMember``.

    ``StaffMember`` has no natural unique key, so rows are matched on
    (school, full_name) — renames would orphan the old chain row, which is
    acceptable for a light count/transfer mirror.
    """
    chain_staff, _ = StaffMember.objects.update_or_create(
        school=staff_member.school,
        full_name=staff_member.full_name,
        defaults={
            "designation": staff_member.designation,
            "is_active": staff_member.is_active,
        },
    )
    return chain_staff


def sync_registry_count(school):
    """Keep ``School.students`` (the operator console's registry number)
    aligned with the ACTIVE mirror rows. Cheap — call it freely."""
    school.students = Student.objects.filter(
        school=school, status=Student.Status.ACTIVE
    ).count()
    school.save(update_fields=["students"])
    return school.students


def escalate_to_owner(
    school, request_type, title, details="", amount=None, requested_by=""
):
    """Create one ``ApprovalRequest`` in the owning chain's feed.

    Returns the created row, or ``None`` when the school is standalone
    (no chain) or the type is not a valid ``ApprovalRequest.Type``.
    """
    if school.chain_id is None or request_type not in ApprovalRequest.Type.values:
        return None
    return ApprovalRequest.objects.create(
        chain=school.chain,
        school=school,
        request_type=request_type,
        title=title[:200],
        details=details,
        amount=amount,
        requested_by=(requested_by or "")[:120],
    )


def principal_request_to_owner(
    principal_user, school, request_type, title, details="", amount=None
):
    """A branch principal submits a request to the group owner.

    Fills ``requested_by`` with the principal's display name (the column
    is still free text until the FK swap noted on the model).
    """
    return escalate_to_owner(
        school,
        request_type=request_type,
        title=title,
        details=details,
        amount=amount,
        requested_by=(
            principal_user.get_full_name() or principal_user.get_username()
            if getattr(principal_user, "is_authenticated", False)
            else ""
        ),
    )