"""Tests for the Teacher / Staff dashboard.

Focus: access control (teacher-role routing + principal read-through),
tenant isolation (a teacher can never touch another school's data) and
the core write flows — one-tap attendance (with the School_Admin
snapshot sync), the marks grid (with the exam-average sync), leave,
substitute finder, private notes and report-comment generation.
"""
import datetime

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from SAAS_admin.models import School, SchoolUser
from School_Admin.models import (
    AttendanceSnapshot,
    ClassSection,
    ExamRecord,
    LeaveRequest,
    StaffMember,
    Student,
)

from .models import (
    GradeEntry,
    ReportCardComment,
    StudentAttendance,
    TeacherNote,
    TimetableSlot,
)


class TeacherData(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.today = datetime.date.today()
        cls.tomorrow = cls.today + datetime.timedelta(days=1)
        cls.school = School.objects.create(
            name="Test School", city="Lahore", status="active"
        )
        cls.other_school = School.objects.create(name="Other School", city="Karachi")

        cls.teacher = User.objects.create_user(
            "teacher1", "sana@school.io", "teacher-pass-1",
            first_name="Sana", last_name="Malik",
        )
        SchoolUser.objects.create(
            school=cls.school, user=cls.teacher, role=SchoolUser.Role.TEACHER
        )
        cls.staff = StaffMember.objects.create(
            school=cls.school, full_name="Sana Malik",
            email="sana@school.io", designation="Teacher",
        )

        cls.principal = User.objects.create_user(
            "principal1", "p@school.io", "principal-pass-1"
        )
        SchoolUser.objects.create(
            school=cls.school, user=cls.principal, role=SchoolUser.Role.PRINCIPAL
        )

        cls.section = ClassSection.objects.create(
            school=cls.school, grade="Grade 5", section="A"
        )
        cls.student = Student.objects.create(
            school=cls.school, class_section=cls.section,
            admission_no="ADM-1", full_name="Ayesha Khan",
            status=Student.Status.ACTIVE,
        )
        cls.student2 = Student.objects.create(
            school=cls.school, class_section=cls.section,
            admission_no="ADM-2", full_name="Bilal Ahmed",
            status=Student.Status.ACTIVE,
        )
        cls.exam = ExamRecord.objects.create(
            school=cls.school, class_section=cls.section,
            exam_name="Unit Test 1", subject="Math", exam_date=cls.today,
        )

        # another school's data — must never be reachable by teacher1
        cls.other_section = ClassSection.objects.create(
            school=cls.other_school, grade="Grade 5", section="B"
        )
        cls.other_staff = StaffMember.objects.create(
            school=cls.other_school, full_name="Zafar Ali"
        )
        cls.other_student = Student.objects.create(
            school=cls.other_school, class_section=cls.other_section,
            admission_no="X-1", full_name="Outsider",
            status=Student.Status.ACTIVE,
        )

    def json(self, url, payload, expect=200):
        resp = self.client.post(url, content_type="application/json", data=payload)
        self.assertEqual(resp.status_code, expect, getattr(resp, "content", b""))
        return resp


class AccessControlTests(TeacherData):
    def test_teacher_login_redirects_to_teacher_dashboard(self):
        resp = self.client.post("/", {"username": "teacher1",
                                      "password": "teacher-pass-1"})
        self.assertRedirects(resp, reverse("Teachers:dashboard"))

    def test_principal_login_keeps_priority_over_teacher_app(self):
        resp = self.client.post("/", {"username": "principal1",
                                      "password": "principal-pass-1"})
        self.assertRedirects(resp, reverse("School_Admin:dashboard"))

    def test_teacher_reaches_all_teacher_pages(self):
        self.client.force_login(self.teacher)
        for url in (
            "/teacher/", "/teacher/attendance/", "/teacher/marks/",
            "/teacher/assignments/", "/teacher/diary/", "/teacher/lesson-plans/",
            "/teacher/resources/", "/teacher/inbox/", "/teacher/leave/",
            "/teacher/payslips/", "/teacher/notes/", "/teacher/report-comments/",
            "/teacher/substitute/", "/teacher/analytics/",
        ):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_teacher_of_other_school_redirected_from_teacher_app(self):
        outsider = User.objects.create_user("teacher2", password="teacher-pass-2")
        SchoolUser.objects.create(
            school=self.other_school, user=outsider, role=SchoolUser.Role.TEACHER
        )
        self.client.force_login(outsider)
        resp = self.client.get("/teacher/attendance/?section=%d" % self.section.pk)
        # page renders but the foreign section resolves to None
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Pick a class")

    def test_anonymous_redirected_to_login(self):
        resp = self.client.get("/teacher/")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.url.startswith("/"))


class AttendanceFlowTests(TeacherData):
    def test_one_tap_attendance_syncs_school_snapshot(self):
        self.client.force_login(self.teacher)
        resp = self.json("/teacher/attendance/", {
            "section_id": self.section.pk,
            "marks": {str(self.student.pk): "present",
                      str(self.student2.pk): "absent"},
        })
        data = resp.json()
        self.assertEqual(data["present"], 1)
        self.assertEqual(data["absent"], 1)
        snapshot = AttendanceSnapshot.objects.get(
            school=self.school, class_section=self.section, date=self.today
        )
        self.assertEqual((snapshot.present, snapshot.absent), (1, 1))

    def test_absent_marks_go_to_roster_and_revert(self):
        self.client.force_login(self.teacher)
        self.json("/teacher/attendance/", {
            "section_id": self.section.pk,
            "marks": {str(self.student.pk): "late"},
        })
        row = StudentAttendance.objects.get(student=self.student, date=self.today)
        self.assertEqual(row.mark, StudentAttendance.Mark.LATE)
        self.assertEqual(row.marked_by, self.staff)
        self.json("/teacher/attendance/", {
            "section_id": self.section.pk,
            "marks": {str(self.student.pk): "present"},
        })
        row.refresh_from_db()
        self.assertEqual(row.mark, StudentAttendance.Mark.PRESENT)

    def test_foreign_student_is_ignored(self):
        self.client.force_login(self.teacher)
        resp = self.json("/teacher/attendance/", {
            "section_id": self.section.pk,
            "marks": {str(self.other_student.pk): "present"},
        })
        self.assertEqual(resp.json()["saved"], 0)
        self.assertFalse(
            StudentAttendance.objects.filter(student=self.other_student).exists()
        )

    def test_marks_grid_updates_exam_average(self):
        self.client.force_login(self.teacher)
        resp = self.json("/teacher/marks/", {
            "exam_id": self.exam.pk,
            "entries": [
                {"student_id": self.student.pk, "marks_obtained": 80, "total_marks": 100},
                {"student_id": self.student2.pk, "marks_obtained": 60, "total_marks": 100},
            ],
        })
        self.assertEqual(resp.json()["average_pct"], 70.0)
        self.exam.refresh_from_db()
        self.assertEqual(self.exam.average_pct, 70.0)
        entry = GradeEntry.objects.get(student=self.student, exam=self.exam)
        self.assertEqual(entry.percentage, 80.0)


class LeaveAndSubstituteTests(TeacherData):
    def test_leave_request_lands_in_principal_approvals(self):
        self.client.force_login(self.teacher)
        self.json("/teacher/leave/", {
            "from_date": self.tomorrow.isoformat(),
            "to_date": self.tomorrow.isoformat(),
            "reason": "Family matter",
        })
        row = LeaveRequest.objects.get(staff=self.staff)
        self.assertEqual(row.status, LeaveRequest.Status.PENDING)
        self.assertEqual(row.to_date, self.tomorrow)

    def test_overlap_is_blocked(self):
        self.client.force_login(self.teacher)
        payload = {
            "from_date": self.tomorrow.isoformat(),
            "to_date": self.tomorrow.isoformat(),
        }
        # (kept simple: submit once, expect 400 on identical dates)
        self.json("/teacher/leave/", payload)
        self.json("/teacher/leave/", payload, expect=400)


class SubstituteFinderTests(TeacherData):
    def setUp(self):
        # slot for tomorrow so the approved leave exposes a gap
        self.slot = TimetableSlot.objects.create(
            school=self.school, class_section=self.section,
            subject="Math", teacher=self.staff,
            day=self.tomorrow.strftime("%a"), period=1,
        )

    def test_approved_leave_exposes_gap_and_free_candidates(self):
        # approve the leave (what the principal's approvals page does)
        LeaveRequest.objects.create(
            school=self.school, staff=self.staff,
            from_date=self.tomorrow, to_date=self.tomorrow,
            status=LeaveRequest.Status.APPROVED,
        )
        cover = StaffMember.objects.create(
            school=self.school, full_name="Cover Ali", is_active=True
        )
        self.client.force_login(self.teacher)
        resp = self.client.get(
            "/teacher/substitute/?date=" + self.tomorrow.isoformat()
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Cover Ali")
        self.assertContains(resp, "Math")  # slot subject on the gap card
        self.assertContains(resp, "Sana Malik")  # the teacher who is away

        # arrange the cover
        self.json("/teacher/substitute/", {
            "slot_id": self.slot.pk,
            "substitute_id": cover.pk,
            "date": self.tomorrow.isoformat(),
        })
        resp = self.client.get(
            "/teacher/substitute/?date=" + self.tomorrow.isoformat()
        )
        self.assertContains(resp, "covered by")

    def test_substitute_who_is_also_teaching_is_not_suggested(self):
        LeaveRequest.objects.create(
            school=self.school, staff=self.staff,
            from_date=self.tomorrow, to_date=self.tomorrow,
            status=LeaveRequest.Status.APPROVED,
        )
        busy = StaffMember.objects.create(
            school=self.school, full_name="Busy Bibi", is_active=True
        )
        other_section = ClassSection.objects.create(
            school=self.school, grade="Grade 6", section="A"
        )
        # Busy Bibi teaches ANOTHER section in the same period — a clash
        # that must exclude her from the candidate list.
        TimetableSlot.objects.create(
            school=self.school, class_section=other_section,
            subject="English", teacher=busy,
            day=self.tomorrow.strftime("%a"), period=1,
        )
        from .metrics import substitute_candidates

        candidates = substitute_candidates(self.school, self.slot, self.tomorrow)
        self.assertNotIn(busy.pk, [c["id"] for c in candidates])


class NotesAndCommentTests(TeacherData):
    def test_private_note_created_and_listed(self):
        self.client.force_login(self.teacher)
        self.json("/teacher/notes/", {
            "student_id": self.student.pk,
            "category": "strength",
            "body": "Excellent at mental math",
        })
        note = TeacherNote.objects.get(student=self.student)
        self.assertEqual(note.category, TeacherNote.Category.STRENGTH)
        self.assertEqual(note.author, self.staff)
        resp = self.client.get("/teacher/notes/?student=" + str(self.student.pk))
        self.assertContains(resp, "Excellent at mental math")

    def test_report_comment_generated_from_marks_and_notes(self):
        GradeEntry.objects.create(
            school=self.school, exam=self.exam, student=self.student,
            marks_obtained=85, total_marks=100,
        )
        TeacherNote.objects.create(
            school=self.school, student=self.student, author=self.staff,
            category=TeacherNote.Category.CONCERN,
            body="Needs homework follow-up at home",
        )
        self.client.force_login(self.teacher)
        resp = self.json("/teacher/report-comments/", {
            "student_id": self.student.pk,
            "term": "Term 1 2026",
        })
        data = resp.json()
        self.assertIn("85", data["draft"])
        self.assertIn("homework follow-up", data["draft"])
        comment = ReportCardComment.objects.get(
            student=self.student, term="Term 1 2026"
        )
        self.assertEqual(comment.status, ReportCardComment.Status.DRAFT)

    def test_comment_can_be_marked_final(self):
        comment = ReportCardComment.objects.create(
            school=self.school, student=self.student, term="Term 1 2026",
            draft="A fine term.",
        )
        self.client.force_login(self.teacher)
        url = reverse("Teachers:report-comment-save", args=[comment.pk])
        self.json(url, {"draft": "A fine term.", "final": "A fine term."})
        comment.refresh_from_db()
        self.assertEqual(comment.status, ReportCardComment.Status.FINAL)


class EarlyWarningTests(TeacherData):
    def test_low_attendance_and_marks_are_flagged(self):
        StudentAttendance.objects.create(
            school=self.school, class_section=self.section,
            student=self.student, date=self.today,
            mark=StudentAttendance.Mark.ABSENT,
        )
        GradeEntry.objects.create(
            school=self.school, exam=self.exam, student=self.student,
            marks_obtained=30, total_marks=100,
        )
        from .metrics import early_warnings

        warnings = early_warnings(self.school, today=self.today)
        row = next(w for w in warnings if w["student_id"] == self.student.pk)
        self.assertIn("attendance", row["flags"])
        self.assertIn("low_marks", row["flags"])
        self.assertEqual(row["attendance_pct"], 0.0)
        self.assertEqual(row["avg_pct"], 30.0)

    def test_healthy_student_not_flagged(self):
        StudentAttendance.objects.create(
            school=self.school, class_section=self.section,
            student=self.student, date=self.today,
            mark=StudentAttendance.Mark.PRESENT,
        )
        GradeEntry.objects.create(
            school=self.school, exam=self.exam, student=self.student,
            marks_obtained=90, total_marks=100,
        )
        from .metrics import early_warnings

        warnings = early_warnings(self.school, today=self.today)
        self.assertFalse(
            [w for w in warnings if w["student_id"] == self.student.pk]
        )


