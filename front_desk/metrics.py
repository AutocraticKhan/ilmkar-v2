"""Snapshot + alert metrics for the Front Desk dashboard.

Everything the dashboard and sidebar badges need is computed here so the
pages never disagree. Same philosophy as ``HR.metrics`` / ``Accountant.metrics``:
cheap queries, one source of truth per number.
"""
import datetime

from django.db.models import Count

from School_Admin.models import Complaint

from .models import AdmissionEnquiry, GatePass, IDCard


def enquiry_funnel(school):
    """Lead counts per stage + the live (open) totals for the dashboard
    chips: ``{stage_counts, open, applied, enrolled, dropped, due_followups}``.
    """
    rows = (
        AdmissionEnquiry.objects.filter(school=school)
        .values("stage")
        .annotate(count=Count("pk"))
    )
    stage_counts = {row["stage"]: row["count"] for row in rows}
    today = datetime.date.today()
    open_qs = AdmissionEnquiry.objects.filter(school=school).exclude(
        stage__in=[AdmissionEnquiry.Stage.ENROLLED, AdmissionEnquiry.Stage.DROPPED]
    )
    return {
        "stage_counts": stage_counts,
        "total": sum(stage_counts.values()),
        "open": open_qs.count(),
        "enrolled": stage_counts.get(AdmissionEnquiry.Stage.ENROLLED, 0),
        "dropped": stage_counts.get(AdmissionEnquiry.Stage.DROPPED, 0),
        "due_followups": open_qs.filter(
            follow_up_date__isnull=False, follow_up_date__lte=today
        ).count(),
    }


def visitors_inside(school):
    """Visitors currently on campus (checked in, not yet out)."""
    from .models import VisitorLog

    return VisitorLog.objects.filter(
        school=school, exited_at__isnull=True
    ).order_by("-entered_at")


def open_complaints(school):
    """Complaints/requests not yet resolved or closed."""
    return Complaint.objects.filter(school=school).exclude(
        status__in=[Complaint.Status.RESOLVED, Complaint.Status.CLOSED]
    )


def open_gate_passes(school):
    """Gate passes still active (not returned / cancelled)."""
    return GatePass.objects.filter(school=school, status=GatePass.Status.ACTIVE)


def id_card_summary(school):
    """Card state: drafts awaiting print vs printed."""
    rows = IDCard.objects.filter(school=school)
    return {
        "total": rows.count(),
        "drafts": rows.filter(status=IDCard.Status.DRAFT).count(),
        "printed": rows.filter(status=IDCard.Status.PRINTED).count(),
    }