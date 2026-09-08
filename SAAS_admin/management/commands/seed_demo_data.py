"""
Seed the operator console with dummy data so every page works before the
school-side dashboards produce real numbers.

Usage:
    python manage.py seed_demo_data          # seeds anything that is missing
    python manage.py seed_demo_data --force  # wipe dummy rows and re-seed

Real data will replace these snapshots once billing, login tracking and
storage accounting are implemented in the school dashboards.
"""
import datetime
import random

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from SAAS_admin.models import (
    Announcement,
    Invoice,
    School,
    SupportReply,
    SupportTicket,
    UsageSnapshot,
)

TICKETS = [
    ("Cannot upload student photos", "Uploading profile pictures fails with an error after a few students. It worked last week.", "Front Desk", "open", "high"),
    ("Fee report export is blank", "The monthly fee report exports an empty spreadsheet for August.", "Accountant", "open", "normal"),
    ("Parent portal login emails not arriving", "Parents say the password reset emails never reach their inboxes.", "Front Desk", "pending", "high"),
    ("Request: extra teacher accounts", "We hired two new teachers this term and need two more accounts.", "School Admin / Principal", "open", "low"),
    ("Timetable clash in section B", "Grade 7B has two classes booked in the lab at the same time on Thursdays.", "Teacher", "closed", "normal"),
    ("Invoice shows old package", "Our latest invoice still reflects the Starter package after upgrading.", "Owner", "pending", "normal"),
    ("Attendance module wishlist", "Could we get a weekly attendance summary export? Teachers would love it.", "School Admin / Principal", "open", "low"),
    ("Website link on parent emails is wrong", "The link points to the old school domain and shows a 404.", "Front Desk", "closed", "low"),
]

class Command(BaseCommand):
    help = "Seed dummy billing, usage, ticket and announcement data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force", action="store_true",
            help="Delete existing dummy rows first",
        )

    def handle(self, *args, **options):
        force = options["force"]
        schools = list(School.objects.all())
        if not schools:
            self.stdout.write(
                self.style.WARNING("No schools registered yet - nothing to seed.")
            )
            return

        if force:
            Invoice.objects.all().delete()
            UsageSnapshot.objects.all().delete()
            SupportTicket.objects.all().delete()
            Announcement.objects.all().delete()
            self.stdout.write("Existing dummy data removed (--force).")

        random.seed(42)
        today = datetime.date.today()
        year = today.year

        self._seed_invoices(schools, today, year)
        self._seed_usage(schools, today)
        self._seed_tickets(schools)
        self._seed_announcements()

        self.stdout.write(self.style.SUCCESS("Dummy data seeded successfully."))

    def _seed_invoices(self, schools, today, year):
        created = 0
        months = ["June", "July", "August", "September", "October"]
        for school in schools:
            if school.invoices.exists():
                continue
            for idx, month in enumerate(months):
                due_day = min(28, 10 + idx)
                try:
                    due = datetime.date(year, 6 + idx, due_day)
                except ValueError:
                    continue
                if due < today.replace(day=1):
                    status = Invoice.Status.PAID
                    paid_at = due - datetime.timedelta(days=random.randint(0, 5))
                elif due < today:
                    status = Invoice.Status.OVERDUE
                    paid_at = None
                else:
                    status = Invoice.Status.UNPAID
                    paid_at = None
                Invoice.objects.create(
                    school=school,
                    period=f"{month} {year}",
                    amount=school.mrr,
                    due_date=due,
                    status=status,
                    paid_at=paid_at,
                )
                created += 1

        if not Invoice.objects.filter(status=Invoice.Status.OVERDUE).exists():
            inv = Invoice.objects.filter(status=Invoice.Status.UNPAID).first()
            if inv:
                inv.status = Invoice.Status.OVERDUE
                inv.due_date = today - datetime.timedelta(days=12)
                inv.save(update_fields=["status", "due_date"])
        self.stdout.write(f"Invoices ready ({created} created).")

    def _seed_usage(self, schools, today):
        """Last 6 weekly snapshots; the first school gets a declining trend
        so the churn-risk column has something interesting to show."""
        snaps = 0
        declining_name = schools[0].name
        for school in schools:
            if school.usage_snapshots.exists():
                continue
            base_logins = max(20, school.students // 4) or 30
            base_active = int(school.students * 0.8) or 25
            for week in range(5, -1, -1):
                date = today - datetime.timedelta(days=week * 7)
                week_num = 5 - week  # 0 = oldest
                if school.name == declining_name:
                    # healthy start, then a crash in recent weeks -> at-risk
                    trend = [1.0, 0.95, 0.90, 0.85, 0.80, 0.45]
                    factor = trend[min(week_num, len(trend) - 1)]
                else:
                    factor = 0.85 + 0.05 * ((week_num * 7) % 5)  # gentle noise
                UsageSnapshot.objects.create(
                    school=school,
                    date=date,
                    logins=max(0, int(base_logins * factor)),
                    storage_mb=200 + week_num * 60 + random.randint(0, 40),
                    active_students=max(1, int(base_active * min(1.0, factor + 0.1))),
                )
                snaps += 1
        self.stdout.write(f"Usage snapshots ready ({snaps} created).")

    def _seed_tickets(self, schools):
        operator = User.objects.filter(is_superuser=True).first()
        tickets_created = 0
        for idx, (subject, body, requester_role, status, priority) in enumerate(TICKETS):
            school = schools[idx % len(schools)]
            if SupportTicket.objects.filter(subject=subject).exists():
                continue
            ticket = SupportTicket.objects.create(
                school=school,
                subject=subject,
                body=body,
                requester=f"{requester_role} ({school.name})",
                status=status,
                priority=priority,
            )
            tickets_created += 1
            if status == "closed":
                SupportReply.objects.create(
                    ticket=ticket, is_staff=True,
                    author=operator.get_username() if operator else "operator",
                    body="Thanks for the report - this has been fixed and deployed to your school.",
                )
                SupportReply.objects.create(
                    ticket=ticket, is_staff=False,
                    author=ticket.requester,
                    body="Confirmed working now. Thank you!",
                )
            elif status == "pending":
                SupportReply.objects.create(
                    ticket=ticket, is_staff=True,
                    author=operator.get_username() if operator else "operator",
                    body="Looking into this now - we will update you shortly.",
                )
        self.stdout.write(f"Support tickets ready ({tickets_created} created).")

    def _seed_announcements(self):
        if Announcement.objects.exists():
            self.stdout.write("Announcements already present - skipped.")
            return
        operator = User.objects.filter(is_superuser=True).first()
        Announcement.objects.create(
            title="Welcome to the ILMKAR operator console",
            body=(
                "School workspaces, billing and support tooling are rolling out. "
                "Expect more modules to appear here over the coming weeks."
            ),
            severity=Announcement.Severity.INFO,
            created_by=operator,
        )
        Announcement.objects.create(
            title="Scheduled maintenance this weekend",
            body=(
                "ILMKAR will be briefly unavailable on Saturday 02:00-04:00 "
                "while we upgrade the platform. No data will be lost."
            ),
            severity=Announcement.Severity.UPDATE,
            created_by=operator,
        )
        self.stdout.write("Announcements created (2).")