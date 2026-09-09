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

# chain demo data is appended below in this same command

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
        self._seed_chain(schools, today)

        self.stdout.write(self.style.SUCCESS("Dummy data seeded successfully."))

    # --- chain demo data seeders (part 1) ---------------------------------
    def _seed_chain(self, schools, today):
        """Seed one chain demo: owner login, 3 branches, students, staff,
        classrooms, fee invoices, attendance, exams + chain features.

        TODO(placeholder): student/staff/fee/attendance/exam rows feed the
        chain owner dashboard. When the real school-side modules land they
        will own this data — replace this seeding accordingly.
        """
        from django.contrib.auth.models import User

        from school_owner.models import (
            ApprovalRequest,
            AttendanceSnapshot,
            BranchAnnouncement,
            Chain,
            Classroom,
            ExamSummary,
            FeeInvoice,
            GroupPolicy,
            JobPosting,
            Student,
            StaffMember,
        )

        import datetime as dt

        from django.utils import timezone

        random.seed(7)
        owner, owner_created = User.objects.get_or_create(username="groupowner")
        # Always (re)set the demo password + display fields so the documented
        # login keeps working even if this command is re-run or the user was
        # pre-created by something else. Skip superusers to never clobber an
        # operator account.
        if not owner.is_superuser:
            owner.is_active = True
            owner.email = owner.email or "owner@ilmkar.edu"
            owner.first_name = owner.first_name or "Group"
            owner.last_name = owner.last_name or "Owner"
            owner.set_password("ilmkar-owner-2026")
            owner.save()

        chain, chain_created = Chain.objects.get_or_create(
            name="Ilmkar Group of Schools", defaults={"owner": owner}
        )
        if not chain_created and chain.owner_id is None:
            chain.owner = owner
            chain.save(update_fields=["owner"])

        # Branches: first 3 registry schools (or create them if empty).
        branches = list(School.objects.filter(chain=chain)[:3])
        if len(branches) < 3:
            missing = [s for s in schools if s not in branches]
            branches += missing[: 3 - len(branches)]
            for s in branches:
                if s.chain_id != chain.pk:
                    s.chain = chain
                    s.save(update_fields=["chain"])
        if not branches:
            self.stdout.write(self.style.WARNING("No schools to seed as branches."))
            return
        self.stdout.write(f"Chain branches: {', '.join(s.name for s in branches)}")
        FIRST = ["Ayesha", "Bilal", "Fatima", "Hamza", "Imran", "Javeria",
                 "Kamran", "Laiba", "Mahnoor", "Nadia", "Osama", "Paras"]
        LAST = ["Khan", "Raza", "Sheikh", "Malik", "Qureshi"]
        DESIG = ["Teacher", "Senior Teacher", "Coordinator", "Librarian",
                 "Front Desk"]

        for s in branches:
            if Classroom.objects.filter(school=s).exists():
                continue
            rooms = [
                Classroom.objects.create(school=s, name=f"Room {r}", capacity=cap)
                for r, cap in zip(("A", "B", "C"), (40, 35, 30))
            ]
            for idx in range(random.randint(24, 32)):
                Student.objects.create(
                    school=s,
                    classroom=random.choice(rooms),
                    full_name=f"{random.choice(FIRST)} {random.choice(LAST)}",
                    admission_no=f"{s.pk}-{1000 + idx}",
                    monthly_fee=3500,
                    status=Student.Status.ACTIVE,
                )
            for idx in range(random.randint(12, 18)):
                StaffMember.objects.create(
                    school=s,
                    full_name=f"{random.choice(FIRST)} {random.choice(LAST)}",
                    designation=random.choice(DESIG),
                )
            # 30 days of attendance with a different health per branch.
            health = (0.96, 0.90, 0.86)[branches.index(s) % 3]
            total = Student.objects.filter(school=s).count()
            for back in range(30):
                date = today - dt.timedelta(days=back)
                present = int(total * min(1.0, health + random.uniform(-0.02, 0.02)))
                AttendanceSnapshot.objects.get_or_create(
                    school=s, date=date,
                    defaults={"present": present, "absent": max(0, total - present)},
                )
            ExamSummary.objects.get_or_create(
                school=s, term="Mid Term 2026",
                defaults={
                    "average_pct": round(random.uniform(52, 82), 1),
                    "recorded_at": today - dt.timedelta(days=10),
                },
            )
            self.stdout.write(f"Chain demo rows seeded for {s.name}.")
        # Fees for the current + previous periods across all branches.
        periods = []
        back = 0
        while len(periods) < 4:
            d = today - dt.timedelta(days=30 * back)
            periods.append(d.strftime("%B %Y"))
            back += 1
        for s in branches:
            students = list(Student.objects.filter(school=s))
            if FeeInvoice.objects.filter(school=s, period=periods[0]).exists():
                continue
            for p_idx, period in enumerate(periods):
                due = dt.date(today.year, today.month, 10) - dt.timedelta(days=30 * p_idx)
                # Different branches collect at different rates.
                rate = (0.92, 0.71, 0.55)[branches.index(s) % 3]
                for student in students:
                    paid = random.random() < rate * (1 - 0.05 * p_idx)
                    FeeInvoice.objects.create(
                        school=s, student=student, period=period,
                        amount=student.monthly_fee, due_date=due,
                        status=(FeeInvoice.Status.PAID if paid
                                else FeeInvoice.Status.UNPAID),
                        paid_at=due if paid else None,
                    )
        if not GroupPolicy.objects.filter(chain=chain).exists():
            GroupPolicy.objects.create(
                chain=chain, name="Monthly tuition 2026",
                category=GroupPolicy.Category.FEE_STRUCTURE,
                default_value="Tuition Rs 3,500/month \u00b7 sibling discount 15% "
                              "\u00b7 admission fee Rs 5,000 one-time",
                created_by=owner,
            )
            GroupPolicy.objects.create(
                chain=chain, name="Annual leave policy",
                category=GroupPolicy.Category.LEAVE_POLICY,
                default_value="12 paid casual leaves \u00b7 10 sick leaves \u00b7 "
                              "prior approval required for 3+ days",
                created_by=owner,
            )

        if not JobPosting.objects.filter(chain=chain).exists():
            JobPosting.objects.create(
                chain=chain, title="Physics teacher \u2014 secondary section",
                description="MSc Physics, 3+ years experience, O-Level background.",
                created_by=owner,
            )
            filled = JobPosting.objects.create(
                chain=chain, title="Front desk officer",
                description="Evening shift, strong communication skills.",
                created_by=owner,
            )
            filled.status = JobPosting.Status.FILLED
            filled.filled_branch = branches[0]
            filled.filled_at = timezone.now()
            filled.save(update_fields=["status", "filled_branch", "filled_at"])

        if not BranchAnnouncement.objects.filter(chain=chain).exists():
            BranchAnnouncement.objects.create(
                chain=chain, title="Parent-teacher meeting \u2014 next Friday",
                body="All branches hold PTM next Friday 16:00-19:00. "
                     "Prepare result slips before Wednesday.",
                created_by=owner,
            )
            BranchAnnouncement.objects.create(
                chain=chain, school=branches[0],
                title="Science lab stock check",
                body=f"{branches[0].name}: the group office will audit lab "
                     "inventory this week.",
                created_by=owner,
            )
        if not ApprovalRequest.objects.filter(chain=chain).exists():
            ApprovalRequest.objects.create(
                chain=chain, school=branches[1],
                request_type=ApprovalRequest.Type.BUDGET,
                title="Computer lab upgrade \u2014 Q3",
                details="20 machines + networking for the computer lab.",
                amount=1850000, requested_by=f"Principal ({branches[1].name})",
            )
            ApprovalRequest.objects.create(
                chain=chain, school=branches[2],
                request_type=ApprovalRequest.Type.NEW_HIRE,
                title="Extra math teacher for Grade 9",
                details="Section split pushed class size over 40.",
                requested_by=f"Principal ({branches[2].name})",
            )
            decided = ApprovalRequest.objects.create(
                chain=chain, school=branches[0], request_type=ApprovalRequest.Type.OTHER,
                title="Inter-branch sports tournament",
                details=f"Hosting fee for the annual {chain.name} tournament.",
                amount=120000, requested_by=f"Principal ({branches[0].name})",
            )
            decided.status = ApprovalRequest.Status.APPROVED
            decided.decision_note = "Approved \u2014 invoice the group office."
            decided.decided_at = timezone.now()
            decided.save(update_fields=["status", "decision_note", "decided_at"])
            ApprovalRequest.objects.create(
                chain=chain, school=branches[0], request_type=ApprovalRequest.Type.BUDGET,
                title="Rooftop canteen contract",
                amount=300000, requested_by=f"Principal ({branches[0].name})",
                status=ApprovalRequest.Status.REJECTED,
                decision_note="Revisit next year \u2014 safety concerns.",
                decided_at=timezone.now(),
            )

        self.stdout.write(
            f"Chain demo ready: {chain.name} \u00b7 owner @groupowner "
            "(password: ilmkar-owner-2026)"
        )

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