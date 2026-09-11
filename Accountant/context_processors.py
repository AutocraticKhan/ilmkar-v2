"""Context processor: sidebar badge counts for the finance dashboard.

Kept in one place (instead of threading counts through every view) so the
sidebar badges stay consistent on every page. The queries only run for
signed-in finance users of a resolved school — every other request gets a
no-op dict.
"""
import datetime

from django.db.models import Count

from School_Admin.models import StudentFeeInvoice

from .models import LedgerEntry, PayrollPeriod, Refund
from .utils import current_school


def finance_badges(request):
    """Counts for the sidebar badges (kept cheap on purpose)."""
    school = current_school(getattr(request, "user", None))
    if school is None:
        return {}
    pending_refunds = Refund.objects.filter(
        school=school, status=Refund.Status.REQUESTED
    ).count()
    open_payroll = PayrollPeriod.objects.filter(
        school=school,
        status__in=[PayrollPeriod.Status.DRAFT, PayrollPeriod.Status.APPROVED],
    ).count()
    unreconciled = LedgerEntry.objects.filter(
        school=school, reconciled=False
    ).count()
    pending_defaulters = (
        StudentFeeInvoice.objects.filter(
            school=school,
            status__in=[
                StudentFeeInvoice.Status.UNPAID,
                StudentFeeInvoice.Status.PARTIAL,
            ],
            due_date__lt=datetime.date.today(),
        )
        .values("student_id")
        .distinct()
        .count()
    )
    return {
        "pending_refunds": pending_refunds,
        "open_payroll": open_payroll,
        "unreconciled": unreconciled,
        "pending_defaulters": pending_defaulters,
    }
