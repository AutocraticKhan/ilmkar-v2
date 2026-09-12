"""Tests for the Chain / Group Owner dashboard.

Focus: access control, tenant isolation (an owner can never see or touch
schools outside their chain) and the core write flows.
"""
import datetime

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from SAAS_admin.models import School
from School_Admin.models import (
    AttendanceSnapshot as SchoolAttendanceSnapshot,
    ClassSection,
    ExamRecord,
    FeePayment,
    Student as SchoolStudent,
    StudentFeeInvoice,
)

from .metrics import branch_metrics, consolidated, scorecard
from .models import (
    ApprovalRequest, Chain, Classroom, GroupPolicy, JobPosting, Student,
    StaffMember, TransferLog,
)


class ChainData(TestCase):
    """Two chains with their own branches + one independent school."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("owner1", password="ilmkar-owner-pass-1")
        cls.other = User.objects.create_user("owner2", password="ilmkar-owner-pass-2")
        cls.chain = Chain.objects.create(name="Group One", owner=cls.owner)
        cls.other_chain = Chain.objects.create(name="Group Two", owner=cls.other)
        cls.branch_a = School.objects.create(name="G1-A", city="Lahore", chain=cls.chain)
        cls.branch_b = School.objects.create(name="G1-B", city="Karachi", chain=cls.chain)
        cls.foreign = School.objects.create(name="G2-X", city="Islamabad", chain=cls.other_chain)
        cls.room_a = Classroom.objects.create(school=cls.branch_a, name="Room A", capacity=30)
        cls.student = Student.objects.create(school=cls.branch_a, classroom=cls.room_a,
                                             full_name="Ayesha Khan", monthly_fee=3500)
        cls.other_student = Student.objects.create(school=cls.foreign, full_name="Outsider")
        cls.staff = StaffMember.objects.create(school=cls.branch_a, full_name="Kamran Raza")

    def json(self, url, payload, expect=200):
        resp = self.client.post(url, content_type="application/json", data=payload)
        self.assertEqual(resp.status_code, expect, getattr(resp, "content", b""))
        return resp


class AccessControlTests(ChainData):
    def test_owner_login_redirects_to_chain_dashboard(self):
        resp = self.client.post("/", {"username": "owner1",
                                      "password": "ilmkar-owner-pass-1"})
        self.assertRedirects(resp, reverse("school_owner:dashboard"))

    def test_superuser_login_goes_to_operator_console(self):
        User.objects.create_superuser("admin", "admin@x.io", "admin-pass-123")
        resp = self.client.post("/", {"username": "admin",
                                      "password": "admin-pass-123"})
        self.assertRedirects(resp, reverse("SAAS_admin:dashboard"))

    def test_owner_reaches_all_owner_pages(self):
        self.client.force_login(self.owner)
        for url in ("/chain/", "/chain/financials/", "/chain/transfers/",
                    "/chain/policies/", "/chain/hiring/",
                    "/chain/announcements/", "/chain/approvals/"):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_non_owner_redirected_to_login(self):
        User.objects.create_user("plain", password="plain-pass-123")
        self.client.force_login(User.objects.get(username="plain"))
        resp = self.client.get("/chain/")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.url.startswith("/"))  # back to the login page

    def test_school_user_login_gets_friendly_error_not_crash(self):
        """Regression: a valid non-console account must get the form back
        with a clear message — not a 500 from the reverse OneToOne accessor."""
        User.objects.create_user("suser", password="suser-pass-123")
        resp = self.client.post(
            "/", {"username": "suser", "password": "suser-pass-123"}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "sign in to a console")

    def test_anonymous_redirected_to_login(self):
        self.assertEqual(self.client.get("/chain/").status_code, 302)


class IsolationTests(ChainData):
    def setUp(self):
        self.client.force_login(self.owner)

    def test_dashboard_lists_only_own_branches(self):
        resp = self.client.get("/chain/")
        self.assertContains(resp, "G1-A")
        self.assertNotContains(resp, "G2-X")

    def test_transfer_rejects_foreign_source_and_target(self):
        self.json("/chain/transfers/move/", {
            "person_type": "student", "person_id": self.other_student.pk,
            "from_school_id": self.foreign.pk, "to_school_id": self.branch_a.pk,
        }, expect=400)
        self.json("/chain/transfers/move/", {
            "person_type": "student", "person_id": self.student.pk,
            "from_school_id": self.branch_a.pk, "to_school_id": self.foreign.pk,
        }, expect=400)
        self.student.refresh_from_db()
        self.assertEqual(self.student.school_id, self.branch_a.pk)

    def test_policy_override_rejects_foreign_branch(self):
        policy = GroupPolicy.objects.create(chain=self.chain, name="Fee", default_value="x")
        self.json(f"/chain/policies/{policy.pk}/override/",
                  {"school_id": self.foreign.pk, "value": "hacked"}, expect=400)
        self.assertEqual(policy.overrides.count(), 0)

    def test_cannot_decide_foreign_chain_request(self):
        foreign_req = ApprovalRequest.objects.create(
            chain=self.other_chain, school=self.foreign, title="Foreign req")
        self.json(f"/chain/approvals/{foreign_req.pk}/decide/",
                  {"decision": "approved"}, expect=404)
        foreign_req.refresh_from_db()
        self.assertEqual(foreign_req.status, ApprovalRequest.Status.PENDING)

    def test_hiring_fill_rejects_foreign_branch(self):
        job = JobPosting.objects.create(chain=self.chain, title="Teacher")
        self.json(f"/chain/hiring/{job.pk}/fill/",
                  {"branch_id": self.foreign.pk}, expect=400)


class TransferTests(ChainData):
    def setUp(self):
        self.client.force_login(self.owner)

    def test_transfer_student_moves_without_reentry(self):
        self.json("/chain/transfers/move/", {
            "person_type": "student", "person_id": self.student.pk,
            "from_school_id": self.branch_a.pk, "to_school_id": self.branch_b.pk,
            "note": "family relocated",
        })
        self.student.refresh_from_db()
        self.assertEqual(self.student.school, self.branch_b)
        self.assertIsNone(self.student.classroom)  # old branch's room cleared
        log = TransferLog.objects.latest("pk")
        self.assertEqual(log.person_display, "Ayesha Khan")
        self.assertEqual(log.note, "family relocated")

    def test_transfer_staff_between_branches(self):
        self.json("/chain/transfers/move/", {
            "person_type": "staff", "person_id": self.staff.pk,
            "from_school_id": self.branch_a.pk, "to_school_id": self.branch_b.pk,
        })
        self.staff.refresh_from_db()
        self.assertEqual(self.staff.school, self.branch_b)
        self.assertEqual(self.staff.full_name, "Kamran Raza")

    def test_same_branch_transfer_refused(self):
        self.json("/chain/transfers/move/", {
            "person_type": "staff", "person_id": self.staff.pk,
            "from_school_id": self.branch_a.pk, "to_school_id": self.branch_a.pk,
        }, expect=400)


class PolicyJobApprovalTests(ChainData):
    def setUp(self):
        self.client.force_login(self.owner)

    def test_policy_create_and_override(self):
        resp = self.json("/chain/policies/create/", {
            "name": "Fee structure 2026", "category": "fee_structure",
            "default_value": "Rs 3,500"}, expect=201)
        pid = resp.json()["policy"]["id"]
        self.json(f"/chain/policies/{pid}/override/",
                  {"school_id": self.branch_b.pk, "value": "Rs 3,000"})
        policy = GroupPolicy.objects.get(pk=pid)
        self.assertEqual(policy.overrides.get(school=self.branch_b).value, "Rs 3,000")
        self.assertEqual(policy.overrides.filter(school=self.branch_a).count(), 0)

    def test_job_post_once_fill_at_branch(self):
        resp = self.json("/chain/hiring/create/",
                         {"title": "Physics teacher", "branch_id": None}, expect=201)
        jid = resp.json()["job"]["id"]
        self.json(f"/chain/hiring/{jid}/fill/", {"branch_id": self.branch_b.pk})
        job = JobPosting.objects.get(pk=jid)
        self.assertEqual(job.status, JobPosting.Status.FILLED)
        self.assertEqual(job.filled_branch, self.branch_b)

    def test_announcement_all_branches_vs_single(self):
        resp = self.json("/chain/announcements/create/",
                         {"title": "PTM", "body": "All.", "school_id": None}, expect=201)
        self.assertEqual(resp.json()["announcement"]["scope"], "all")
        resp = self.json("/chain/announcements/create/",
                         {"title": "Audit", "body": "One.",
                          "school_id": self.branch_a.pk}, expect=201)
        self.assertEqual(resp.json()["announcement"]["scope"], "branch")

    def test_approve_request_then_no_redismiss(self):
        req = ApprovalRequest.objects.create(chain=self.chain, school=self.branch_a,
                                             title="Budget", amount=1000)
        self.json(f"/chain/approvals/{req.pk}/decide/",
                  {"decision": "approved", "note": "ok"})
        req.refresh_from_db()
        self.assertEqual(req.status, ApprovalRequest.Status.APPROVED)
        self.json(f"/chain/approvals/{req.pk}/decide/",
                  {"decision": "rejected"}, expect=400)
        req.refresh_from_db()
        self.assertEqual(req.status, ApprovalRequest.Status.APPROVED)


class MetricsTests(ChainData):
    """The chain dashboard must read the REAL school-side data the
    principal/teachers/portals create (School_Admin), not any parallel set."""

    def test_metrics_collection_attendance_exams_and_consolidation(self):
        today = datetime.date.today()
        section = ClassSection.objects.create(
            school=self.branch_a, grade="Grade 3", section="A", capacity=30)
        for i in range(10):
            s = SchoolStudent.objects.create(
                school=self.branch_a, class_section=section,
                admission_no=f"M-{i}", full_name=f"S{i}")
            invoice = StudentFeeInvoice.objects.create(
                school=self.branch_a, student=s,
                period=today.strftime("%B %Y"), amount=1000,
                due_date=today - datetime.timedelta(days=5))
            if i < 8:  # 8 of the 10 invoices fully collected
                FeePayment.objects.create(
                    invoice=invoice, amount=1000,
                    paid_on=today - datetime.timedelta(days=2))
        # A teacher's register save upserts this snapshot (Teachers.metrics).
        SchoolAttendanceSnapshot.objects.create(
            school=self.branch_a, class_section=section, date=today,
            present=95, absent=5)
        # Marks entries keep this average live (Teachers.metrics).
        ExamRecord.objects.create(
            school=self.branch_a, class_section=section,
            exam_name="Mid Term", subject="Math", exam_date=today,
            average_pct=72.5)

        m = branch_metrics(self.branch_a, today)
        self.assertEqual(m["students"], 10)
        self.assertEqual(m["free_seats"], 20)  # capacity 30, 10 enrolled
        self.assertEqual(m["collection_pct"], 80.0)
        self.assertEqual(m["attendance_pct"], 95.0)
        self.assertEqual(m["exam_avg"], 72.5)
        lights = scorecard(self.branch_a, today)["lights"]
        self.assertEqual(lights["fees"], "yellow")
        self.assertEqual(lights["attendance"], "green")
        self.assertEqual(lights["exams"], "green")

        totals = consolidated([m, branch_metrics(self.branch_b, today)])
        self.assertEqual(totals["branches"], 2)

    def test_per_section_snapshots_are_not_double_counted(self):
        """A school with both per-section and school-wide snapshot rows must
        count only one shape (teacher saves always upsert per-section rows)."""
        today = datetime.date.today()
        section = ClassSection.objects.create(
            school=self.branch_a, grade="Grade 1", section="A")
        SchoolAttendanceSnapshot.objects.create(
            school=self.branch_a, class_section=section, date=today,
            present=40, absent=10)
        SchoolAttendanceSnapshot.objects.create(
            school=self.branch_a, date=today, present=400, absent=100)
        from .metrics import attendance_pct
        self.assertEqual(attendance_pct(self.branch_a, today=today), 80.0)

    def test_empty_branch_shows_no_data_not_zero_attendance(self):
        from .metrics import attendance_pct, exam_average
        self.assertIsNone(attendance_pct(self.branch_b, today=datetime.date.today()))
        self.assertIsNone(exam_average(self.branch_b))
