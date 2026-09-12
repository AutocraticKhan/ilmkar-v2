"""Real usage-metric computation for the operator console.

``UsageSnapshot`` rows used to come from the seed command (dummy data);
these helpers compute the values from live data instead. Call
``refresh_snapshots`` — via the ``refresh_usage_snapshots`` management
command (cron-able) or automatically when the operator opens the Usage
page — to capture the numbers for a day.

Snapshot semantics (one row per school per day):
- ``logins`` — members of the school (``SAAS_admin.SchoolUser``) whose
  platform ``User.last_login`` falls on the snapshot day;
- ``active_students`` — ACTIVE student count; prefers the school-side
  ``School_Admin.Student`` rows and falls back to the chain mirror
  (``school_owner.Student``) for schools whose students only exist in
  the owner dashboard yet;
- ``storage_mb`` — 0 for now; becomes the sum of uploaded-file sizes
  once the content module introduces ``FileField`` uploads.
"""
import datetime

from django.contrib.auth.models import User
from django.utils import timezone

from SAAS_admin.models import School, SchoolUser, UsageSnapshot


def _day_bounds(day):
    """UTC-aware [start, end) window covering ``day`` in local time."""
    start = timezone.make_aware(
        datetime.datetime.combine(day, datetime.time.min)
    )
    return start, start + datetime.timedelta(days=1)


def active_students_of(school):
    """ACTIVE students at the school (school dashboard first, chain
    mirror as fallback)."""
    from School_Admin.models import Student as SchoolStudent

    count = SchoolStudent.objects.filter(
        school=school, status=SchoolStudent.Status.ACTIVE
    ).count()
    if count:
        return count

    from school_owner.models import Student as ChainStudent

    return ChainStudent.objects.filter(
        school=school, status=ChainStudent.Status.ACTIVE
    ).count()


def logins_of(school, day):
    """Distinct member logins of the school on ``day`` (by last_login)."""
    start, end = _day_bounds(day)
    member_ids = list(
        SchoolUser.objects.filter(school=school).values_list("user_id", flat=True)
    )
    if not member_ids:
        return 0
    return User.objects.filter(
        pk__in=member_ids, last_login__gte=start, last_login__lt=end
    ).count()


def compute_school_usage(school, day):
    """The three metric values for one school on one day."""
    return {
        "logins": logins_of(school, day),
        "storage_mb": 0,
        "active_students": active_students_of(school),
    }


def refresh_snapshots(schools=None, day=None):
    """Compute (and upsert) the usage snapshot for ``day`` (default:
    today) for all schools, or the given subset. Returns the snapshots."""
    day = day or timezone.localdate()
    schools = schools if schools is not None else School.objects.all()
    snapshots = []
    for school in schools:
        snapshot, _ = UsageSnapshot.objects.update_or_create(
            school=school, date=day, defaults=compute_school_usage(school, day)
        )
        snapshots.append(snapshot)
    return snapshots