"""
Seed the Front Desk / Admissions dashboard with demo data.

Usage:
    python manage.py seed_front_desk_demo
    python manage.py seed_front_desk_demo --force   # wipe front_desk rows first

Reuses the school + students + staff created by ``seed_school_demo`` (run
that first for a full picture), then adds: admission enquiries across the
funnel (new -> contacted -> site visit -> applied -> enrolled/dropped),
visitors (one still inside), complaint/request register entries (shared
``School_Admin.Complaint`` rows the principal also sees), gate passes
(student early leave + visitor, one returned), and ID cards (student
draft + staff printed).

Creates (or re-uses) a demo front-desk login ``frontdesk`` /
``ilmkar-frontdesk-2026`` (front_desk-role membership on the first school).
"""
import datetime

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from SAAS_admin.models import School, SchoolUser

from School_Admin.models import (
    AdmissionApplication,
    Complaint,
    StaffMember,
    Student,
)
from front_desk.models import (
    AdmissionEnquiry,
    AuditLog,
    GatePass,
    IDCard,
    VisitorLog,
)

FRONT_DESK_USERNAME = "frontdesk"
FRONT_DESK_PASSWORD = "ilmkar-frontdesk-2026"


class Command(BaseCommand):
    help = "Seed demo data for the Front Desk / Admissions dashboard."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force", action="store_true",
            help="Delete existing Front Desk rows for the school first",
        )

    def handle(self, *args, **options):
        school = School.objects.first()
        if school is None:
            self.stdout.write(self.style.WARNING(
                "No schools registered yet — run seed_school_demo first "
                "(or register a school in the operator console)."
            ))
            return
        students = list(Student.objects.filter(school=school))
        if not students:
            self.stdout.write(self.style.WARNING(
                "No students on record — run seed_school_demo first."
            ))
            return
        if options["force"]:
            self._wipe(school)

        today = datetime.date.today()
        self._seed_enquiries(school, students, today)
        self._seed_visitors(school)
        self._seed_register(school)
        self._seed_gate_passes(school, students, today)
        self._seed_id_cards(school, students, today)
        AuditLog.record(
            school, "seed", "demo data seeded", "Front Desk dashboard",
            note="enquiries, visitors, register, gate passes, ID cards",
        )
        username = self._ensure_login(school)
        self.stdout.write(self.style.SUCCESS(
            f"Front Desk demo data ready for {school.name} — login "
            f"'{username}' at /frontdesk/ (password in the command source)."
        ))

    def _wipe(self, school):
        school.fd_enquiries.all().delete()
        school.fd_visitor_logs.all().delete()
        school.fd_gate_passes.all().delete()
        school.fd_id_cards.all().delete()
        school.fd_audit_logs.all().delete()
        school.complaints.all().delete()
    def _seed_enquiries(self, school, students, today):
        if school.fd_enquiries.exists():
            return
        first = [
            ("Hamza Tariq", "Mrs. Sana Tariq", "0300 1110001", "Grade 1",
             AdmissionEnquiry.Source.WALK_IN, AdmissionEnquiry.Stage.NEW,
             today + datetime.timedelta(days=2)),
            ("Areeba Yousaf", "Mr. Yousaf Ali", "0300 1110002", "KG",
             AdmissionEnquiry.Source.PHONE, AdmissionEnquiry.Stage.CONTACTED,
             today + datetime.timedelta(days=3)),
            ("Muhammad Danyal", "Mr. Rana Danyal", "0300 1110003", "Grade 3",
             AdmissionEnquiry.Source.REFERRAL, AdmissionEnquiry.Stage.SITE_VISIT,
             today + datetime.timedelta(days=5)),
            ("Iqra Nadeem", "Mrs. Nadeem Akhtar", "0300 1110004", "Grade 2",
             AdmissionEnquiry.Source.ONLINE, AdmissionEnquiry.Stage.APPLIED,
             today + datetime.timedelta(days=1)),
        ]
        for name, guardian, phone, grade, source, stage, followup in first:
            AdmissionEnquiry.objects.create(
                school=school, applicant_name=name, guardian_name=guardian,
                guardian_phone=phone, interested_grade=grade, source=source,
                stage=stage, follow_up_date=followup,
                follow_up_note="Call after result day", notes="Demo lead",
                assigned_to=FRONT_DESK_USERNAME, created_by="seed",
            )
        # One lead that already enrolled (link the first student) and one
        # that dropped off — the funnel needs both lifecycle ends.
        enrolled = AdmissionEnquiry.objects.create(
            school=school, applicant_name=students[0].full_name,
            guardian_name=students[0].guardian_name,
            guardian_phone=students[0].guardian_phone,
            interested_grade=students[0].class_section.label
            if students[0].class_section_id else "",
            source=AdmissionEnquiry.Source.WALK_IN,
            stage=AdmissionEnquiry.Stage.ENROLLED,
            student=students[0], assigned_to=FRONT_DESK_USERNAME,
            created_by="seed",
        )
        dropped = AdmissionEnquiry.objects.create(
            school=school, applicant_name="Raza Ahmed",
            guardian_name="Mr. Ahmed Nawaz", guardian_phone="0300 1110005",
            interested_grade="Playgroup", source=AdmissionEnquiry.Source.PHONE,
            stage=AdmissionEnquiry.Stage.DROPPED,
            notes="[seed] Withdrew — chose another school",
            assigned_to=FRONT_DESK_USERNAME, created_by="seed",
        )
        # Link the applied-stage lead to a shared AdmissionApplication row.
        applied = school.fd_enquiries.filter(
            stage=AdmissionEnquiry.Stage.APPLIED
        ).first()
        if applied is not None:
            applied.application = AdmissionApplication.objects.create(
                school=school, applicant_name=applied.applicant_name,
                guardian_name=applied.guardian_name,
                guardian_phone=applied.guardian_phone,
                note="Created by front desk from demo enquiry",
            )
            applied.save(update_fields=["application"])
        self.stdout.write(
            f"Enquiries ready ({school.fd_enquiries.count()}): "
            f"enrolled {enrolled.applicant_name}, dropped {dropped.applicant_name}."
        )
    def _seed_visitors(self, school):
        if school.fd_visitor_logs.exists():
            return
        VisitorLog.objects.create(
            school=school, visitor_name="Mr. Imran Khan",
            contact="0300 2220001", id_number="35202-1234567-1",
            purpose=VisitorLog.Purpose.MEETING, whom_to_meet="Principal",
            badge_no="V-14", entered_at=timezone.now() - datetime.timedelta(hours=1),
            notes="Interview scheduled", handled_by=FRONT_DESK_USERNAME,
        )
        VisitorLog.objects.create(
            school=school, visitor_name="Courier — TCS",
            contact="—", purpose=VisitorLog.Purpose.DELIVERY,
            badge_no="V-15", entered_at=timezone.now() - datetime.timedelta(minutes=40),
            handled_by=FRONT_DESK_USERNAME,
        )
        VisitorLog.objects.create(
            school=school, visitor_name="Mr. Salman Butt",
            contact="0300 2220002", purpose=VisitorLog.Purpose.ADMISSION,
            whom_to_meet="Front desk", badge_no="V-12",
            entered_at=timezone.now() - datetime.timedelta(hours=3),
            exited_at=timezone.now() - datetime.timedelta(hours=2),
            notes="Picked up admission form", handled_by=FRONT_DESK_USERNAME,
        )
        self.stdout.write(
            f"Visitors ready (inside: "
            f"{school.fd_visitor_logs.filter(exited_at__isnull=True).count()})."
        )

    def _seed_register(self, school):
        if school.complaints.exists():
            return
        Complaint.objects.create(
            school=school, complainant_name="Mrs. Farheen Javed",
            contact="0300 3330001", source=Complaint.Source.WALK_IN,
            category=Complaint.Category.FACILITIES,
            subject="Classroom fan not working (Grade 2-B)",
            details="Requesting repair — warm for the morning shift.",
            assigned_to="Maintenance", status=Complaint.Status.IN_PROGRESS,
        )
        Complaint.objects.create(
            school=school, complainant_name="Mr. Asad Mehmood",
            source=Complaint.Source.PHONE, category=Complaint.Category.REQUEST,
            subject="Request: duplicate fee challan copy",
            details="Needs a soft copy of last month's challan for reimbursement.",
            status=Complaint.Status.OPEN,
        )
        Complaint.objects.create(
            school=school, complainant_name="Mrs. Uzma Riaz",
            source=Complaint.Source.WALK_IN, category=Complaint.Category.TRANSPORT,
            subject="Van late on Route 2",
            details="Van arrived 25 minutes late this morning.",
            status=Complaint.Status.RESOLVED,
            resolution_note="Re-routed; driver warned (seed demo).",
            resolved_at=timezone.now(),
        )
        self.stdout.write("Register seeded (requests + complaints).")

    def _seed_gate_passes(self, school, students, today):
        if school.fd_gate_passes.exists():
            return
        GatePass.objects.get_or_create(
            school=school, pass_no="GP-2026-0001",
            defaults=dict(
                pass_type=GatePass.PassType.STUDENT_EARLY, student=students[0],
                reason="Medical appointment — dentist",
                issued_to=students[0].guardian_name, issued_by=FRONT_DESK_USERNAME,
                expected_return=timezone.now() + datetime.timedelta(hours=2),
                status=GatePass.Status.ACTIVE,
            ),
        )
        GatePass.objects.get_or_create(
            school=school, pass_no="GP-2026-0002",
            defaults=dict(
                pass_type=GatePass.PassType.VISITOR, visitor_name="Mr. Salman Butt",
                contact="0300 2220002", reason="Admission meeting",
                issued_to="Self", issued_by=FRONT_DESK_USERNAME,
                expected_return=timezone.now() + datetime.timedelta(hours=1),
                status=GatePass.Status.ACTIVE,
            ),
        )
        GatePass.objects.get_or_create(
            school=school, pass_no="GP-2026-0003",
            defaults=dict(
                pass_type=GatePass.PassType.VISITOR, visitor_name="TCS Courier",
                reason="Lab equipment delivery", issued_by=FRONT_DESK_USERNAME,
                status=GatePass.Status.RETURNED,
                returned_at=timezone.now() - datetime.timedelta(hours=1),
            ),
        )
        self.stdout.write("Gate passes ready (2 active, 1 returned).")
    def _seed_id_cards(self, school, students, today):
        if school.fd_id_cards.exists():
            return
        student = students[0]
        IDCard.objects.get_or_create(
            school=school, card_no="IC-2026-0001",
            defaults=dict(
                holder_type=IDCard.HolderType.STUDENT, student=student,
                holder_name=student.full_name,
                holder_line=student.class_section.label
                if student.class_section_id else "Student",
                admission_no=student.admission_no,
                guardian_phone=student.guardian_phone,
                issued_on=today, expires_on=today + datetime.timedelta(days=365),
                status=IDCard.Status.DRAFT, created_by=FRONT_DESK_USERNAME,
            ),
        )
        staff = StaffMember.objects.filter(school=school).first()
        if staff is not None:
            IDCard.objects.get_or_create(
                school=school, card_no="IC-2026-0002",
                defaults=dict(
                    holder_type=IDCard.HolderType.STAFF, staff=staff,
                    holder_name=staff.full_name,
                    holder_line=staff.designation or "Staff",
                    issued_on=today,
                    expires_on=today + datetime.timedelta(days=365),
                    status=IDCard.Status.PRINTED, created_by=FRONT_DESK_USERNAME,
                    printed_at=timezone.now(),
                ),
            )
        self.stdout.write("ID cards ready (1 draft, 1 printed).")

    def _ensure_login(self, school):
        user, created = User.objects.get_or_create(
            username=FRONT_DESK_USERNAME,
            defaults={"email": "frontdesk@ilmkar.pk"},
        )
        if created:
            user.set_password(FRONT_DESK_PASSWORD)
            user.save()
        SchoolUser.objects.get_or_create(
            school=school, user=user,
            defaults={"role": SchoolUser.Role.FRONT_DESK},
        )
        return user.get_username()
        # Leave the linked AdmissionApplications in place (shared record).