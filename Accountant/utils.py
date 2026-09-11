"""Finance-tenant helpers for the Accountant dashboard.

Access model: an accountant is a user holding a ``SAAS_admin.SchoolUser``
membership with the ``accountant`` role. Principals are ALSO admitted
(their read-through mirrors the Teachers app pattern — they can review
statements and approve refunds without leaving their own dashboard; every
view still resolves ONE school).

Like every other dashboard, the tenant scope is always a single ``School``
resolved from the signed-in user's membership — never a raw id from the
request.
"""
from SAAS_admin.models import SchoolUser

DASHBOARD_ROLES = (SchoolUser.Role.ACCOUNTANT, SchoolUser.Role.PRINCIPAL)


def is_accountant(user):
    """True when the user may use the finance dashboard (accountant-role
    membership; principals get the read-through like the Teachers app)."""
    if not getattr(user, "is_authenticated", False):
        return False
    return SchoolUser.objects.filter(
        user_id=user.pk, role__in=DASHBOARD_ROLES
    ).exists()


def current_school(user):
    """The ONE school this finance user belongs to, or None.

    Mirrors ``School_Admin.utils.current_school`` (fresh query, filtered
    by ``user_id``) but accepts the wider DASHBOARD_ROLES set.
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
