"""Student-tenant helpers for the Student dashboard.

Access model: a student is a user holding a ``SAAS_admin.SchoolUser``
membership with the ``student`` role. Like every other dashboard, the
tenant scope is always a single ``School`` resolved from the signed-in
user's membership — never a raw id from the request.

TODO(integration): when the parent portal lands it must NOT reuse these
helpers — parents see their child's data through a different (guardian)
link, and the security notes in ``Teachers.models.TeacherNote`` apply.
"""
from SAAS_admin.models import SchoolUser
from School_Admin.models import Student

from .models import PortalSetting


def is_student(user):
    """True when the user may use the student dashboard (student-role
    membership on a school)."""
    if not getattr(user, "is_authenticated", False):
        return False
    return SchoolUser.objects.filter(
        user_id=user.pk, role=SchoolUser.Role.STUDENT
    ).exists()


def current_school(user):
    """The ONE school this student belongs to, or None.

    Mirrors ``Teachers.utils.current_school`` but for the student role.
    """
    if not getattr(user, "is_authenticated", False):
        return None
    membership = (
        SchoolUser.objects.filter(user_id=user.pk, role=SchoolUser.Role.STUDENT)
        .select_related("school")
        .first()
    )
    if membership is None:
        return None
    return membership.school


def current_student(user, school):
    """The ``School_Admin.Student`` record of the signed-in student.

    Resolution order:
      1. an explicit ``StudentProfile`` link (best — set from the admin
         console), then
      2. ``Student.admission_no`` == username, then
      3. ``Student.full_name`` == user's full name.

    Returns None when no match — views degrade gracefully (read-only /
    "not linked yet" states) instead of crashing.

    TODO(placeholder): step 1 is the real fix. TODO(integration): when
    ``School_Admin.Student`` gains a ``user`` FK (see StudentProfile),
    replace this whole lookup with ``user.student_record`` and delete the
    fallbacks.
    """
    if not getattr(user, "is_authenticated", False) or school is None:
        return None
    profile = getattr(user, "student_profile", None)
    if profile is not None and profile.student_id:
        return profile.student
    username = (user.get_username() or "").strip()
    if username:
        match = Student.objects.filter(
            school=school, status=Student.Status.ACTIVE,
            admission_no__iexact=username,
        ).first()
        if match:
            return match
    full_name = (user.get_full_name() or "").strip()
    if full_name:
        match = Student.objects.filter(
            school=school, status=Student.Status.ACTIVE,
            full_name__iexact=full_name,
        ).first()
        if match:
            return match
    return None


def portal_setting(school):
    """The ``PortalSetting`` switches for this school (creating the row on
    first touch so views never have to None-check)."""
    if school is None:
        return None
    setting, _ = PortalSetting.objects.get_or_create(school=school)
    return setting


def day_code(day):
    """``datetime.date`` -> ``Teachers.TimetableSlot.Day`` code ("Mon" ...).

    The Day choices are exactly the ``%a`` abbreviations, so this is a
    straight format (kept local so the Student app does not import from
    the Teachers app for one line).
    """
    return day.strftime("%a")


DAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
"""Canonical weekday order used to lay out the weekly timetable."""