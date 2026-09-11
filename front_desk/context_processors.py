"""Context processor: sidebar badge counts for the Front Desk dashboard.

Kept in one place (instead of threading counts through every view) so the
sidebar badges stay consistent on every page. The queries only run for
signed-in front-desk users of a resolved school — every other request gets
a no-op dict.
"""
from School_Admin.models import Complaint

from .models import AdmissionEnquiry, GatePass
from .utils import can_mutate, current_school


def front_desk_badges(request):
    """Counts for the sidebar badges (kept cheap on purpose)."""
    school = current_school(getattr(request, "user", None))
    if school is None:
        return {}
    return {
        "fd_can_edit": can_mutate(getattr(request, "user", None)),
        "fd_open_enquiries": AdmissionEnquiry.objects.filter(school=school).exclude(
            stage__in=[
                AdmissionEnquiry.Stage.ENROLLED, AdmissionEnquiry.Stage.DROPPED
            ]
        ).count(),
        "fd_visitors_inside": school.fd_visitor_logs.filter(
            exited_at__isnull=True
        ).count(),
        "fd_open_complaints": Complaint.objects.filter(school=school).exclude(
            status__in=[Complaint.Status.RESOLVED, Complaint.Status.CLOSED]
        ).count(),
        "fd_active_passes": GatePass.objects.filter(
            school=school, status=GatePass.Status.ACTIVE
        ).count(),
    }