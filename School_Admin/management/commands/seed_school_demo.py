"""
Seed the School Admin / Principal dashboard with demo data.

Usage:
    python manage.py seed_school_demo             # seeds the first school
    python manage.py seed_school_demo --force     # wipe School_Admin rows first

Creates (or re-uses) a demo principal login ``principal`` /
``ilmkar-principal-2026`` attached to the first registered school, plus
classes, students, admissions, staff, fees, attendance, exams, notices,
complaints and front-desk entries so every School_Admin page has data.

TODO(integration): real data will replace these rows once the live
student/fee/attendance modules and the parent/teacher portals push their
own records into ``School_Admin.models``.
"""
import datetime
import random

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from SAAS_admin.models import School, SchoolUser

from School_Admin.models import (
    AdmissionApplication,
    AttendanceSnapshot,
    ClassSection,
    Complaint,
    ExamRecord,
    ExpenseRequest,
    FeeHead,
    FeePayment,
    FrontDeskEntry,
    LeaveRequest,
    Notice,
    Student,
    StudentFeeInvoice,
    StaffMember,
)

PRINCIPAL_USERNAME = "principal"
PRINCIPAL_PASSWORD = "ilmkar-principal-2026"

SECTIONS = [
    ("Playgroup", "A"),
    ("KG", "A"),
    ("Grade 1", "A"),
    ("Grade 1", "B"),
    ("Grade 2", "A"),
    ("Grade 3", "A"),
]

STUDENTS = [
    ("ADM-2025-0001", "Ayesha Khan", "Mrs. Farah Khan", "0300 1112233", "Grade 1", "A", 2800),
    ("ADM-2025-0002", "Hamza Ali", "Mr. Ali Raza", "0300 2223344", "Grade 1", "A", 2800),
    ("ADM-2025-0003", "Zainab Fatima", "Mr. Kamran Aslam", "0300 3334455", "Grade 1", "B", 2600),
    ("ADM-2024-0010", "Bilal Ahmed", "Mr. Imran Ahmed", "0300 4445566", "Grade 2", "A", 2500),
    ("ADM-2024-0011", "Mahnoor Tariq", "Mrs. Sana Tariq", "0300 5556677", "Grade 2", "A", 2500),
    ("ADM-2023-0020", "Ali Hassan", "Mr. Hassan Raza", "0300 6667788", "Grade 3", "A", 2400),
    ("ADM-2023-0021", "Hira Shahid", "Mr. Shahid Mehmood", "0300 7778899", "Grade 3", "A", 2400),
    ("ADM-2025-0004", "Umaima Noor", "Mr. Tariq Noor", "0300 8889900", "KG", "A", 1800),
    ("ADM-2025-0005", "Rohan Faraz", "Mr. Faraz Iqbal", "0300 9990011", "Playgroup", "A", 1600),
]

STAFF = [
    ("Ms. Sana Tariq", "Vice Principal", "Academics", "0301 1112223", "sana.tariq@school.edu"),
    ("Mr. Kamran Aslam", "Senior Teacher", "Science", "0301 2223334", "kamran.aslam@school.edu"),
    ("Ms. Rabia Ahmed", "Teacher", "English", "0301 3334445", "rabia.ahmed@school.edu"),
    ("Mr. Shahid Mehmood", "Accountant", "Finance", "0301 4445556", "shahid@school.edu"),
    ("Ms. Farah Khan", "Front Desk", "Admin", "0301 5556667", "frontdesk@school.edu"),
    ("Mr. Bilal Qureshi", "PT / Sports", "Sports", "0301 6667778", "bilal.q@school.edu"),
]


class Command(BaseCommand):
    help = "Seed demo data for the School Admin / Principal dashboard."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force", action="store_true",
            help="Delete existing School_Admin rows for the school first",
        )

    def handle(self, *args, **options):
        school = School.objects.first()
        if school is None:
            self.stdout.write(self.style.WARNING(
                "No schools registered yet - nothing to seed."
            ))
            return
        force = options["force"]

        if force:
            school.sections.all().delete()
            school.school_students.all().delete()
            school.admission_applications.all().delete()
            school.school_staff.all().delete()
            school.leave_requests.all().delete()
            school.expense_requests.all().delete()
            school.fee_heads.all().delete()
            school.fee_invoices.all().delete()
            school.attendance_records.all().delete()
            school.exam_records.all().delete()
            school.notices.all().delete()
            school.complaints.all().delete()
            school.front_desk_entries.all().delete()
            school.memberships.filter(user__username=PRINCIPAL_USERNAME).delete()
            User.objects.filter(username=PRINCIPAL_USERNAME, is_superuser=False).delete()
            self.stdout.write("Existing School_Admin demo data removed (--force).")

        random.seed(7)

        principal = self._ensure_principal(school)

        sections = self._seed_sections(school)
        staff = self._seed_staff(school)
        students = self._seed_students(school, sections)
        self._seed_admissions(school, sections)
        self._seed_leaves(school, staff)
        self._seed_expenses(school, staff)
        heads = self._seed_fee_heads(school, sections)
        self._seed_invoices(school, students, heads)
        self._seed_attendance(school, sections)
        self._seed_exams(school, sections)
        self._seed_notices(school, principal)
        self._seed_complaints(school)
        self._seed_front_desk(school, staff)

        self.stdout.write(self.style.SUCCESS(
            f"School_Admin demo data seeded for '{school.name}'.\n"
            f"  Demo principal login: '{PRINCIPAL_USERNAME}' / '{PRINCIPAL_PASSWORD}'"
        ))

    def _ensure_principal(self, school):
        user = User.objects.filter(username=PRINCIPAL_USERNAME).first()
        if user is None:
            user = User.objects.create_user(
                username=PRINCIPAL_USERNAME,
                email="principal@school.edu",
                first_name="School",
                last_name="Principal",
                password=PRINCIPAL_PASSWORD,
                is_staff=False,
                is_superuser=False,
            )
        if not SchoolUser.objects.filter(user=user).exists():
            SchoolUser.objects.create(school=school, user=user, role=SchoolUser.Role.PRINCIPAL)
        self.stdout.write(f"Principal account ready: '{PRINCIPAL_USERNAME}'.")
        return user

    def _seed_sections(self, school):
        if school.sections.exists():
            self.stdout.write("Sections already present - skipped.")
            return list(school.sections.all())
        created = []
        for grade, section in SECTIONS:
            created.append(ClassSection.objects.create(
                school=school, grade=grade, section=section, capacity=30,
            ))
        self.stdout.write(f"Class sections ready ({len(created)}).")
        return created

    def _seed_staff(self, school):
        if school.school_staff.exists():
            return list(school.school_staff.all())
        created = [
            StaffMember.objects.create(
                school=school, full_name=name, designation=desig,
                department=dept, phone=phone, email=email,
                join_date=datetime.date(2023, 8, 1),
            )
            for name, desig, dept, phone, email in STAFF
        ]
        self.stdout.write(f"Staff ready ({len(created)}).")
        return created

    def _seed_students(self, school, sections):
        if school.school_students.exists():
            return list(school.school_students.select_related("class_section"))
        lookup = {f"{s.grade}-{s.section}": s for s in sections}
        created = []
        for idx, (adm_no, name, guardian, phone, grade, section, fee) in enumerate(STUDENTS):
            student = Student.objects.create(
                school=school,
                class_section=lookup.get(f"{grade}-{section}"),
                admission_no=adm_no,
                full_name=name,
                guardian_name=guardian,
                guardian_phone=phone,
                monthly_fee=fee,
                admission_date=datetime.date(2025, 8, 15),
                status=Student.Status.LEFT if idx == 4 else Student.Status.ACTIVE,
            )
            created.append(student)
        self.stdout.write(f"Students ready ({len(created)}).")
        return created

    def _seed_admissions(self, school, sections):
        if school.admission_applications.exists():
            return
        pending = [
            ("Hamza Tariq", "Grade 1", "A", "Mr. Tariq Mehmood", "0302 1110001"),
            ("Anaya Rizwan", "Playgroup", "A", "Mr. Rizwan Khan", "0302 2220002"),
            ("Hassan Jamal", "Grade 2", "A", "Mrs. Jamal Fatima", "0302 3330003"),
        ]
        lookup = {f"{s.grade}-{s.section}": s for s in sections}
        for name, grade, section, guardian, phone in pending:
            AdmissionApplication.objects.create(
                school=school,
                applicant_name=name,
                guardian_name=guardian,
                guardian_phone=phone,
                class_section=lookup.get(f"{grade}-{section}"),
                note="Applied for the coming term.",
            )
        AdmissionApplication.objects.create(
            school=school,
            applicant_name="Zohaib Anwar",
            guardian_name="Mr. Anwar Sadiq",
            guardian_phone="0302 4440004",
            class_section=lookup.get("KG-A"),
            status=AdmissionApplication.Status.WAITLISTED,
            decision_note="Waitlist - class full for now.",
            decided_by=PRINCIPAL_USERNAME,
            decided_at=timezone.now(),
            note="Second child - hoping for a sibling seat.",
        )
        self.stdout.write("Admission applications ready (4).")

    def _seed_leaves(self, school, staff):
        if school.leave_requests.exists():
            return
        today = datetime.date.today()
        teacher = next((s for s in staff if "Teacher" in s.designation), staff[0])
        LeaveRequest.objects.create(
            school=school, staff=teacher,
            from_date=today + datetime.timedelta(days=4),
            to_date=today + datetime.timedelta(days=6),
            reason="Medical leave.",
        )
        acct = next((s for s in staff if s.designation == "Accountant"), staff[1])
        LeaveRequest.objects.create(
            school=school, staff=acct,
            from_date=today + datetime.timedelta(days=10),
            to_date=today + datetime.timedelta(days=11),
            reason="Personal work.",
        )
        LeaveRequest.objects.create(
            school=school, staff=teacher,
            from_date=today - datetime.timedelta(days=30),
            to_date=today - datetime.timedelta(days=29),
            reason="Half-day appointment.",
            status=LeaveRequest.Status.APPROVED,
            decided_at=timezone.now(),
        )
        self.stdout.write("Leave requests ready (3).")

    def _seed_expenses(self, school, staff):
        if school.expense_requests.exists():
            return
        ExpenseRequest.objects.create(
            school=school, title="Science lab consumables",
            details="Test tubes, chemicals and beakers for Grade 3 experiments.",
            amount=15000,
            requested_by="Mr. Kamran Aslam",
        )
        ExpenseRequest.objects.create(
            school=school, title="Printer toner refill",
            details="Two black cartridges for the office printer.",
            amount=9000,
            requested_by="Ms. Farah Khan",
        )
        ExpenseRequest.objects.create(
            school=school, title="Sports day trophies",
            details="Trophies for the annual sports day winners.",
            amount=12000,
            requested_by="Mr. Bilal Qureshi",
            status=ExpenseRequest.Status.APPROVED,
            decided_at=timezone.now(),
        )
        self.stdout.write("Expense requests ready (3).")

    def _seed_fee_heads(self, school, sections):
        if school.fee_heads.exists():
            return list(school.fee_heads.all())
        head1 = FeeHead.objects.create(school=school, name="Tuition", amount=2600, frequency=FeeHead.Frequency.MONTHLY)
        head2 = FeeHead.objects.create(school=school, name="Transport", amount=1200, frequency=FeeHead.Frequency.MONTHLY)
        head3 = FeeHead.objects.create(school=school, name="Admission fee", amount=5000, frequency=FeeHead.Frequency.ONE_TIME)
        g3 = next((s for s in sections if s.grade == "Grade 3"), None)
        FeeHead.objects.create(
            school=school, name="Tuition", amount=2400,
            frequency=FeeHead.Frequency.MONTHLY,
            class_section=g3,
        )
        self.stdout.write("Fee heads ready (4).")
        return [head1, head2, head3]

    def _seed_invoices(self, school, students, heads):
        if school.fee_invoices.exists():
            return
        today = datetime.date.today()
        period = today.strftime("%B %Y")
        prev_period = (today.replace(day=1) - datetime.timedelta(days=1)).strftime("%B %Y")
        tuition = heads[0] if heads else None

        for i, student in enumerate(students):
            if student.status != Student.Status.ACTIVE:
                continue
            amount = float(student.monthly_fee)
            prev_invoice = StudentFeeInvoice.objects.create(
                school=school, student=student, fee_head=tuition,
                period=prev_period, amount=amount,
                due_date=today,
                status=StudentFeeInvoice.Status.PAID,
            )
            FeePayment.objects.create(
                invoice=prev_invoice, amount=amount,
                paid_on=today - datetime.timedelta(days=random.randint(1, 3)),
                method=FeePayment.Method.BANK,
                received_by="Front desk",
            )
            status = StudentFeeInvoice.Status.UNPAID
            if i % 3 == 1:
                status = StudentFeeInvoice.Status.PAID
            elif i % 3 == 2:
                status = StudentFeeInvoice.Status.PARTIAL
            cur_invoice = StudentFeeInvoice.objects.create(
                school=school, student=student, fee_head=tuition,
                period=period, amount=amount,
                due_date=today,
                status=status,
            )
            if status == StudentFeeInvoice.Status.PAID:
                FeePayment.objects.create(
                    invoice=cur_invoice, amount=amount,
                    paid_on=today - datetime.timedelta(days=random.randint(0, 2)),
                    method=FeePayment.Method.CASH,
                    received_by="Front desk",
                )
            elif status == StudentFeeInvoice.Status.PARTIAL:
                FeePayment.objects.create(
                    invoice=cur_invoice, amount=amount / 2,
                    paid_on=today - datetime.timedelta(days=random.randint(0, 2)),
                    method=FeePayment.Method.CASH,
                    received_by="Front desk",
                )
        self.stdout.write("Invoices + payments ready.")

    def _seed_attendance(self, school, sections):
        if school.attendance_records.exists():
            return
        today = datetime.date.today()
        count = 0
        for day_delta in range(14, -1, -1):
            day = today - datetime.timedelta(days=day_delta)
            if day.weekday() >= 5:
                continue
            for section in sections:
                enrolled = Student.objects.filter(
                    school=school, class_section=section, status=Student.Status.ACTIVE,
                ).count()
                if enrolled == 0:
                    continue
                absent = random.randint(1, max(1, enrolled // 4))
                AttendanceSnapshot.objects.create(
                    school=school, class_section=section, date=day,
                    present=max(0, enrolled - absent), absent=absent,
                )
                count += 1
        self.stdout.write(f"Attendance snapshots ready ({count}).")

    def _seed_exams(self, school, sections):
        if school.exam_records.exists():
            return
        today = datetime.date.today()
        for idx, section in enumerate(sections[:4]):
            ExamRecord.objects.create(
                school=school, class_section=section,
                exam_name=f"Term II \u2014 {section.label}",
                subject="Mathematics" if idx % 2 == 0 else "English",
                exam_date=today + datetime.timedelta(days=7 + idx * 3),
            )
        if len(sections) > 2:
            ExamRecord.objects.create(
                school=school, class_section=sections[2],
                exam_name=f"Term I \u2014 {sections[2].label}", subject="Science",
                exam_date=today - datetime.timedelta(days=20), average_pct=71.4,
            )
        self.stdout.write("Exam records ready (5).")

    def _seed_notices(self, school, principal):
        if school.notices.exists():
            return
        Notice.objects.create(
            school=school, title="Sports day \u2014 save the date",
            body="The annual sports day will be held on the last Friday of next month. Students should bring their house shirts, and parents are warmly invited.",
            audience=Notice.Audience.PARENTS, priority=Notice.Priority.IMPORTANT,
            created_by=principal,
        )
        Notice.objects.create(
            school=school, title="Staff meeting \u2014 Tuesday",
            body="Please attend the short staff meeting at 08:15 this Tuesday in the staff room to review Term II exam preparation.",
            audience=Notice.Audience.STAFF, priority=Notice.Priority.INFO,
            created_by=principal,
        )
        self.stdout.write("Notices ready (2).")

    def _seed_complaints(self, school):
        if school.complaints.exists():
            return
        Complaint.objects.create(
            school=school, complainant_name="Mrs. Sana Tariq", contact="0303 1110001",
            source=Complaint.Source.PHONE, category=Complaint.Category.TRANSPORT,
            subject="Bus late on route 2", details="The bus has been arriving 15-20 minutes late all week.",
            status=Complaint.Status.OPEN, assigned_to="Mr. Bilal Qureshi",
        )
        Complaint.objects.create(
            school=school, complainant_name="Mr. Ali Raza", contact="0303 2220002",
            source=Complaint.Source.WALK_IN, category=Complaint.Category.FACILITIES,
            subject="Borrowed library books not logged",
            details="Returned two books but they still show as borrowed on the parent portal.",
            status=Complaint.Status.IN_PROGRESS, assigned_to="Front desk",
        )
        Complaint.objects.create(
            school=school, complainant_name="Mrs. Farah Khan", contact="0303 3330003",
            source=Complaint.Source.ONLINE, category=Complaint.Category.FEES,
            subject="Duplicate fee receipt", details="Received two receipts for the same transaction.",
            status=Complaint.Status.RESOLVED, resolution_note="Refunded the duplicate. Confirmed via email.",
            resolved_at=timezone.now(),
        )
        self.stdout.write("Complaints ready (3).")

    def _seed_front_desk(self, school, staff):
        if school.front_desk_entries.exists():
            return
        now = timezone.now()
        FrontDeskEntry.objects.create(
            school=school, entry_type=FrontDeskEntry.EntryType.VISITOR,
            person="Mr. Kamran (courier)", summary="Delivered science lab equipment (3 boxes).",
            handled_by="Farah Khan", occurred_at=now - datetime.timedelta(hours=2),
        )
        FrontDeskEntry.objects.create(
            school=school, entry_type=FrontDeskEntry.EntryType.ENQUIRY,
            person="Mrs. Iqra Nadeem", summary="Asked about Grade 1 admissions for the new term. Given the application form.",
            handled_by="Farah Khan", follow_up_needed=True,
            occurred_at=now - datetime.timedelta(hours=4),
        )
        FrontDeskEntry.objects.create(
            school=school, entry_type=FrontDeskEntry.EntryType.PHONE_CALL,
            person="Parent of Hamza Ali", summary="Reported a missed bus in the morning. Escalated to transport in-charge.",
            handled_by="Farah Khan", follow_up_needed=True,
            occurred_at=now - datetime.timedelta(hours=5),
        )
        FrontDeskEntry.objects.create(
            school=school, entry_type=FrontDeskEntry.EntryType.VISITOR,
            person="Mr. Bilawal (electrician)", summary="Fix the air conditioner on the first floor.",
            handled_by="Farah Khan", occurred_at=now - datetime.timedelta(days=1),
        )
        self.stdout.write("Front desk entries ready (4).")
