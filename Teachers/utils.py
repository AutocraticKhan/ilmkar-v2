"""Teacher-tenant helpers for the Teacher / Staff dashboard.

Access model: a teacher is a user holding a ``SAAS_admin.SchoolUser``
membership with the ``teacher`` role. Principals are ALSO admitted (their
read-through is what makes the private teacher notes + report comments
usable in parent meetings — every view still resolves ONE school).

Like every other dashboard, the tenant scope is always a single ``School``
resolved from the signed-in user's membership — never a raw id from the
request.
"""
from SAAS_admin.models import SchoolUser
from School_Admin.models import ClassSection, StaffMember

DASHBOARD_ROLES = (SchoolUser.Role.TEACHER, SchoolUser.Role.PRINCIPAL)


def is_teacher(user):
    """True when the user may use the teacher/staff dashboard.

    TODO(integration): when the front-desk and accountant apps land, keep
    them OUT of here — this dashboard is strictly teacher + principal
    preview. Owner-role memberships keep going to the chain dashboard.
    """
    if not getattr(user, "is_authenticated", False):
        return False
    return SchoolUser.objects.filter(
        user_id=user.pk, role__in=DASHBOARD_ROLES
    ).exists()


def current_school(user):
    """The ONE school this teacher belongs to, or None.

    Mirrors ``School_Admin.utils.current_school`` (fresh query, filtered by
    ``user_id``) but accepts the wider DASHBOARD_ROLES set.
    """
    if not getattr(user, "is_authenticated", False):
        return None
    membership = (
        SchoolUser.objects.filter(user_id=user.pk)
        .select_related("school")
        .first()
    )
    if membership is None or membership.role not in DASHBOARD_ROLES:
        return None
    return membership.school


def current_staff_member(user, school):
    """The ``School_Admin.StaffMember`` HR row of the signed-in teacher.

    Resolution order:
      1. an explicit ``TeacherProfile`` link (best — set from the admin
         console), then
      2. StaffMember email == user email, then
      3. StaffMember full_name == user's full name.

    Returns None when no match — views degrade gracefully (read-only /
    "not linked yet" states) instead of crashing.

    TODO(placeholder): step 1 is the real fix. TODO(integration): when
    ``StaffMember`` gains a ``user`` FK (see TeacherProfile), replace this
    whole lookup with ``user.staffmember`` and delete the fallbacks.
    """
    if not getattr(user, "is_authenticated", False) or school is None:
        return None
    profile = getattr(user, "teacher_profile", None)
    if profile is not None and profile.staff_member_id:
        return profile.staff_member
    if user.email:
        match = StaffMember.objects.filter(
            school=school, is_active=True, email__iexact=user.email
        ).first()
        if match:
            return match
    full_name = (user.get_full_name() or "").strip()
    if full_name:
        match = StaffMember.objects.filter(
            school=school, is_active=True, full_name__iexact=full_name
        ).first()
        if match:
            return match
    return None


def teacher_sections(school, staff):
    """ClassSections this teacher teaches (from the timetable), or ALL
    sections of the school when the staff link isn't resolved yet (or for
    the principal preview). Used by attendance / marks / diary scoping."""
    from .models import TimetableSlot

    if staff is None:
        return ClassSection_queryset(school)
    section_ids = (
        TimetableSlot.objects.filter(school=school, teacher=staff)
        .values_list("class_section_id", flat=True)
        .distinct()
    )
    sections = ClassSection.objects.filter(school=school, pk__in=list(section_ids))
    return sections or ClassSection_queryset(school)


def ClassSection_queryset(school):
    """All active sections of the school (helper kept explicit for
    readability above)."""
    return ClassSection.objects.filter(school=school)
