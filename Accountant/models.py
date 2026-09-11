"""Models for the Accountant / Finance dashboard.

``Accountant`` is the dedicated finance cockpit for ONE school: fee
collection analytics, defaulter follow-ups, expense and other-income
tracking, a unified cash/bank ledger with reconciliation, payroll
processing, printable invoices/receipts, and a refunds & adjustments
log with an append-only approval trail.

Conventions followed (matching School_Admin / school_owner / Teachers):
- every model is scoped to a ``SAAS_admin.School`` so the tenant boundary
  is enforced in views via ``Accountant.utils.current_school``;
- school-side rows FK to the placeholder ``School_Admin`` models
  (``Student``, ``StaffMember``, ``StudentFeeInvoice``);
- every money movement is mirrored into ``LedgerEntry`` (see
  ``LedgerEntry.sync_school``) so reconciliation and the income &
  expense statement never re-derive balances from four different models;
- ``AuditLog`` is APPEND-ONLY: no view ever edits or deletes a row, which
  is what makes the refund/approval trail tamper-evident.

TODO(integration): the fee side reads ``School_Admin.FeePayment`` /
``StudentFeeInvoice``; when the real fees module lands, keep the period
format ``"%B %Y"`` identical and point the sync at the new models.
TODO(integration): payroll mirrors paid rows into ``Teachers.Payslip``
(keeping the unique ``staff + period`` constraint) so the teacher's
salary history keeps working.
"""
from django.db import models

from SAAS_admin.models import School
from School_Admin.models import StaffMember, Student, StudentFeeInvoice


class CashAccount(models.Model):
    """A cash box or bank account the school's money is tracked against.

    Every ``LedgerEntry`` books against exactly one account; balances are
    ``opening_balance`` + SUM(in) - SUM(out). Two convenience accounts
    ("Cash box" + "Bank account") are created on first use by the sync
    helper — schools can add more (e.g. a second bank) from this app.
    """

    class Kind(models.TextChoices):
        CASH = "cash", "Cash"
        BANK = "bank", "Bank"

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="cash_accounts"
    )
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.CASH)
    opening_balance = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "name"], name="unique_cash_account_per_school"
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.get_kind_display()}) @ {self.school.name}"

    def as_dict(self):
        return {
            "id": self.pk,
            "name": self.name,
            "kind": self.kind,
            "kind_display": self.get_kind_display(),
            "opening_balance": float(self.opening_balance),
        }


class Expense(models.Model):
    """Money paid out: vendor payments, utility bills, salaries, rent.

    Payroll "mark paid" creates one salary-category ``Expense`` per staff
    member (see ``views.payroll_mark_paid``), so the P&L and the ledger
    count salaries exactly once.
    """

    class Category(models.TextChoices):
        VENDOR = "vendor_payment", "Vendor payment"
        UTILITY = "utility", "Utility bill"
        SALARY = "salary", "Salary"
        RENT = "rent", "Rent"
        OTHER = "other", "Other"

    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        BANK = "bank", "Bank transfer"
        CHEQUE = "cheque", "Cheque"
        ONLINE = "online", "Online"

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="expenses"
    )
    title = models.CharField(max_length=200)
    category = models.CharField(
        max_length=15, choices=Category.choices, default=Category.VENDOR
    )
    vendor = models.CharField(max_length=150, blank=True, default="")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(
        max_length=10, choices=Method.choices, default=Method.CASH
    )
    paid_on = models.DateField()
    reference_no = models.CharField(max_length=60, blank=True, default="")
    details = models.TextField(blank=True, default="")
    recorded_by = models.CharField(max_length=120, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-paid_on", "-created_at"]

    def __str__(self):
        return f"{self.title} ({self.get_category_display()}) @ {self.school.name}"

    def as_dict(self):
        from django.utils import timezone

        return {
            "id": self.pk,
            "title": self.title,
            "category": self.category,
            "category_display": self.get_category_display(),
            "vendor": self.vendor or "\u2014",
            "amount": float(self.amount),
            "method": self.method,
            "method_display": self.get_method_display(),
            "paid_on": self.paid_on.isoformat(),
            "reference_no": self.reference_no or "\u2014",
            "details": self.details,
            "recorded_by": self.recorded_by or "\u2014",
            "created_at": timezone.localtime(self.created_at).strftime("%b %d, %Y"),
        }


class IncomeEntry(models.Model):
    """Non-fee income (rent, canteen, donations, uniform shop, ...).

    Fee collections are NOT rows here — they come from
    ``School_Admin.FeePayment``. Each entry gets a receipt number so it
    can be printed from the Receipts page like a fee receipt.
    """

    class Source(models.TextChoices):
        RENT = "rent", "Rent"
        CANTEEN = "canteen", "Canteen"
        DONATION = "donation", "Donation"
        SALE = "sale", "Uniform / books sale"
        OTHER = "other", "Other"

    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        BANK = "bank", "Bank transfer"
        CHEQUE = "cheque", "Cheque"
        ONLINE = "online", "Online"

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="income_entries"
    )
    title = models.CharField(max_length=200)
    source = models.CharField(
        max_length=10, choices=Source.choices, default=Source.OTHER
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(
        max_length=10, choices=Method.choices, default=Method.CASH
    )
    received_on = models.DateField()
    receipt_no = models.CharField(max_length=40, blank=True, default="")
    details = models.TextField(blank=True, default="")
    recorded_by = models.CharField(max_length=120, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-received_on", "-created_at"]

    def __str__(self):
        return f"{self.title} ({self.get_source_display()}) @ {self.school.name}"

    def as_dict(self):
        from django.utils import timezone

        return {
            "id": self.pk,
            "title": self.title,
            "source": self.source,
            "source_display": self.get_source_display(),
            "amount": float(self.amount),
            "method": self.method,
            "method_display": self.get_method_display(),
            "received_on": self.received_on.isoformat(),
            "receipt_no": self.receipt_no or "\u2014",
            "details": self.details,
            "recorded_by": self.recorded_by or "\u2014",
            "created_at": timezone.localtime(self.created_at).strftime("%b %d, %Y"),
        }


class PayrollPeriod(models.Model):
    """One payroll run for one billing period (e.g. "September 2026").

    Status flow: draft (items being calculated/edited) -> approved
    (frozen, ``approved_by`` recorded) -> paid (salary ``Expense`` rows +
    ``LedgerEntry`` out rows created, ``Teachers.Payslip`` mirrored).
    The period label format is the platform-wide ``"%B %Y"`` so the P&L
    and the fee invoices line up.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        APPROVED = "approved", "Approved"
        PAID = "paid", "Paid"

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="payroll_periods"
    )
    period = models.CharField(max_length=30)  # e.g. "September 2026"
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.DRAFT
    )
    approved_by = models.CharField(max_length=120, blank=True, default="")
    approved_at = models.DateTimeField(null=True, blank=True)
    created_by = models.CharField(max_length=120, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "period"], name="unique_payroll_period_per_school"
            )
        ]

    def __str__(self):
        return f"Payroll {self.period} @ {self.school.name} ({self.status})"

    def as_dict(self):
        from django.utils import timezone

        return {
            "id": self.pk,
            "period": self.period,
            "status": self.status,
            "status_display": self.get_status_display(),
            "approved_by": self.approved_by or "\u2014",
            "created_by": self.created_by or "\u2014",
            "created_at": timezone.localtime(self.created_at).strftime("%b %d, %Y"),
        }


class PayrollItem(models.Model):
    """One staff member's calculated pay inside a ``PayrollPeriod``.

    "Calculate" pre-fills basic/allowances/deductions from the staff
    member's LATEST ``Teachers.Payslip`` (their salary history) or from
    the previous period's item — otherwise zero, for the accountant to
    fill in before approval.
    """

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="payroll_items"
    )
    period = models.ForeignKey(
        PayrollPeriod, on_delete=models.CASCADE, related_name="items"
    )
    staff = models.ForeignKey(
        StaffMember, on_delete=models.CASCADE, related_name="payroll_items"
    )
    basic = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    allowances = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid_on = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["staff__full_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["period", "staff"], name="unique_payroll_item_per_staff"
            )
        ]

    def __str__(self):
        return f"{self.staff.full_name} · {self.period.period}"

    @property
    def net_pay(self):
        return self.basic + self.allowances - self.deductions

    def as_dict(self):
        from django.utils import timezone

        return {
            "id": self.pk,
            "period_id": self.period_id,
            "staff_id": self.staff_id,
            "staff_name": self.staff.full_name,
            "designation": self.staff.designation or "\u2014",
            "basic": float(self.basic),
            "allowances": float(self.allowances),
            "deductions": float(self.deductions),
            "net_pay": float(self.net_pay),
            "paid_on": self.paid_on.isoformat() if self.paid_on else None,
            "created_at": timezone.localtime(self.created_at).strftime("%b %d, %Y"),
        }


class LedgerEntry(models.Model):
    """One book-keeping line for a single money movement.

    ``source_type`` + ``source_id`` point at the originating row (a fee
    payment, expense, income entry or refund). The sync helper
    (:meth:`sync_school`) upserts entries for every source row that does
    not have one yet, so the ledger is always complete and
    reconciliation = flagging entries as confirmed against the real
    cash/bank position ("money that has come in vs. what's recorded").

    Note: payroll does NOT create entries here directly — marking a
    payroll period paid creates salary ``Expense`` rows which sync like
    any other expense (prevents double counting).
    """

    class SourceType(models.TextChoices):
        FEE_PAYMENT = "fee_payment", "Fee payment"
        INCOME = "income", "Other income"
        EXPENSE = "expense", "Expense"
        REFUND = "refund", "Refund"

    class Direction(models.TextChoices):
        IN = "in", "Money in"
        OUT = "out", "Money out"

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="ledger_entries"
    )
    account = models.ForeignKey(
        CashAccount, on_delete=models.CASCADE, related_name="ledger_entries"
    )
    direction = models.CharField(
        max_length=3, choices=Direction.choices, default=Direction.IN
    )
    source_type = models.CharField(max_length=15, choices=SourceType.choices)
    source_id = models.PositiveIntegerField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    entry_date = models.DateField()
    description = models.CharField(max_length=240, blank=True, default="")
    reconciled = models.BooleanField(default=False)
    reconciled_at = models.DateTimeField(null=True, blank=True)
    reconciled_by = models.CharField(max_length=120, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-entry_date", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["source_type", "source_id"],
                name="unique_ledger_entry_per_source",
            )
        ]

    def __str__(self):
        return (
            f"[{self.get_direction_display()}] {self.amount} on {self.entry_date} "
            f"({self.get_source_type_display()})"
        )

    def as_dict(self):
        from django.utils import timezone

        return {
            "id": self.pk,
            "account_id": self.account_id,
            "account": self.account.name,
            "direction": self.direction,
            "source_type": self.source_type,
            "source_type_display": self.get_source_type_display(),
            "source_id": self.source_id,
            "amount": float(self.amount),
            "entry_date": self.entry_date.isoformat(),
            "description": self.description or "\u2014",
            "reconciled": self.reconciled,
            "reconciled_by": self.reconciled_by or "\u2014",
            "reconciled_at": (
                timezone.localtime(self.reconciled_at).strftime("%b %d, %Y")
                if self.reconciled_at else None
            ),
        }

    @classmethod
    def _accounts_for(cls, school):
        """Convenience (cash, bank) account pair, created on first use."""
        cash, _ = CashAccount.objects.get_or_create(
            school=school,
            kind=CashAccount.Kind.CASH,
            defaults={"name": "Cash box"},
        )
        bank, _ = CashAccount.objects.get_or_create(
            school=school,
            kind=CashAccount.Kind.BANK,
            defaults={"name": "Bank account"},
        )
        return cash, bank

    @staticmethod
    def _account_for_method(method, cash, bank):
        """Map a payment method onto the cash box or the bank account.

        Uses ``School_Admin.FeePayment.Method`` as the shared vocabulary
        (cash vs everything that clears through the bank).
        """
        from School_Admin.models import FeePayment

        if method == FeePayment.Method.CASH:
            return cash
        return bank  # bank transfer / online / cheque clear through the bank

    def balance_delta(self):
        """Signed effect of this entry on its account balance."""
        return (
            float(self.amount)
            if self.direction == self.Direction.IN
            else -float(self.amount)
        )


    @classmethod
    def sync_school(cls, school):
        """Create missing ledger entries for every recorded money movement.

        Idempotent: rows are keyed by (source_type, source_id), so it is
        safe (and cheap at demo scale) to call before any ledger view.
        Returns the number of entries created.
        """
        from School_Admin.models import FeePayment

        from .models import Expense, IncomeEntry, Refund

        cash, bank = cls._accounts_for(school)
        created = 0

        # Fee collections: money IN, routed by the recorded method.
        for payment in FeePayment.objects.filter(
            invoice__school=school
        ).select_related("invoice__student"):
            _, was_created = cls.objects.get_or_create(
                school=school,
                source_type=cls.SourceType.FEE_PAYMENT,
                source_id=payment.pk,
                defaults={
                    "account": cls._account_for_method(payment.method, cash, bank),
                    "direction": cls.Direction.IN,
                    "amount": payment.amount,
                    "entry_date": payment.paid_on,
                    "description": (
                        f"Fee payment — {payment.invoice.student.full_name} "
                        f"({payment.invoice.period})"
                    ),
                },
            )
            created += 1 if was_created else 0

        # Other income: money IN.
        for income in IncomeEntry.objects.filter(school=school):
            _, was_created = cls.objects.get_or_create(
                school=school,
                source_type=cls.SourceType.INCOME,
                source_id=income.pk,
                defaults={
                    "account": cls._account_for_method(income.method, cash, bank),
                    "direction": cls.Direction.IN,
                    "amount": income.amount,
                    "entry_date": income.received_on,
                    "description": f"{income.title} ({income.get_source_display()})",
                },
            )
            created += 1 if was_created else 0

        # Expenses: money OUT, routed by the recorded method.
        for expense in Expense.objects.filter(school=school):
            _, was_created = cls.objects.get_or_create(
                school=school,
                source_type=cls.SourceType.EXPENSE,
                source_id=expense.pk,
                defaults={
                    "account": cls._account_for_method(expense.method, cash, bank),
                    "direction": cls.Direction.OUT,
                    "amount": expense.amount,
                    "entry_date": expense.paid_on,
                    "description": f"{expense.title} ({expense.get_category_display()})",
                },
            )
            created += 1 if was_created else 0

        # Refunds that have actually been PAID: money OUT of the cash box.
        for refund in Refund.objects.filter(
            school=school, status=Refund.Status.PAID
        ).select_related("student"):
            _, was_created = cls.objects.get_or_create(
                school=school,
                source_type=cls.SourceType.REFUND,
                source_id=refund.pk,
                defaults={
                    "account": cash,
                    "direction": cls.Direction.OUT,
                    "amount": refund.amount,
                    "entry_date": refund.paid_on or refund.created_at.date(),
                    "description": (
                        f"{refund.get_kind_display()} — {refund.student.full_name}"
                    ),
                },
            )
            created += 1 if was_created else 0

        return created


class Refund(models.Model):
    """A refund or an adjustment owed back to a family.

    Anti-misuse design (the point of the approval trail):
    - created in ``requested`` state with ``requested_by`` recorded;
    - can ONLY be approved by a DIFFERENT signed-in user (the view refuses
      self-approval) — ``approved_by`` + ``decided_at`` are stamped and an
      ``AuditLog`` row is appended;
    - money only leaves the school at the separate "mark paid" step.
    """

    class Kind(models.TextChoices):
        REFUND = "refund", "Refund"
        ADJUSTMENT = "adjustment", "Adjustment"

    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        PAID = "paid", "Paid"

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="refunds"
    )
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="refunds"
    )
    invoice = models.ForeignKey(
        StudentFeeInvoice, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="refunds",
    )
    kind = models.CharField(
        max_length=12, choices=Kind.choices, default=Kind.REFUND
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.TextField()
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.REQUESTED
    )
    requested_by = models.CharField(max_length=120, blank=True, default="")
    approved_by = models.CharField(max_length=120, blank=True, default="")
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField(max_length=300, blank=True, default="")
    paid_on = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"[{self.get_status_display()}] {self.get_kind_display()} "
            f"{self.amount} for {self.student.full_name}"
        )

    def as_dict(self):
        from django.utils import timezone

        return {
            "id": self.pk,
            "student_id": self.student_id,
            "student_name": self.student.full_name,
            "class_section": (
                self.student.class_section.label
                if self.student.class_section_id else "\u2014"
            ),
            "invoice_id": self.invoice_id,
            "kind": self.kind,
            "kind_display": self.get_kind_display(),
            "amount": float(self.amount),
            "reason": self.reason,
            "status": self.status,
            "status_display": self.get_status_display(),
            "requested_by": self.requested_by or "\u2014",
            "approved_by": self.approved_by or "\u2014",
            "decided_at": (
                timezone.localtime(self.decided_at).strftime("%b %d, %Y")
                if self.decided_at else None
            ),
            "decision_note": self.decision_note,
            "paid_on": self.paid_on.isoformat() if self.paid_on else None,
            "created_at": timezone.localtime(self.created_at).strftime("%b %d, %Y"),
        }


class DefaulterFollowUp(models.Model):
    """A follow-up touchpoint on a fee defaulter (the collections page).

    ``outcome`` records what happened (called / no answer / promised /
    visited / cleared) and ``promised_on`` captures the promised payment
    date so the next follow-up can be prioritised.
    """

    class Outcome(models.TextChoices):
        CALLED = "called", "Called"
        NO_ANSWER = "no_answer", "No answer"
        PROMISED = "promised", "Promised to pay"
        VISITED = "visited", "Parent visited school"
        SETTLED = "settled", "Cleared / paid"

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="follow_ups"
    )
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="follow_ups"
    )
    outcome = models.CharField(
        max_length=12, choices=Outcome.choices, default=Outcome.CALLED
    )
    promised_on = models.DateField(null=True, blank=True)
    note = models.TextField(blank=True, default="")
    followed_up_by = models.CharField(max_length=120, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_outcome_display()} — {self.student.full_name}"

    def as_dict(self):
        from django.utils import timezone

        return {
            "id": self.pk,
            "student_id": self.student_id,
            "student_name": self.student.full_name,
            "outcome": self.outcome,
            "outcome_display": self.get_outcome_display(),
            "promised_on": self.promised_on.isoformat() if self.promised_on else None,
            "note": self.note,
            "followed_up_by": self.followed_up_by or "\u2014",
            "created_at": timezone.localtime(self.created_at).strftime(
                "%b %d, %Y %H:%M"
            ),
        }


class AuditLog(models.Model):
    """APPEND-ONLY action trail for the finance cockpit.

    Every mutation (expense/income/refund/payroll/reconciliation) writes a
    row here with the acting username. There are deliberately NO update or
    delete paths for audit rows in this app — that is what makes the
    approval trail trustworthy.
    """

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="audit_logs"
    )
    actor = models.CharField(max_length=120)
    action = models.CharField(max_length=40)
    target = models.CharField(max_length=200)
    note = models.CharField(max_length=300, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.actor} — {self.action} — {self.target}"

    def as_dict(self):
        from django.utils import timezone

        return {
            "id": self.pk,
            "actor": self.actor,
            "action": self.action,
            "target": self.target,
            "note": self.note or "\u2014",
            "created_at": timezone.localtime(self.created_at).strftime(
                "%b %d, %Y %H:%M"
            ),
        }

    @classmethod
    def record(cls, school, actor, action, target, note=""):
        """Single append point used by every mutating view."""
        return cls.objects.create(
            school=school, actor=actor, action=action, target=target, note=note
        )







