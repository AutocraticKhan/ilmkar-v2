"""School Admin / Principal dashboard views.

Access model: every view is wrapped in ``school_admin_required`` — the
signed-in user must hold a ``SchoolUser`` membership with the ``principal``
role (see ``School_Admin.utils``). All data is resolved through
``utils.current_school``, so a principal can only ever see and affect the
ONE school their account belongs to.
"""
import datetime
import json

from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from . import metrics
from .models import (
    AdmissionApplication,
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
from .utils import current_school, is_school_admin


def _school_of(request):
    """The tenant scope of this principal (their ONE school)."""
    return current_school(request.user)


def _is_school_admin(user):
    return is_school_admin(user)


school_admin_required = user_passes_test(_is_school_admin, login_url="/")


def _parse_body(request):
    try:
        return json.loads(request.body or "{}"), None
    except json.JSONDecodeError:
        return None, JsonResponse({"error": "Invalid request body."}, status=400)


def _pending_counts(school):
    """Pending approval counts used by the sidebar badge + approvals page."""
    return (
        LeaveRequest.objects.filter(school=school, status=LeaveRequest.Status.PENDING).count()
        + ExpenseRequest.objects.filter(school=school, status=ExpenseRequest.Status.PENDING).count()
        + AdmissionApplication.objects.filter(
            school=school, status=AdmissionApplication.Status.PENDING
        ).count()
    )


def _sections_of(school):
    return ClassSection.objects.filter(school=school)


def _section_of(school, section_id):
    """Resolve a ClassSection by id, ONLY within the tenant scope."""
    if section_id in (None, "", "all"):
        return None
    try:
        return _sections_of(school).get(pk=int(section_id))
    except (ClassSection.DoesNotExist, TypeError, ValueError):
        return None


# ---------- snapshot home ----------


@login_required
@school_admin_required
def dashboard(request):
    """Snapshot home: today's attendance %, fees collected today/this
    month, pending admissions and upcoming exams."""
    school = _school_of(request)
    today = datetime.date.today()
    fees = metrics.fee_kpis(school, today)
    pending_admissions = metrics.pending_admissions(school)
    exams = metrics.upcoming_exams(school, today=today)
    return render(
        request,
        "School_Admin/dashboard.html",
        {
            "school": school,
            "attendance_today": metrics.attendance_pct(school, day=today),
            "attendance_30d": metrics.attendance_pct(school, days=30, today=today),
            "fees": fees,
            "pending_admissions": [
                a.as_dict() for a in pending_admissions
            ],
            "pending_admissions_count": len(pending_admissions),
            "upcoming_exams": [e.as_dict() for e in exams],
            "active_students": Student.objects.filter(
                school=school, status=Student.Status.ACTIVE
            ).count(),
            "active_staff": StaffMember.objects.filter(
                school=school, is_active=True
            ).count(),
            "pending_approvals": _pending_counts(school),
        },
    )


# ---------- students + admissions ----------


def _next_admission_no(school):
    """Auto admission number for the year. TODO(placeholder): replace with
    the numbering policy of the real Student Information module."""
    year = timezone.now().year
    count = Student.objects.filter(school=school).count() + 1
    return f"ADM-{year}-{count:04d}"


@login_required
@school_admin_required
def students(request):
    """Student records + admission applications."""
    school = _school_of(request)
    return render(
        request,
        "School_Admin/students.html",
        {
            "school": school,
            "students": [s.as_dict() for s in Student.objects.filter(
                school=school).select_related("class_section")],
            "applications": [a.as_dict() for a in AdmissionApplication.objects.filter(
                school=school).select_related("class_section")],
            "sections": [c.as_dict() for c in _sections_of(school)],
            "pending_admissions": AdmissionApplication.objects.filter(
                school=school, status=AdmissionApplication.Status.PENDING
            ).count(),
            "pending_approvals": _pending_counts(school),
        },
    )


@require_POST
@login_required
@school_admin_required
def student_create(request):
    school = _school_of(request)
    data, err = _parse_body(request)
    if err:
        return err
    full_name = (data.get("full_name") or "").strip()
    if not full_name:
        return JsonResponse({"error": "Student name is required."}, status=400)
    section = _section_of(school, data.get("class_section_id"))
    admission_no = (data.get("admission_no") or "").strip() or _next_admission_no(school)
    if Student.objects.filter(school=school, admission_no=admission_no).exists():
        return JsonResponse({"error": "Admission number already in use."}, status=400)

    monthly_fee_raw = (data.get("monthly_fee") or "").strip()
    try:
        monthly_fee = max(0, float(monthly_fee_raw)) if monthly_fee_raw else 0
    except ValueError:
        return JsonResponse({"error": "Monthly fee must be a number."}, status=400)

    admission_date = None
    if (data.get("admission_date") or "").strip():
        try:
            admission_date = datetime.date.fromisoformat(data["admission_date"])
        except ValueError:
            return JsonResponse({"error": "Invalid admission date."}, status=400)

    student = Student.objects.create(
        school=school,
        class_section=section,
        admission_no=admission_no,
        full_name=full_name,
        guardian_name=(data.get("guardian_name") or "").strip(),
        guardian_phone=(data.get("guardian_phone") or "").strip(),
        monthly_fee=monthly_fee,
        admission_date=admission_date or datetime.date.today(),
    )
    # TODO(integration): also mirror the new student into school_owner.Student
    # so the owner dashboard's branch numbers stay in sync.
    return JsonResponse({"student": student.as_dict()}, status=201)


@require_POST
@login_required
@school_admin_required
def student_status(request, student_id):
    school = _school_of(request)
    student = Student.objects.filter(school=school, pk=student_id).first()
    if student is None:
        return JsonResponse({"error": "Student not found."}, status=404)
    data, err = _parse_body(request)
    if err:
        return err
    status = data.get("status")
    if status not in Student.Status.values:
        return JsonResponse({"error": "Unknown status."}, status=400)
    student.status = status
    student.save(update_fields=["status"])
    return JsonResponse({"student": student.as_dict()})


@require_POST
@login_required
@school_admin_required
def admission_create(request):
    """TODO(placeholder): manual intake of admission requests until the
    parent portal / online admission form submits these directly."""
    school = _school_of(request)
    data, err = _parse_body(request)
    if err:
        return err
    applicant = (data.get("applicant_name") or "").strip()
    if not applicant:
        return JsonResponse({"error": "Applicant name is required."}, status=400)
    section = _section_of(school, data.get("class_section_id"))
    application = AdmissionApplication.objects.create(
        school=school,
        applicant_name=applicant,
        guardian_name=(data.get("guardian_name") or "").strip(),
        guardian_phone=(data.get("guardian_phone") or "").strip(),
        class_section=section,
        note=(data.get("note") or "").strip(),
    )
    return JsonResponse({"application": application.as_dict()}, status=201)


@require_POST
@login_required
@transaction.atomic
def admission_decide(request, application_id):
    """Decide an admission application. Approving creates the student
    record (plus their first fee invoice when a monthly fee is known)."""
    school = _school_of(request)
    application = AdmissionApplication.objects.filter(
        school=school, pk=application_id
    ).first()
    if application is None:
        return JsonResponse({"error": "Application not found."}, status=404)
    if application.status != AdmissionApplication.Status.PENDING:
        return JsonResponse(
            {"error": "This application has already been decided."}, status=400
        )
    data, err = _parse_body(request)
    if err:
        return err

    decision = data.get("decision")
    if decision not in AdmissionApplication.Status.values:
        return JsonResponse({"error": "Unknown decision."}, status=400)

    application.status = decision
    application.decision_note = (data.get("note") or "").strip()[:300]
    application.decided_by = request.user.get_username()
    application.decided_at = timezone.now()

    student = None
    if decision == AdmissionApplication.Status.APPROVED:
        section = _section_of(school, data.get("class_section_id")) or application.class_section
        try:
            monthly_fee = max(0, float(data.get("monthly_fee") or 0))
        except (TypeError, ValueError):
            return JsonResponse({"error": "Monthly fee must be a number."}, status=400)
        student = Student.objects.create(
            school=school,
            class_section=section,
            admission_no=_next_admission_no(school),
            full_name=application.applicant_name,
            guardian_name=application.guardian_name,
            guardian_phone=application.guardian_phone,
            monthly_fee=monthly_fee,
            admission_date=datetime.date.today(),
        )
        application.created_student = student
        if monthly_fee > 0:
            # First invoice for the current period.
            StudentFeeInvoice.objects.create(
                school=school,
                student=student,
                period=metrics.current_period(),
                amount=monthly_fee,
                due_date=datetime.date.today().replace(day=28),
            )
    application.save()
    return JsonResponse({
        "application": application.as_dict(),
        "student": student.as_dict() if student else None,
    })


# ---------- staff ----------


@login_required
@school_admin_required
def staff(request):
    """Staff management page."""
    school = _school_of(request)
    return render(
        request,
        "School_Admin/staff.html",
        {
            "school": school,
            "staff": [s.as_dict() for s in StaffMember.objects.filter(school=school)],
            "active_staff": StaffMember.objects.filter(
                school=school, is_active=True
            ).count(),
            "pending_leaves": LeaveRequest.objects.filter(
                school=school, status=LeaveRequest.Status.PENDING
            ).count(),
            "pending_approvals": _pending_counts(school),
        },
    )


@require_POST
@login_required
@school_admin_required
def staff_create(request):
    school = _school_of(request)
    data, err = _parse_body(request)
    if err:
        return err
    full_name = (data.get("full_name") or "").strip()
    if not full_name:
        return JsonResponse({"error": "Staff name is required."}, status=400)
    join_date = None
    if (data.get("join_date") or "").strip():
        try:
            join_date = datetime.date.fromisoformat(data["join_date"])
        except ValueError:
            return JsonResponse({"error": "Invalid join date."}, status=400)
    member = StaffMember.objects.create(
        school=school,
        full_name=full_name,
        designation=(data.get("designation") or "").strip(),
        department=(data.get("department") or "").strip(),
        phone=(data.get("phone") or "").strip(),
        email=(data.get("email") or "").strip(),
        join_date=join_date,
    )
    # TODO(integration): mirror into school_owner.StaffMember and offer a
    # staff-side login (SchoolUser membership) once the staff app exists.
    return JsonResponse({"member": member.as_dict()}, status=201)


@require_POST
@login_required
@school_admin_required
def staff_toggle(request, staff_id):
    school = _school_of(request)
    member = StaffMember.objects.filter(school=school, pk=staff_id).first()
    if member is None:
        return JsonResponse({"error": "Staff member not found."}, status=404)
    member.is_active = not member.is_active
    member.save(update_fields=["is_active"])
    return JsonResponse({"member": member.as_dict()})


# ---------- fees ----------


@login_required
@school_admin_required
def fees(request):
    """Fee structure setup + defaulter list + recent invoices."""
    school = _school_of(request)
    today = datetime.date.today()
    invoices = [
        inv.as_dict()
        for inv in StudentFeeInvoice.objects.filter(school=school)
        .select_related("student", "student__class_section", "fee_head")[:60]
    ]
    return render(
        request,
        "School_Admin/fees.html",
        {
            "school": school,
            "fee_heads": [h.as_dict() for h in FeeHead.objects.filter(school=school)],
            "defaulters": list(metrics.defaulters(school, today)),
            "invoices": invoices,
            "students": [s.as_dict() for s in Student.objects.filter(
                school=school, status=Student.Status.ACTIVE
            ).select_related("class_section")],
            "sections": [c.as_dict() for c in _sections_of(school)],
            "period": metrics.current_period(today),
            "overdue_amount": metrics.fee_kpis(school, today)["overdue_amount"],
            "pending_approvals": _pending_counts(school),
        },
    )


@require_POST
@login_required
@school_admin_required
def fee_head_create(request):
    school = _school_of(request)
    data, err = _parse_body(request)
    if err:
        return err
    name = (data.get("name") or "").strip()
    if not name:
        return JsonResponse({"error": "Fee head name is required."}, status=400)
    try:
        amount = max(0, float(data.get("amount") or 0))
    except (TypeError, ValueError):
        return JsonResponse({"error": "Amount must be a number."}, status=400)
    frequency = data.get("frequency")
    if frequency not in FeeHead.Frequency.values:
        frequency = FeeHead.Frequency.MONTHLY
    head = FeeHead.objects.create(
        school=school,
        name=name,
        class_section=_section_of(school, data.get("class_section_id")),
        amount=amount,
        frequency=frequency,
    )
    return JsonResponse({"fee_head": head.as_dict()}, status=201)


@require_POST
@login_required
@school_admin_required
def fee_head_delete(request, head_id):
    school = _school_of(request)
    head = FeeHead.objects.filter(school=school, pk=head_id).first()
    if head is None:
        return JsonResponse({"error": "Fee head not found."}, status=404)
    head.is_active = False
    head.save(update_fields=["is_active"])
    return JsonResponse({"fee_head": head.as_dict()})


@require_POST
@login_required
@school_admin_required
def invoice_create(request):
    """Issue an invoice to a student. Amount defaults to the chosen fee
    head's amount, else the student's monthly fee."""
    school = _school_of(request)
    data, err = _parse_body(request)
    if err:
        return err
    student = Student.objects.filter(
        school=school, pk=data.get("student_id")
    ).first()
    if student is None:
        return JsonResponse({"error": "Pick a student of your school."}, status=400)
    head = None
    if data.get("fee_head_id") not in (None, "", "all"):
        head = FeeHead.objects.filter(school=school, pk=data["fee_head_id"]).first()
    amount_raw = (data.get("amount") or "").strip()
    if amount_raw:
        try:
            amount = max(0, float(amount_raw))
        except ValueError:
            return JsonResponse({"error": "Amount must be a number."}, status=400)
    elif head is not None:
        amount = float(head.amount)
    else:
        amount = float(student.monthly_fee)
    if amount <= 0:
        return JsonResponse(
            {"error": "No amount — pick a fee head or enter an amount."}, status=400
        )

    period = (data.get("period") or "").strip() or metrics.current_period()
    due_date = None
    if (data.get("due_date") or "").strip():
        try:
            due_date = datetime.date.fromisoformat(data["due_date"])
        except ValueError:
            return JsonResponse({"error": "Invalid due date."}, status=400)
    invoice = StudentFeeInvoice.objects.create(
        school=school,
        student=student,
        fee_head=head,
        period=period,
        amount=amount,
        due_date=due_date
        or datetime.date.today().replace(day=28),
    )
    return JsonResponse({"invoice": invoice.as_dict()}, status=201)


@require_POST
@login_required
@school_admin_required
def invoice_pay(request, invoice_id):
    """Record a payment against an invoice; the invoice status updates to
    partial/paid automatically."""
    school = _school_of(request)
    invoice = StudentFeeInvoice.objects.filter(school=school, pk=invoice_id).first()
    if invoice is None:
        return JsonResponse({"error": "Invoice not found."}, status=404)
    if invoice.status == StudentFeeInvoice.Status.PAID:
        return JsonResponse({"error": "This invoice is already paid."}, status=400)
    data, err = _parse_body(request)
    if err:
        return err
    try:
        amount = float(data.get("amount") or 0)
    except (TypeError, ValueError):
        return JsonResponse({"error": "Amount must be a number."}, status=400)
    outstanding = float(invoice.amount) - invoice.paid_amount
    if amount <= 0 or amount > outstanding + 0.001:
        return JsonResponse(
            {"error": f"Amount must be between 0 and {outstanding:.2f}."}, status=400
        )
    method = data.get("method")
    if method not in FeePayment.Method.values:
        method = FeePayment.Method.CASH
    paid_on = datetime.date.today()
    if (data.get("paid_on") or "").strip():
        try:
            paid_on = datetime.date.fromisoformat(data["paid_on"])
        except ValueError:
            return JsonResponse({"error": "Invalid payment date."}, status=400)

    payment = FeePayment.objects.create(
        invoice=invoice,
        amount=amount,
        paid_on=paid_on,
        method=method,
        received_by=(data.get("received_by") or "").strip()[:120],
    )
    new_total = invoice.paid_amount
    if new_total >= float(invoice.amount) - 0.001:
        invoice.status = StudentFeeInvoice.Status.PAID
    elif new_total > 0:
        invoice.status = StudentFeeInvoice.Status.PARTIAL
    invoice.save(update_fields=["status"])
    return JsonResponse({"payment": payment.as_dict(), "invoice": invoice.as_dict()})


# ---------- approvals ----------


@login_required
@school_admin_required
def approvals(request):
    """Leave requests, expense requests and admission applications in one
    decision feed."""
    school = _school_of(request)
    return render(
        request,
        "School_Admin/approvals.html",
        {
            "school": school,
            "leaves": [l.as_dict() for l in LeaveRequest.objects.filter(
                school=school).select_related("staff")],
            "expenses": [e.as_dict() for e in ExpenseRequest.objects.filter(school=school)],
            "applications": [a.as_dict() for a in AdmissionApplication.objects.filter(
                school=school).select_related("class_section")],
            "staff": [
                {"id": s.pk, "full_name": s.full_name}
                for s in StaffMember.objects.filter(school=school, is_active=True)
            ],
            "sections": [c.as_dict() for c in _sections_of(school)],
            "pending_approvals": _pending_counts(school),
        },
    )


@require_POST
@login_required
@school_admin_required
def leave_create(request):
    """TODO(placeholder): manual intake until the staff app submits leave
    requests from the teacher dashboard."""
    school = _school_of(request)
    data, err = _parse_body(request)
    if err:
        return err
    member = StaffMember.objects.filter(
        school=school, pk=data.get("staff_id"), is_active=True
    ).first()
    if member is None:
        return JsonResponse({"error": "Pick a staff member of your school."}, status=400)
    try:
        from_date = datetime.date.fromisoformat(data.get("from_date") or "")
        to_date = datetime.date.fromisoformat(data.get("to_date") or "")
    except ValueError:
        return JsonResponse({"error": "Valid from/to dates are required."}, status=400)
    if to_date < from_date:
        return JsonResponse(
            {"error": "To-date cannot be before the from-date."}, status=400
        )
    leave = LeaveRequest.objects.create(
        school=school,
        staff=member,
        from_date=from_date,
        to_date=to_date,
        reason=(data.get("reason") or "").strip()[:300],
    )
    return JsonResponse({"leave": leave.as_dict()}, status=201)


@require_POST
@login_required
@school_admin_required
def leave_decide(request, leave_id):
    school = _school_of(request)
    leave = LeaveRequest.objects.filter(school=school, pk=leave_id).first()
    if leave is None:
        return JsonResponse({"error": "Leave request not found."}, status=404)
    if leave.status != LeaveRequest.Status.PENDING:
        return JsonResponse(
            {"error": "This leave request has already been decided."}, status=400
        )
    data, err = _parse_body(request)
    if err:
        return err
    decision = data.get("decision")
    if decision not in (LeaveRequest.Status.APPROVED, LeaveRequest.Status.REJECTED):
        return JsonResponse(
            {"error": "Decision must be approved or rejected."}, status=400
        )
    leave.status = decision
    leave.decision_note = (data.get("note") or "").strip()[:300]
    leave.decided_at = timezone.now()
    leave.save(update_fields=["status", "decision_note", "decided_at"])
    return JsonResponse({"leave": leave.as_dict()})


@require_POST
@login_required
@school_admin_required
def expense_create(request):
    school = _school_of(request)
    data, err = _parse_body(request)
    if err:
        return err
    title = (data.get("title") or "").strip()
    if not title:
        return JsonResponse({"error": "Expense title is required."}, status=400)
    try:
        amount = float(data.get("amount") or 0)
    except (TypeError, ValueError):
        return JsonResponse({"error": "Amount must be a number."}, status=400)
    if amount <= 0:
        return JsonResponse({"error": "Amount must be greater than zero."}, status=400)
    expense = ExpenseRequest.objects.create(
        school=school,
        title=title,
        details=(data.get("details") or "").strip(),
        amount=amount,
        requested_by=(data.get("requested_by") or "").strip()[:120],
    )
    return JsonResponse({"expense": expense.as_dict()}, status=201)


@require_POST
@login_required
@school_admin_required
def expense_decide(request, expense_id):
    school = _school_of(request)
    expense = ExpenseRequest.objects.filter(school=school, pk=expense_id).first()
    if expense is None:
        return JsonResponse({"error": "Expense request not found."}, status=404)
    if expense.status != ExpenseRequest.Status.PENDING:
        return JsonResponse(
            {"error": "This expense request has already been decided."}, status=400
        )
    data, err = _parse_body(request)
    if err:
        return err
    decision = data.get("decision")
    if decision not in (ExpenseRequest.Status.APPROVED, ExpenseRequest.Status.REJECTED):
        return JsonResponse(
            {"error": "Decision must be approved or rejected."}, status=400
        )
    expense.status = decision
    expense.decision_note = (data.get("note") or "").strip()[:300]
    expense.decided_at = timezone.now()
    expense.save(update_fields=["status", "decision_note", "decided_at"])
    # TODO(integration): escalate large approved expenses to the owner
    # dashboard (school_owner.ApprovalRequest) once the apps are connected.
    return JsonResponse({"expense": expense.as_dict()})


# ---------- reports ----------


@login_required
@school_admin_required
def reports(request):
    """Attendance / academic / financial reports, filterable by class and
    section. Server-rendered from GET params so filtered views are
    URL-shareable (?view=academic&section=3)."""
    school = _school_of(request)
    today = datetime.date.today()

    view = request.GET.get("view", "attendance")
    if view not in ("attendance", "academic", "financial"):
        view = "attendance"
    section = _section_of(school, request.GET.get("section"))
    days = 30
    try:
        days = min(180, max(7, int(request.GET.get("days", 30))))
    except (TypeError, ValueError):
        pass

    context = {
        "school": school,
        "view": view,
        "days": days,
        "section": section,
        "sections": [c.as_dict() for c in _sections_of(school)],
        "pending_approvals": _pending_counts(school),
    }

    if view == "attendance":
        rows = metrics.class_attendance_rows(
            school, days=days, class_section=section, today=today
        )
        context["attendance_rows"] = rows
        context["attendance_avg"] = (
            round(
                sum(r["pct"] for r in rows if r["pct"] is not None)
                / max(1, sum(1 for r in rows if r["pct"] is not None)),
                1,
            )
            if any(r["pct"] is not None for r in rows) else None
        )
    elif view == "academic":
        exam_qs = ExamRecord.objects.filter(school=school).select_related("class_section")
        if section is not None:
            exam_qs = exam_qs.filter(class_section=section)
        context["exam_rows"] = [e.as_dict() for e in exam_qs[:60]]
    else:
        context["financial_rows"] = metrics.monthly_financials(school, today=today)
        fees = metrics.fee_kpis(school, today)
        context["fees"] = fees

    return render(request, "School_Admin/reports.html", context)


# ---------- notices / circulars ----------


@login_required
@school_admin_required
def notices(request):
    school = _school_of(request)
    return render(
        request,
        "School_Admin/notices.html",
        {
            "school": school,
            "notices": [n.as_dict() for n in Notice.objects.filter(school=school)],
            "pending_approvals": _pending_counts(school),
        },
    )


@require_POST
@login_required
@school_admin_required
def notice_create(request):
    """TODO(integration): when the teacher/student/parent portals exist,
    fan this out to their inboxes on create (post_save or a task queue)."""
    school = _school_of(request)
    data, err = _parse_body(request)
    if err:
        return err
    title = (data.get("title") or "").strip()
    body = (data.get("body") or "").strip()
    if not title or not body:
        return JsonResponse(
            {"error": "Title and message are required."}, status=400
        )
    audience = data.get("audience")
    if audience not in Notice.Audience.values:
        audience = Notice.Audience.ALL
    priority = data.get("priority")
    if priority not in Notice.Priority.values:
        priority = Notice.Priority.INFO
    notice = Notice.objects.create(
        school=school,
        title=title,
        body=body,
        audience=audience,
        priority=priority,
        created_by=request.user,
    )
    return JsonResponse({"notice": notice.as_dict()}, status=201)


@require_POST
@login_required
@school_admin_required
def notice_delete(request, notice_id):
    school = _school_of(request)
    notice = Notice.objects.filter(school=school, pk=notice_id).first()
    if notice is None:
        return JsonResponse({"error": "Notice not found."}, status=404)
    notice.delete()
    return JsonResponse({"ok": True})


# ---------- complaints & front-desk log ----------


@login_required
@school_admin_required
def frontdesk(request):
    school = _school_of(request)
    return render(
        request,
        "School_Admin/frontdesk.html",
        {
            "school": school,
            "complaints": [c.as_dict() for c in Complaint.objects.filter(school=school)],
            "entries": [e.as_dict() for e in FrontDeskEntry.objects.filter(school=school)[:80]],
            "open_complaints": Complaint.objects.filter(
                school=school,
                status__in=[Complaint.Status.OPEN, Complaint.Status.IN_PROGRESS],
            ).count(),
            "follow_ups": FrontDeskEntry.objects.filter(
                school=school, follow_up_needed=True
            ).count(),
            "pending_approvals": _pending_counts(school),
        },
    )


@require_POST
@login_required
@school_admin_required
def complaint_create(request):
    school = _school_of(request)
    data, err = _parse_body(request)
    if err:
        return err
    complainant = (data.get("complainant_name") or "").strip()
    subject = (data.get("subject") or "").strip()
    if not complainant or not subject:
        return JsonResponse(
            {"error": "Complainant and subject are required."}, status=400
        )
    source = data.get("source")
    if source not in Complaint.Source.values:
        source = Complaint.Source.WALK_IN
    category = data.get("category")
    if category not in Complaint.Category.values:
        category = Complaint.Category.OTHER
    complaint = Complaint.objects.create(
        school=school,
        complainant_name=complainant,
        contact=(data.get("contact") or "").strip(),
        source=source,
        category=category,
        subject=subject,
        details=(data.get("details") or "").strip(),
        assigned_to=(data.get("assigned_to") or "").strip(),
    )
    return JsonResponse({"complaint": complaint.as_dict()}, status=201)


@require_POST
@login_required
@school_admin_required
def complaint_status(request, complaint_id):
    school = _school_of(request)
    complaint = Complaint.objects.filter(school=school, pk=complaint_id).first()
    if complaint is None:
        return JsonResponse({"error": "Complaint not found."}, status=404)
    data, err = _parse_body(request)
    if err:
        return err
    status = data.get("status")
    if status not in Complaint.Status.values:
        return JsonResponse({"error": "Unknown status."}, status=400)
    complaint.status = status
    if (data.get("assigned_to") or "").strip():
        complaint.assigned_to = data["assigned_to"].strip()[:120]
    if status in (Complaint.Status.RESOLVED, Complaint.Status.CLOSED):
        complaint.resolved_at = timezone.now()
    complaint.save(update_fields=["status", "assigned_to", "resolved_at"])
    return JsonResponse({"complaint": complaint.as_dict()})


@require_POST
@login_required
@school_admin_required
def complaint_resolve(request, complaint_id):
    school = _school_of(request)
    complaint = Complaint.objects.filter(school=school, pk=complaint_id).first()
    if complaint is None:
        return JsonResponse({"error": "Complaint not found."}, status=404)
    data, err = _parse_body(request)
    if err:
        return err
    complaint.status = Complaint.Status.RESOLVED
    complaint.resolution_note = (data.get("note") or "").strip()
    complaint.resolved_at = timezone.now()
    complaint.save(update_fields=["status", "resolution_note", "resolved_at"])
    return JsonResponse({"complaint": complaint.as_dict()})


@require_POST
@login_required
@school_admin_required
def entry_create(request):
    """Log a front-desk activity (visitor, enquiry, call, delivery)."""
    school = _school_of(request)
    data, err = _parse_body(request)
    if err:
        return err
    person = (data.get("person") or "").strip()
    summary = (data.get("summary") or "").strip()
    if not person or not summary:
        return JsonResponse(
            {"error": "Person and summary are required."}, status=400
        )
    entry_type = data.get("entry_type")
    if entry_type not in FrontDeskEntry.EntryType.values:
        entry_type = FrontDeskEntry.EntryType.VISITOR
    occurred_at = timezone.now()
    if (data.get("occurred_at") or "").strip():
        try:
            occurred_at = datetime.datetime.fromisoformat(data["occurred_at"])
            if timezone.is_naive(occurred_at):
                occurred_at = timezone.make_aware(occurred_at)
        except ValueError:
            return JsonResponse({"error": "Invalid date/time."}, status=400)
    entry = FrontDeskEntry.objects.create(
        school=school,
        entry_type=entry_type,
        person=person,
        summary=summary[:300],
        handled_by=(data.get("handled_by") or "").strip()[:120],
        follow_up_needed=bool(data.get("follow_up_needed")),
        occurred_at=occurred_at,
    )
    return JsonResponse({"entry": entry.as_dict()}, status=201)
