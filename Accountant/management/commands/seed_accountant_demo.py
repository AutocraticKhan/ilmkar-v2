"""
Seed the Accountant / Finance dashboard with demo data.

Usage:
    python manage.py seed_accountant_demo
    python manage.py seed_accountant_demo --force   # wipe Accountant rows first

Reuses the school + students + staff + fee invoices created by
``seed_school_demo`` (run that first for a full picture), then adds:
cash/bank accounts with a synced ledger, expenses (vendor + utility),
other income, a payroll run (calculated -> approved for the previous
period and a draft for the current one), a refund awaiting approval,
defaulter follow-ups and audit entries.

Creates (or re-uses) a demo finance login ``accountant`` /
``ilmkar-accountant-2026`` (accountant-role membership on the first
school).
"""
import datetime

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from SAAS_admin.models import School, SchoolUser

from Accountant.models import (
    AuditLog,
    CashAccount,
    DefaulterFollowUp,
    Expense,
    IncomeEntry,
    LedgerEntry,
    PayrollItem,
    PayrollPeriod,
    Refund,
)
from School_Admin.models import (
    FeeHead,
    FeePayment,
    StaffMember,
    Student,
    StudentFeeInvoice,
)

ACCOUNTANT_USERNAME = "accountant"
ACCOUNTANT_PASSWORD = "ilmkar-accountant-2026"

EXPENSES = [
    ("Anwar Stationers — supplies", Expense.Category.VENDOR, 12500, 12),
    ("Monthly premises rent", Expense.Category.RENT, 65000, 15),
    ("K-Electric bill", Expense.Category.UTILITY, 18400, 8),
    ("SSGC gas bill", Expense.Category.UTILITY, 7600, 9),
    ("Internet + phone", Expense.Category.UTILITY, 5200, 11),
    ("Water tanker", Expense.Category.UTILITY, 3600, 6),
]

INCOME = [
    ("Canteen monthly share", IncomeEntry.Source.CANTEEN, 22000, 10),
    ("Uniform & books sale", IncomeEntry.Source.SALE, 31500, 5),
    ("Community donation", IncomeEntry.Source.DONATION, 50000, 3),
]


class Command(BaseCommand):
    help = "Seed demo data for the Accountant / Finance dashboard."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force", action="store_true",
            help="Delete existing Accountant rows for the school first",
        )

    def handle(self, *args, **options):
        school = School.objects.first()
        if school is None:
            self.stdout.write(self.style.WARNING(
                "No schools registered yet — run seed_school_demo first "
                "(or register a school in the operator console)."
            ))
            return

        if options["force"]:
            self._wipe(school)
            self.stdout.write("Existing Accountant rows deleted.")

        actor = self._ensure_login(school)
        today = datetime.date.today()
        last_month = today.replace(day=1) - datetime.timedelta(days=1)
        prev_period = last_month.strftime("%B %Y")

        # 1. cash + bank accounts with opening balances
        CashAccount.objects.get_or_create(
            school=school, kind=CashAccount.Kind.CASH,
            defaults={"name": "Cash box", "opening_balance": 25000},
        )
        CashAccount.objects.get_or_create(
            school=school, kind=CashAccount.Kind.BANK,
            defaults={"name": "Bank account", "opening_balance": 180000},
        )

        # 2. make sure the current period has invoices + a few payments so
        #    collections/defaulters have data (only when nothing exists).
        if not StudentFeeInvoice.objects.filter(school=school).exists():
            self._seed_fees(school, today)
        if not FeePayment.objects.filter(invoice__school=school).exists():
            self._seed_payments(school, today)

        # 3. expenses + other income (this month, staggered dates)
        for title, category, amount, day in EXPENSES:
            Expense.objects.get_or_create(
                school=school, title=title,
                defaults={
                    "category": category,
                    "vendor": title.split(" — ")[0],
                    "amount": amount,
                    "method": (
                        Expense.Method.BANK
                        if category == Expense.Category.RENT
                        else Expense.Method.CASH
                    ),
                    "paid_on": today.replace(day=min(day, today.day)),
                    "reference_no": f"BILL-{category[:3].upper()}-{day:02d}",
                    "details": "Demo seed row.",
                    "recorded_by": actor,
                },
            )
        for title, source, amount, day in INCOME:
            count = IncomeEntry.objects.filter(school=school).count() + 1
            IncomeEntry.objects.get_or_create(
                school=school, title=title,
                defaults={
                    "source": source,
                    "amount": amount,
                    "method": IncomeEntry.Method.CASH,
                    "received_on": today.replace(day=min(day, today.day)),
                    "receipt_no": f"RCPT-{today.year}-{count:04d}",
                    "details": "Demo seed row.",
                    "recorded_by": actor,
                },
            )

        # 4. payroll: last month's run fully processed, current run draft
        prev_run, _ = PayrollPeriod.objects.get_or_create(
            school=school, period=prev_period,
            defaults={"created_by": actor},
        )
        if prev_run.status == PayrollPeriod.Status.DRAFT:
            self._calculate(prev_run, actor)
            prev_run.status = PayrollPeriod.Status.APPROVED
            prev_run.approved_by = actor
            prev_run.approved_at = timezone.now()
            prev_run.save()
        current_run, _ = PayrollPeriod.objects.get_or_create(
            school=school,
            period=today.strftime("%B %Y"),
            defaults={"created_by": actor},
        )
        if current_run.status == PayrollPeriod.Status.DRAFT:
            self._calculate(current_run, actor)

        # 5. a refund request awaiting a second person's approval
        student = Student.objects.filter(school=school).first()
        if student and not Refund.objects.filter(school=school).exists():
            Refund.objects.create(
                school=school,
                student=student,
                kind=Refund.Kind.REFUND,
                amount=1200,
                reason="Duplicate payment recorded for the same invoice.",
                requested_by=actor,
            )
            AuditLog.record(
                school, actor, "refund requested",
                f"Refund — {student.full_name}",
                note="Rs 1200: duplicate payment recorded for the same invoice.",
            )

        # 6. defaulter follow-ups
        self._seed_follow_ups(school, actor, today)

        # 7. ledger sync so reconciliation + P&L have the full picture
        created = LedgerEntry.sync_school(school)

        self.stdout.write(self.style.SUCCESS(
            f"Seeded Accountant data for {school.name}: "
            f"{created} ledger entries pulled in; payroll runs for "
            f"{prev_period} (approved) and {current_run.period} (draft); "
            f"login: {ACCOUNTANT_USERNAME} / {ACCOUNTANT_PASSWORD}"
        ))

    # ---------- helpers ----------

    def _wipe(self, school):
        LedgerEntry.objects.filter(school=school).delete()
        AuditLog.objects.filter(school=school).delete()
        DefaulterFollowUp.objects.filter(school=school).delete()
        Refund.objects.filter(school=school).delete()
        PayrollItem.objects.filter(school=school).delete()
        PayrollPeriod.objects.filter(school=school).delete()
        IncomeEntry.objects.filter(school=school).delete()
        Expense.objects.filter(school=school).delete()
        CashAccount.objects.filter(school=school).delete()

    def _ensure_login(self, school):
        user, created = User.objects.get_or_create(
            username=ACCOUNTANT_USERNAME,
            defaults={"email": "accounts@ilmkar.pk"},
        )
        if created:
            user.set_password(ACCOUNTANT_PASSWORD)
            user.save()
        SchoolUser.objects.get_or_create(
            school=school, user=user,
            defaults={"role": SchoolUser.Role.ACCOUNTANT},
        )
        return user.get_username()

    def _seed_fees(self, school, today):
        period = today.strftime("%B %Y")
        students = list(Student.objects.filter(school=school))
        heads = list(FeeHead.objects.filter(school=school))
        for index, student in enumerate(students):
            head = heads[index % len(heads)] if heads else None
            StudentFeeInvoice.objects.get_or_create(
                school=school, student=student, period=period,
                defaults={
                    "fee_head": head,
                    "amount": student.monthly_fee or 2500,
                    "due_date": today.replace(day=10),
                    "status": StudentFeeInvoice.Status.UNPAID,
                },
            )
        # a past-month invoice for a couple of students (defaulter history)
        prev_period = (today.replace(day=1) - datetime.timedelta(days=1)
                       ).strftime("%B %Y")
        for student in students[:3]:
            StudentFeeInvoice.objects.get_or_create(
                school=school, student=student, period=prev_period,
                defaults={
                    "amount": student.monthly_fee or 2500,
                    "due_date": (today.replace(day=1)
                                 - datetime.timedelta(days=20)),
                    "status": StudentFeeInvoice.Status.UNPAID,
                },
            )

    def _seed_payments(self, school, today):
        invoices = StudentFeeInvoice.objects.filter(
            school=school, period=today.strftime("%B %Y")
        )
        for index, invoice in enumerate(invoices):
            if index % 3 == 0:
                continue  # leave some unpaid so the defaulter list lives
            amount = invoice.amount if index % 2 == 0 else invoice.amount / 2
            FeePayment.objects.create(
                invoice=invoice,
                amount=amount,
                paid_on=today,
                method=(
                    FeePayment.Method.CASH if index % 2 == 0
                    else FeePayment.Method.BANK
                ),
                received_by="frontdesk",
            )
            paid_total = sum(p.amount for p in invoice.payments.all())
            invoice.status = (
                StudentFeeInvoice.Status.PAID
                if paid_total >= invoice.amount
                else StudentFeeInvoice.Status.PARTIAL
            )
            invoice.save()

    def _calculate(self, period, actor):
        from Teachers.models import Payslip

        for staff in StaffMember.objects.filter(
            school=period.school, is_active=True
        ):
            payslip = Payslip.objects.filter(
                school=period.school, staff=staff
            ).first()
            basic = payslip.basic if payslip else 32000
            allowances = payslip.allowances if payslip else 3000
            deductions = payslip.deductions if payslip else 1200
            PayrollItem.objects.get_or_create(
                period=period, staff=staff, school=period.school,
                defaults={
                    "basic": basic,
                    "allowances": allowances,
                    "deductions": deductions,
                },
            )
        AuditLog.record(
            period.school, actor, "payroll calculated", period.period,
            note=f"{period.items.count()} staff in the run",
        )

    def _seed_follow_ups(self, school, actor, today):
        # idempotent: clear existing follow-ups for the school first
        DefaulterFollowUp.objects.filter(school=school).delete()
        overdue_students = Student.objects.filter(
            school=school,
            fee_invoices__status__in=[
                StudentFeeInvoice.Status.UNPAID,
                StudentFeeInvoice.Status.PARTIAL,
            ],
            fee_invoices__due_date__lt=today,
        ).distinct()[:6]
        samples = [
            (DefaulterFollowUp.Outcome.CALLED, None,
             "Reminder call made; parent will check salary date."),
            (DefaulterFollowUp.Outcome.PROMISED,
             today + datetime.timedelta(days=7),
             "Promised to clear by Friday."),
            (DefaulterFollowUp.Outcome.VISITED, None,
             "Visited the office; asked for a two-week instalment plan."),
        ]
        for index, student in enumerate(overdue_students):
            outcome, promised, note = samples[index % len(samples)]
            DefaulterFollowUp.objects.get_or_create(
                school=school, student=student,
                defaults={
                    "outcome": outcome,
                    "promised_on": promised,
                    "note": note,
                    "followed_up_by": actor,
                },
            )



