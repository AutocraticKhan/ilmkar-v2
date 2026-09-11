"""
Seed the HR / People dashboard with demo data.

Usage:
    python manage.py seed_hr_demo
    python manage.py seed_hr_demo --force   # wipe HR rows first

Reuses the school + staff created by ``seed_school_demo`` (run that
first for a full picture), then adds: employment contracts, staff
documents (some expiring/expired for the alert feed), this month's
attendance grid with a few absents, leave requests (one pending, one
approved) + balances, a job posting with applicants and a scheduled
interview, onboarding checklists, an appraisal, a training program with
enrollments, and generated payroll inputs for the current period.

Creates (or re-uses) a demo HR login ``hr`` / ``ilmkar-hr-2026``
(hr-role membership on the first school).
"""
import datetime
import random

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from SAAS_admin.models import School, SchoolUser

from HR.models import (
    Appraisal,
    AttendanceRecord,
    AuditLog,
    JobApplication,
    JobPosting,
    Interview,
    LeaveBalance,
    OnboardingChecklist,
    PayrollInput,
    StaffContract,
    StaffDocument,
    TrainingEnrollment,
    TrainingProgram,
)
from HR.services import current_period, generate_inputs, start_onboarding
from School_Admin.models import LeaveRequest, StaffMember

HR_USERNAME = "hr"
HR_PASSWORD = "ilmkar-hr-2026"


class Command(BaseCommand):
    help = "Seed demo data for the HR / People dashboard."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force", action="store_true",
            help="Delete existing HR rows for the school first",
        )

    def handle(self, *args, **options):
        school = School.objects.first()
        if school is None:
            self.stdout.write(self.style.WARNING(
                "No schools registered yet — run seed_school_demo first "
                "(or register a school in the operator console)."
            ))
            return
        staff = list(StaffMember.objects.filter(school=school))
        if not staff:
            self.stdout.write(self.style.WARNING(
                "No staff on record — run seed_school_demo first."
            ))
            return
        if options["force"]:
            self._wipe(school)

        today = datetime.date.today()
        self._seed_contracts(school, staff, today)
        self._seed_documents(school, staff, today)
        self._seed_attendance(school, staff, today)
        self._seed_leaves(school, staff, today)
        self._seed_recruitment(school, staff, today)
        self._seed_onboarding(school, staff)
        self._seed_appraisals(school, staff)
        self._seed_training(school, staff, today)
        result = generate_inputs(school, current_period(today))
        AuditLog.record(
            school, "seed", "demo data seeded", "HR dashboard",
            note=f"{result['created']} payroll input rows generated",
        )
        username = self._ensure_login(school)
        self.stdout.write(self.style.SUCCESS(
            f"HR demo data ready for {school.name} — login '{username}' "
            f"at /hr/ (password in the command source)."
        ))

    def _wipe(self, school):
        PayrollInput.objects.filter(school=school).delete()
        TrainingEnrollment.objects.filter(school=school).delete()
        TrainingProgram.objects.filter(school=school).delete()
        Appraisal.objects.filter(school=school).delete()
        OnboardingChecklist.objects.filter(school=school).delete()
        Interview.objects.filter(school=school).delete()
        JobApplication.objects.filter(school=school).delete()
        JobPosting.objects.filter(school=school).delete()
        LeaveBalance.objects.filter(school=school).delete()
        AttendanceRecord.objects.filter(school=school).delete()
        StaffDocument.objects.filter(school=school).delete()
        StaffContract.objects.filter(school=school).delete()
        AuditLog.objects.filter(school=school).delete()

    def _seed_contracts(self, school, staff, today):
        for index, member in enumerate(staff):
            if member.contracts.exists():
                continue
            salary = 45000 + index * 5000
            end_date = (
                # A couple of fixed-term contracts, one already lapsed
                today + datetime.timedelta(days=30 * (6 + index))
                if index % 3 == 0 else None
            )
            if index == len(staff) - 1:
                end_date = today - datetime.timedelta(days=5)
            StaffContract.objects.create(
                school=school,
                staff=member,
                kind=(
                    StaffContract.Kind.PERMANENT if index % 2 == 0
                    else StaffContract.Kind.CONTRACT
                ),
                start_date=member.join_date or datetime.date(2023, 8, 1),
                end_date=end_date,
                monthly_salary=salary,
            )

    def _seed_documents(self, school, staff, today):
        specs = [
            ("certification", "First-Aid certification", 45, 20),
            ("cnic", "CNIC copy", -10, None),          # expired
            ("degree", "B.Ed degree", 900, None),
            ("certification", "Subject specialist cert.", 15, 30),  # expiring
        ]
        for index, member in enumerate(staff):
            kind, title, in_days, issued_days = specs[index % len(specs)]
            if member.hr_documents.exists():
                continue
            StaffDocument.objects.create(
                school=school,
                staff=member,
                kind=kind,
                title=f"{title} — {member.full_name.split()[0]}",
                number=f"DOC-{1000 + index}",
                issued_on=today - datetime.timedelta(days=issued_days or 365),
                expiry_date=(
                    today + datetime.timedelta(days=in_days)
                    if in_days is not None else None
                ),
            )

    def _seed_attendance(self, school, staff, today):
        rng = random.Random(7)
        first_of_month = today.replace(day=1)
        statuses = (
            AttendanceRecord.Status.PRESENT, AttendanceRecord.Status.PRESENT,
            AttendanceRecord.Status.PRESENT, AttendanceRecord.Status.LATE,
            AttendanceRecord.Status.ABSENT, AttendanceRecord.Status.HALF_DAY,
        )
        for day_offset in range((today - first_of_month).days + 1):
            day = first_of_month + datetime.timedelta(days=day_offset)
            if day.weekday() >= 5:
                continue  # weekends off
            for index, member in enumerate(staff):
                status = statuses[rng.randrange(len(statuses))]
                if index == 1 and day.day % 9 == 0:
                    status = AttendanceRecord.Status.ABSENT  # repeat offender
                AttendanceRecord.objects.get_or_create(
                    school=school, staff=member, date=day,
                    defaults={
                        "status": status,
                        "unpaid": (
                            status == AttendanceRecord.Status.ABSENT
                            and index % 2 == 0
                        ),
                        "marked_by": "seed",
                    },
                )

    def _seed_leaves(self, school, staff, today):
        if not LeaveRequest.objects.filter(school=school).exists():
            member = staff[0]
            LeaveRequest.objects.create(
                school=school,
                staff=member,
                from_date=today + datetime.timedelta(days=7),
                to_date=today + datetime.timedelta(days=9),
                reason="Family wedding — pending HR decision",
            )
            LeaveRequest.objects.create(
                school=school,
                staff=staff[-1],
                from_date=today - datetime.timedelta(days=14),
                to_date=today - datetime.timedelta(days=13),
                reason="Sick leave (approved)",
                status=LeaveRequest.Status.APPROVED,
                decision_note="Get well soon",
                decided_at=None,
            )
        LeaveBalance.objects.get_or_create(
            school=school, staff=staff[0],
            year=today.year, defaults={"entitled": 20, "carried_over": 4},
        )

    def _seed_recruitment(self, school, staff, today):
        posting = JobPosting.objects.filter(school=school, title__contains="Physics").first()
        if posting is None:
            posting = JobPosting.objects.create(
                school=school,
                title="Physics Teacher (Secondary)",
                department="Secondary",
                openings=1,
                description="O/A-Level Physics; lab handling experience preferred.",
                posted_on=today - datetime.timedelta(days=12),
                closes_on=today + datetime.timedelta(days=18),
            )
        if not posting.applications.exists():
            applicants = [
                ("Hina Rauf", "shortlisted", "4 years, Beaconhouse"),
                ("Usman Tariq", "new", "Fresh MPhil"),
            ]
            for name, stage, experience in applicants:
                JobApplication.objects.create(
                    school=school,
                    posting=posting,
                    candidate_name=name,
                    experience=experience,
                    stage=stage,
                    phone="0300-0000000",
                )
            app = posting.applications.first()
            Interview.objects.create(
                school=school,
                application=app,
                round_no=1,
                scheduled_on=today + datetime.timedelta(days=3),
                scheduled_at="10:00",
                interviewer="Principal",
            )

    def _seed_onboarding(self, school, staff):
        # The most recently joined staff member gets a half-done checklist.
        member = staff[-1]
        start_onboarding(school, member, due_date=None)
        for task in member.onboarding_tasks.all()[:2]:
            task.is_done = True
            task.save(update_fields=["is_done"])

    def _seed_appraisals(self, school, staff):
        member = staff[0]
        period = f"{datetime.date.today().year - 1}-" \
                 f"{str(datetime.date.today().year)[2:]}"
        Appraisal.objects.get_or_create(
            school=school, staff=member, period=period,
            defaults={
                "reviewer": "Principal",
                "scores": {
                    "teaching": 4, "discipline": 4, "teamwork": 5,
                    "punctuality": 3, "growth": 4,
                },
                "rating": 4.0,
                "strengths": "Strong classroom control; mentors juniors.",
                "improvements": "Punctuality slipped this term.",
            },
        )

    def _seed_training(self, school, staff, today):
        program = TrainingProgram.objects.filter(school=school).first()
        if program is None:
            program = TrainingProgram.objects.create(
                school=school,
                title="Classroom Assessment Workshop",
                kind=TrainingProgram.Kind.WORKSHOP,
                provider="Teachers Resource Centre",
                start_date=today + datetime.timedelta(days=10),
                end_date=today + datetime.timedelta(days=11),
                cost_per_head=3500,
            )
        for member in staff[:2]:
            TrainingEnrollment.objects.get_or_create(
                school=school, program=program, staff=member
            )

    def _ensure_login(self, school):
        user, created = User.objects.get_or_create(
            username=HR_USERNAME,
            defaults={"email": "hr@ilmkar.pk"},
        )
        if created:
            user.set_password(HR_PASSWORD)
            user.save()
        SchoolUser.objects.get_or_create(
            school=school, user=user,
            defaults={"role": SchoolUser.Role.HR},
        )
        return user.get_username()


