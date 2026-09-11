"""Seed demo data for the Parent / Family dashboard.

Usage:
    python manage.py seed_parent_demo

Creates (or re-uses) a demo parent login ``parent`` / ``ilmkar-parent-2026``
attached to the first registered school, links TWO children and seeds the
timetable, today's attendance, class diary, homework, a graded exam and a
teacher conversation so every Parents page has data on first login.
Re-running is safe (idempotent — existing rows are re-used).
"""
import datetime

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from SAAS_admin.models import School, SchoolUser

from Parents.models import ParentChildLink, ParentPortalSetting, ParentProfile

from School_Admin.models import (
    ClassSection,
    ExamRecord,
    FeeHead,
    Student,
    StudentFeeInvoice,
    StaffMember,
)
from Teachers.models import (
    Assignment,
    ClassDiary,
    GradeEntry,
    StudentAttendance,
    TeacherMessage,
    TimetableSlot,
)

PARENT_USERNAME = "parent"
PARENT_PASSWORD = "ilmkar-parent-2026"
PARENT_NAME = "Mrs. Farah Khan"

TEACHERS = [
    ("Ms. Sana Tariq", "Senior Teacher", "Math", "sana.tariq@school.edu"),
    ("Ms. Rabia Ahmed", "Teacher", "English", "rabia.ahmed@school.edu"),
    ("Mr. Kamran Aslam", "Senior Teacher", "Science", "kamran.aslam@school.edu"),
]

CHILDREN = [
    ("ADM-2025-0001", "Ayesha Khan", "Grade 1", "A", 2800),
    ("ADM-2025-0004", "Umaima Noor", "KG", "A", 1800),
]


class Command(BaseCommand):
    help = "Seed demo data for the Parent / Family dashboard."

    def handle(self, *args, **options):
        school = School.objects.first()
        if school is None:
            self.stdout.write(self.style.WARNING(
                "No schools registered yet — nothing to seed."
            ))
            return
        today = datetime.date.today()
        weekdays = today - datetime.timedelta(days=today.weekday())
        mon = weekdays
        tue = weekdays + datetime.timedelta(days=1)

        staff = self._teachers(school)
        sections, students = self._students(school)
        parent = self._parent_user(school)
        profile = ParentProfile.objects.get_or_create(
            school=school, user=parent,
            defaults={"guardian_name": PARENT_NAME},
        )[0]
        for i, student in enumerate(students):
            ParentChildLink.objects.get_or_create(
                parent=profile, student=student,
                defaults={"relationship": "Mother", "is_primary": i == 0},
            )
        ParentPortalSetting.objects.update_or_create(
            school=school,
            defaults={"allow_online_payment": True, "allow_messaging": True},
        )

        self._timetable(school, staff, sections)
        self._attendance(school, staff, students, mon)
        self._diary_and_homework(school, staff, sections, mon)
        self._results(school, staff, students)
        self._fee(school, students, today)
        self._conversation(school, staff, profile, students[0])

        self.stdout.write(self.style.SUCCESS(
            f"Parent demo data seeded for '{school.name}'.\n"
            f"  Demo parent login: '{PARENT_USERNAME}' / '{PARENT_PASSWORD}'"
        ))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _teachers(self, school):
        """StaffMember + teacher-role SchoolUser membership for the demo teachers.
        Returns a list of StaffMember rows in the same order as ``TEACHERS``."""
        staff = []
        for full_name, designation, subject, email in TEACHERS:
            staff_member, _ = StaffMember.objects.get_or_create(
                school=school,
                email=email,
                defaults={
                    "full_name": full_name,
                    "designation": designation,
                    "department": ("Academics" if "Senior" in designation else "Primary"),
                    "phone": "+92-300-0000000",
                },
            )
            role = SchoolUser.Role.TEACHER
            SchoolUser.objects.get_or_create(
                school=school,
                user__email=email,
                defaults={
                    "user": User.objects.get_or_create(
                        username=email.split("@")[0],
                        email=email,
                        defaults={"first_name": full_name.split()[0],
                                 "last_name": " ".join(full_name.split()[1:])},
                    )[0],
                    "role": role,
                },
            )
            staff.append(staff_member)

    def _students(self, school):
        """Two demo children with active status, a KG and a Grade 1 section,
        and the guardian name set so the guardian-name fallback also works."""
        sections = {}
        for grade, section in {("KG", "A"), ("Grade 1", "A"), ("Grade 2", "A")}.items():
            key = (grade, section)
            if key not in sections:
                sec, _ = ClassSection.objects.get_or_create(
                    school=school, grade=grade, section=section,
                    defaults={"capacity": 30, "class_teacher_id": None},
                )
                sections[key] = sec

        students = []
        for admission_no, full_name, grade, section, monthly_fee in CHILDREN:
            student, _ = Student.objects.get_or_create(
                school=school,
                admission_no=admission_no,
                defaults={
                    "full_name": full_name,
                    "guardian_name": PARENT_NAME,
                    "guardian_phone": "+92-300-1111111",
                    "class_section_id": sections[(grade, section)].pk,
                    "monthly_fee": monthly_fee,
                    "admission_date": datetime.date(2025, 3, 1),
                    "status": Student.Status.ACTIVE,
                },
            )
            students.append(student)
        return sections, students
        return staff

    def _parent_user(self, school):
        """The demo parent user + a parent-role SchoolUser membership on the
        school. Password is set every run so the printed credential is live."""
        user, _ = User.objects.get_or_create(
            username=PARENT_USERNAME,
            defaults={
                "email": "farah.khan@family.edu",
                "first_name": "Farah",
                "last_name": "Khan",
            },
        )
        SchoolUser.objects.get_or_create(
            school=school,
            user=user,
            defaults={"role": SchoolUser.Role.PARENT},
        )
        user.set_password(PARENT_PASSWORD)
        user.save(update_fields=["password"])
        return user

    def _timetable(self, school, staff, sections):
        """One weekly slot for each teacher's subject across the demo sections,
        so the digest and messaging can route a subject to a real teacher."""
        staff_by_subject = {s.full_name.split()[-1]: s for s in ["Math", "English", "Science"]}
        # Build the teacher lookup by subject from the TEACHERS list + staff list
        staff_list = staff
        subject_staff = {}
        for full_name, designation, subject, _email in TEACHERS:
            for s in staff_list:
                if s.full_name == full_name:
                    subject_staff[subject] = s
                    break
        if not subject_staff:
            return
        section_list = list(sections.values())
        for day_idx, day in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri"]):
            for period in range(1, 6):
                for sec in section_list:
                    grade = sec.grade
                    if grade == "KG":
                        subject = "English" if day_idx % 2 == 0 else "Math"
                    else:
                        if period <= 2:
                            subject = "English" if period == 1 else "Math"
                        else:
                            subject = "Science" if period == 3 else ("English" if period == 4 else "Math")
                    teacher = subject_staff.get(subject)
                    if teacher is None:
                        continue
                    TimetableSlot.objects.get_or_create(
                        school=school,
                        class_section=sec,
                        day=day,
                        period=period,
                        defaults={"subject": subject, "teacher": teacher},
                    )

    def _attendance(self, school, staff, students, today):
        """Today's attendance for every child: present by default, with one
        recent absence so the digest's alert strip has something to show."""
        if not students:
            return
        teacher = staff[0] if staff else None
        for student in students:
            StudentAttendance.objects.get_or_create(
                school=school,
                student=student,
                date=today,
                defaults={"mark": StudentAttendance.Mark.PRESENT, "marked_by": teacher},
            )
        # One absence two days ago for the first child (alert demo)
        if len(students) >= 1 and teacher is not None:
            StudentAttendance.objects.get_or_create(
                school=school,
                student=students[0],
                date=today - datetime.timedelta(days=2),
                defaults={"mark": StudentAttendance.Mark.ABSENT, "marked_by": teacher},
            )