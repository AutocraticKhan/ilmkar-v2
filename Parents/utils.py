"""Parent-tenant helpers for the Parent / Family dashboard.

Access model: a parent is a user holding a ``SAAS_admin.SchoolUser``
membership with the ``parent`` role. Like every other dashboard, the tenant
scope is always a single ``School`` resolved from the signed-in user's
membership — never a raw id from the request.

Children are resolved through ``ParentChildLink`` rows (explicit), with a
guardian-name fallback so accounts created before linking still work
(mirroring ``Student.utils.current_student``'s philosophy).
"""
from SAAS_admin.models import SchoolUser
from School_Admin.models import Student

from .models import ParentPortalSetting, ParentProfile


def is_parent(user):
    """True when the user may use the parent/family dashboard (parent-role
    membership on a school)."""
    if not getattr(user, "is_authenticated", False):
        return False
    return SchoolUser.objects.filter(
        user_id=user.pk, role=SchoolUser.Role.PARENT
    ).exists()


def current_school(user):
    """The ONE school this parent belongs to, or None.

    Mirrors ``Teachers.utils.current_school`` but for the parent role.
    """
    if not getattr(user, "is_authenticated", False):
        return None
    membership = (
        SchoolUser.objects.filter(user_id=user.pk, role=SchoolUser.Role.PARENT)
        .select_related("school")
        .first()
    )
    if membership is None:
        return None
    return membership.school


def current_profile(user, school):
    """The ``ParentProfile`` of the signed-in parent for this school.

    The row is created on first touch (like ``Student.utils.portal_setting``)
    so views never have to None-check the profile itself. ``guardian_name``
    defaults to the user's full name / username.
    """
    if not getattr(user, "is_authenticated", False) or school is None:
        return None
    profile = getattr(user, "parent_profile", None)
    if profile is not None and profile.school_id == school.pk:
        return profile
    profile, _ = ParentProfile.objects.get_or_create(
        school=school,
        user=user,
        defaults={
            "guardian_name": user.get_full_name() or user.get_username(),
        },
    )
    return profile


def children_of(profile, school):
    """The children (``School_Admin.Student`` rows) this parent may see.

    Resolution order:
      1. explicit ``ParentChildLink`` rows (set from the seed command or the
         Django admin) — a parent with links only ever sees the linked set;
      2. a guardian-name fallback: every ACTIVE student in the school whose
         ``guardian_name`` matches the profile's name, so pre-link accounts
         still work.

    Returns a plain list (always small) in a stable order.
    """
    if profile is None or school is None:
        return []
    linked = list(
        profile.child_links.filter(student__school=school)
        .select_related("student__class_section")
    )
    if linked:
        return [link.student for link in linked]

    full_name = (profile.guardian_name or "").strip()
    if not full_name:
        return []
    return list(
        Student.objects.filter(
            school=school,
            status=Student.Status.ACTIVE,
            guardian_name__iexact=full_name,
        ).select_related("class_section").order_by("full_name")
    )


def child_for_selection(children, child_id):
    """Pick one owned child by id, or the first child when none / a foreign
    id is passed.

    ``children`` is the parent's own list — a raw student id from the request
    is only ever accepted when it belongs to that set (tenant isolation).
    """
    if not children:
        return None
    try:
        child_id = int(child_id)
    except (TypeError, ValueError):
        child_id = None
    for child in children:
        if child_id is not None and child.pk == child_id:
            return child
    return children[0]


def portal_setting(school):
    """The ``ParentPortalSetting`` switches for this school (creating the row
    on first touch so views never have to None-check)."""
    if school is None:
        return None
    setting, _ = ParentPortalSetting.objects.get_or_create(school=school)
    return setting


def day_code(day):
    """``datetime.date`` -> ``Teachers.TimetableSlot.Day`` code ("Mon" ...).

    The Day choices are exactly the ``%a`` abbreviations, so this is a
    straight format (kept local so the Parents app does not import from the
    Teachers app for one line — same reason ``Student.utils.day_code`` exists).
    """
    return day.strftime("%a")


DAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
"""Canonical weekday order used by the digest / timetable surfaces."""