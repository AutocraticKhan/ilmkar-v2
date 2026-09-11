"""Context processor: sidebar badge counts for the HR dashboard.

Kept in one place (instead of threading counts through every view) so
the sidebar badges stay consistent on every page. The queries only run
for signed-in HR users of a resolved school — every other request gets
a no-op dict.
"""
import datetime

from School_Admin.models import LeaveRequest

from .models import OnboardingChecklist, PayrollInput, StaffDocument
from .services import current_period
from .utils import can_mutate, current_school


def hr_badges(request):
    """Counts for the sidebar badges (kept cheap on purpose)."""
    school = current_school(getattr(request, "user", None))
    if school is None:
        return {}
    today = datetime.date.today()
    horizon = today + datetime.timedelta(days=60)
    return {
        "hr_can_edit": can_mutate(getattr(request, "user", None)),
        "hr_pending_leaves": LeaveRequest.objects.filter(
            school=school, status=LeaveRequest.Status.PENDING
        ).count(),
        "hr_doc_alerts": StaffDocument.objects.filter(
            school=school, expiry_date__isnull=False, expiry_date__lte=horizon
        ).count(),
        "hr_open_onboarding": OnboardingChecklist.objects.filter(
            school=school, is_done=False
        ).count(),
        "hr_payroll_pending": PayrollInput.objects.filter(
            school=school, period=current_period(), fed_to_payroll=False
        ).count(),
    }
