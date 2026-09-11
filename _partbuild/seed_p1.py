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