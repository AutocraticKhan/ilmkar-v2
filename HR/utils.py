"""HR-tenant helpers for the HR dashboard.

Access model: an HR user is a user holding a ``SAAS_admin.SchoolUser``
membership with the ``hr`` role. Principals are ALSO admitted as a
read-through (same pattern as the Accountant app: they can review
anything but never mutate). Every view still resolves ONE school.

Like every other dashboard, the tenant scope is always a single
``School`` resolved from the signed-in user's membership — never a raw
id from the request.
"""
from SAAS_admin.models import SchoolUser

DASHBOARD_ROLES = (SchoolUser.Role.HR, SchoolUser.Role.PRINCIPAL)


def is_hr(user):
    """True when the user may use the HR dashboard (hr-role membership;
    principals get the read-through like the Accountant app)."""
    if not getattr(user, "is_authenticated", False):
        return False
    return SchoolUser.objects.filter(
        user_id=user.pk, role__in=DASHBOARD_ROLES
    ).exists()


def can_mutate(user):
    """True when the user may WRITE to HR records. Principals get the
    read-through only — approvals/edits are HR staff's job."""
    if not getattr(user, "is_authenticated", False):
        return False
    return SchoolUser.objects.filter(
        user_id=user.pk, role=SchoolUser.Role.HR
    ).exists()


def current_school(user):
    """The ONE school this HR user belongs to, or None.

    Mirrors ``Accountant.utils.current_school`` (fresh query, filtered by
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