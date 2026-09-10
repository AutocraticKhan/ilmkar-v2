"""School-tenant helpers for the School Admin / Principal dashboard.

Access model: a principal is a user holding a ``SAAS_admin.SchoolUser``
membership with the ``principal`` role (created on the operator console's
Users page). Each membership belongs to exactly ONE school, so the tenant
scope is always a single ``School`` — the dashboard must never query a
school by a raw id from the request.

TODO(integration): when the staff/teacher and front-desk apps land, relax
``is_school_admin`` to accept their roles (or add per-page permission
checks keyed off ``SchoolUser.Role``). Owner-role memberships keep going
to the chain dashboard, so they are deliberately NOT accepted here.
"""
from django.contrib.auth.models import User  # noqa: F401  (documented import)

from SAAS_admin.models import SchoolUser


def is_school_admin(user):
    """True when the user may use the school admin dashboard."""
    if not getattr(user, "is_authenticated", False):
        return False
    return SchoolUser.objects.filter(
        user_id=user.pk, role=SchoolUser.Role.PRINCIPAL
    ).exists()


def current_school(user):
    """The school this principal administers, or None.

    Uses a fresh query instead of ``user.school_membership`` — a OneToOne
    access raises RelatedObjectDoesNotExist when the user has no membership.
    Filtering by ``user_id`` keeps the lookup independent of the lazy
    ``request.user`` proxy object.
    """
    if not getattr(user, "is_authenticated", False):
        return None
    membership = SchoolUser.objects.filter(user_id=user.pk).select_related("school").first()
    if membership is None or membership.role != SchoolUser.Role.PRINCIPAL:
        return None
    return membership.school