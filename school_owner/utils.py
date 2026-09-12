"""Owner-scope helpers shared by the owner dashboard and the operator console.

The first-class concept is: **an owner account owns one or more schools**.
Groups ("chains") still exist under the hood so the chain-wide features
(policies, hiring, announcements, approvals, transfers) keep working, but
they are now created automatically from the owner — the superuser never has
to set up a named chain first.

An account counts as an owner (see ``is_owner``) when any of these hold:
  * it owns a Chain (legacy/manual groups), OR
  * it is assigned as ``School.owner`` of one or more schools, OR
  * it has a school membership with the ``owner`` role (Users page).
"""
from django.db.models import Q

from SAAS_admin.models import School, SchoolUser


def is_owner(user):
    """True when the user may use the owner dashboard."""
    if not getattr(user, "is_authenticated", False):
        return False
    from .models import Chain

    return (
        Chain.objects.filter(owner=user).exists()
        or School.objects.filter(owners=user).exists()
        or SchoolUser.objects.filter(
            user=user, role=SchoolUser.Role.OWNER
        ).exists()
    )


def owner_schools(user):
    """All schools visible to an owner account (deduplicated).

    * assigned via School.owners,
    * or part of a chain they own,
    * or their single Owner-role membership (Users page).

    This is the tenant scope — the owner dashboard must never list anything
    outside this queryset.
    """
    return (
        School.objects.filter(
            Q(owners=user)
            | Q(chain__owner=user)
            | Q(
                memberships__user=user,
                memberships__role=SchoolUser.Role.OWNER,
            )
        )
        .distinct()
        .order_by("name")
    )


def ensure_chain_for_owner(owner):
    """Return the owner's group, creating it on first use.

    The chain name is derived from the account so the superuser never has to
    invent a chain name — it only shows in the dashboard sidebar.
    """
    from .models import Chain

    chain = Chain.objects.filter(owner=owner).first()
    if chain is not None:
        return chain
    return Chain.objects.create(
        name=f"{owner.get_username()}'s schools", owner=owner
    )


def assign_owner(school, owner):
    """Add (or remove) ``owner`` among the accounts owning ``school``.

    Multiple owners are allowed per school — the console warns before a
    second owner is added. Chain membership is NOT touched here: linking a
    school into a named chain is an explicit assignment (``chain_id``).
    """
    if owner is None:
        school.owners.clear()
        return school
    school.owners.add(owner)
    return school


def remove_school_owner(school, owner):
    """Remove one account from the school's owners."""
    school.owners.remove(owner)
    return school