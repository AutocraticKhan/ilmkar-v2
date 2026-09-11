"""Front Desk / Admissions dashboard views.

Access model: every view is wrapped in ``front_desk_required`` — the
signed-in user must hold a ``SchoolUser`` membership with the
``front_desk`` role or the ``principal`` role (read-through, see
``utils``). PRINCIPALS ARE READ-ONLY: every mutation endpoint is
additionally wrapped in ``front_desk_write_required`` (``utils.can_mutate``),
so a principal browsing /frontdesk/ can review everything but never log a
visitor, issue a gate pass or print an ID card.

All data is resolved through ``utils.current_school`` — a front-desk user
can only ever see and affect the ONE school their account belongs to.

Mutation endpoints follow the platform conventions: JSON body in, JSON
out, every write appends an ``AuditLog`` row. The complaint/request
register intentionally writes to ``School_Admin.Complaint`` (the single
source of truth shared with the principal's dashboard); enquiries that
reach the formal application stage link to
``School_Admin.AdmissionApplication`` (the principal decides there).
"""
import datetime
import json
from functools import wraps

from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from School_Admin.models import (
    AdmissionApplication,
    ClassSection,
    Complaint,
    StaffMember,
    Student,
)

from . import metrics, services
from .models import (
    AdmissionEnquiry,
    AuditLog,
    GatePass,
    IDCard,
    VisitorLog,
)
from .utils import can_mutate, current_school, is_front_desk


def _school_of(request):
    """The tenant scope of this front-desk user (their ONE school)."""
    return current_school(request.user)


def _is_front_desk(user):
    return is_front_desk(user)


front_desk_required = user_passes_test(_is_front_desk, login_url="/")


def front_desk_write_required(view):
    """Mutation guard: front-desk staff only. Principals (read-through)
    get a JSON 403 instead of a redirect — the page JS shows the
    read-only toast and the dashboard keeps its 'changes are disabled'
    banner."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not can_mutate(request.user):
            return JsonResponse(
                {
                    "error": "Read-only access — only front desk staff can "
                             "make changes (principals view only)."
                },
                status=403,
            )
        return view(request, *args, **kwargs)

    return wrapper


def _parse_body(request):
    try:
        return json.loads(request.body or "{}"), None
    except json.JSONDecodeError:
        return None, JsonResponse({"error": "Invalid request body."}, status=400)


def _actor(request):
    """Username stamped onto audit rows."""
    return request.user.get_username()


def _parse_date(value):
    """ISO date from a request field, or None when invalid/absent."""
    if not value:
        return None
    try:
        return datetime.date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _parse_dt(value):
    """ISO datetime from a request field, defaulting to now when absent."""
    if not value:
        return timezone.now()
    value = str(value).strip().replace("Z", "+00:00")
    try:
        return timezone.datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return timezone.now()


def _bad(message):
    return JsonResponse({"error": message}, status=400)


# ---------- snapshot home ----------


@login_required
@front_desk_required
def dashboard(request):
    """Front-desk snapshot: who is inside right now, the admission funnel,
    open complaints/requests, outstanding gate passes and card printing
    state."""
    school = _school_of(request)
    today = datetime.date.today()

    funnel = metrics.enquiry_funnel(school)
    inside = [v.as_dict() for v in metrics.visitors_inside(school)[:8]]
    open_reqs = metrics.open_complaints(school)
    passes = metrics.open_gate_passes(school)
    cards = metrics.id_card_summary(school)

    due_followups = [
        e.as_dict()
        for e in AdmissionEnquiry.objects.filter(
            school=school,
            follow_up_date__isnull=False,
            follow_up_date__lte=today,
        ).exclude(
            stage__in=[
                AdmissionEnquiry.Stage.ENROLLED, AdmissionEnquiry.Stage.DROPPED
            ]
        )[:6]
    ]

    return render(
        request,
        "front_desk/dashboard.html",
        {
            "school": school,
            "today": today.isoformat(),
            "funnel": funnel,
            "open_enquiries": funnel["open"],
            "visitors_inside": inside,
            "visitors_inside_count": len(inside),
            "open_complaint_count": open_reqs.count(),
            "open_complaints": [c.as_dict() for c in open_reqs[:6]],
            "active_pass_count": passes.count(),
            "active_passes": [p.as_dict() for p in passes[:6]],
            "cards": cards,
            "due_followups": due_followups,
            "recent_audit": [
                a.as_dict() for a in AuditLog.objects.filter(school=school)[:8]
            ],
        },
    )
# ---------- admissions enquiries / lead funnel ----------


@login_required
@front_desk_required
def enquiries(request):
    """Admissions lead pipeline: every enquiry with its stage, plus the
    class sections for the create drawer."""
    school = _school_of(request)
    rows = AdmissionEnquiry.objects.filter(school=school).select_related(
        "application", "student"
    )
    sections = [
        {"id": s.pk, "name": s.label}
        for s in ClassSection.objects.filter(school=school)
    ]
    students = [
        {"id": s.pk, "name": f"{s.full_name} ({s.admission_no})"}
        for s in Student.objects.filter(school=school, status=Student.Status.ACTIVE)
    ]
    return render(
        request,
        "front_desk/enquiries.html",
        {
            "school": school,
            "rows": [r.as_dict() for r in rows],
            "funnel": metrics.enquiry_funnel(school),
            "sections": sections,
            "students": students,
            "can_edit": can_mutate(request.user),
        },
    )


@login_required
@front_desk_required
@front_desk_write_required
@require_POST
def enquiry_create(request):
    """Register a new admission enquiry (starts the lead funnel)."""
    school = _school_of(request)
    body, error = _parse_body(request)
    if error:
        return error
    name = str(body.get("applicant_name") or "").strip()
    if not name:
        return _bad("Applicant name is required.")
    enquiry = AdmissionEnquiry.objects.create(
        school=school,
        applicant_name=name,
        guardian_name=str(body.get("guardian_name") or "").strip(),
        guardian_phone=str(body.get("guardian_phone") or "").strip(),
        interested_grade=str(body.get("interested_grade") or "").strip(),
        source=body.get("source") or AdmissionEnquiry.Source.WALK_IN,
        follow_up_date=_parse_date(body.get("follow_up_date")),
        follow_up_note=str(body.get("follow_up_note") or "").strip(),
        notes=str(body.get("notes") or "").strip(),
        assigned_to=str(body.get("assigned_to") or "").strip(),
        created_by=_actor(request),
    )
    AuditLog.record(
        school, _actor(request), "enquiry logged",
        enquiry.applicant_name,
        note=f"{enquiry.get_source_display()} — {enquiry.get_stage_display()}",
    )
    return JsonResponse({"enquiry": enquiry.as_dict()})


@login_required
@front_desk_required
@front_desk_write_required
@require_POST
def enquiry_update(request, enquiry_id):
    """Edit contact/follow-up details of a live enquiry."""
    school = _school_of(request)
    enquiry = AdmissionEnquiry.objects.filter(school=school, pk=enquiry_id).first()
    if enquiry is None:
        return JsonResponse({"error": "Enquiry not found."}, status=404)
    body, error = _parse_body(request)
    if error:
        return error
    if "guardian_name" in body:
        enquiry.guardian_name = str(body.get("guardian_name") or "").strip()
    if "guardian_phone" in body:
        enquiry.guardian_phone = str(body.get("guardian_phone") or "").strip()
    if "interested_grade" in body:
        enquiry.interested_grade = str(body.get("interested_grade") or "").strip()
    if "follow_up_date" in body:
        enquiry.follow_up_date = _parse_date(body.get("follow_up_date"))
    if "follow_up_note" in body:
        enquiry.follow_up_note = str(body.get("follow_up_note") or "").strip()[:300]
    if "notes" in body:
        enquiry.notes = str(body.get("notes") or "").strip()
    if "assigned_to" in body:
        enquiry.assigned_to = str(body.get("assigned_to") or "").strip()
    enquiry.save()
    AuditLog.record(
        school, _actor(request), "enquiry updated", enquiry.applicant_name,
        note="contact / follow-up details",
    )
    return JsonResponse({"enquiry": enquiry.as_dict()})
@login_required
@front_desk_required
@front_desk_write_required
@require_POST
def enquiry_stage(request, enquiry_id):
    """Advance (or close) a lead: contacted -> site_visit -> applied
    (create/attach the official application) -> enrolled (attach the
    student) or dropped."""
    school = _school_of(request)
    enquiry = AdmissionEnquiry.objects.filter(school=school, pk=enquiry_id).first()
    if enquiry is None:
        return JsonResponse({"error": "Enquiry not found."}, status=404)
    body, error = _parse_body(request)
    if error:
        return error
    stage = str(body.get("stage") or "").strip()
    valid = set(AdmissionEnquiry.Stage.values)
    if stage not in valid:
        return _bad("Invalid stage.")
    note = str(body.get("note") or "").strip()

    if stage == AdmissionEnquiry.Stage.APPLIED and not enquiry.application_id:
        application_id = body.get("application_id")
        application = None
        if application_id:
            application = AdmissionApplication.objects.filter(
                school=school, pk=application_id
            ).first()
        if application is None:
            section = None
            if body.get("class_section_id"):
                section = ClassSection.objects.filter(
                    school=school, pk=body.get("class_section_id")
                ).first()
            application = AdmissionApplication.objects.create(
                school=school,
                applicant_name=enquiry.applicant_name,
                guardian_name=enquiry.guardian_name,
                guardian_phone=enquiry.guardian_phone,
                class_section=section,
                note=note or f"Created by front desk from enquiry #{enquiry.pk}",
                decided_by="front desk",
            )
        enquiry.application = application

    if stage == AdmissionEnquiry.Stage.ENROLLED and not enquiry.student_id:
        student_id = body.get("student_id")
        student = (
            Student.objects.filter(school=school, pk=student_id).first()
            if student_id else None
        )
        if student is None:
            return _bad("Pick the enrolled student to close the funnel.")
        enquiry.student = student

    enquiry.stage = stage
    if stage == AdmissionEnquiry.Stage.DROPPED and not note:
        note = "Dropped off by front desk"
    stamp = timezone.localtime().strftime("%b %d %H:%M")
    enquiry.notes = (enquiry.notes + "\n" if enquiry.notes else "") + f"[{stamp}] " + note
    enquiry.save(update_fields=["application", "student", "stage", "notes", "updated_at"])
    AuditLog.record(
        school, _actor(request), "enquiry staged",
        f"{enquiry.applicant_name} → {enquiry.get_stage_display()}",
        note=note,
    )
    return JsonResponse({"enquiry": enquiry.as_dict()})
# ---------- visitor log ----------


@login_required
@front_desk_required
def visitors(request):
    """Visitor register: everyone who came in, with check-out state."""
    school = _school_of(request)
    rows = VisitorLog.objects.filter(school=school)
    return render(
        request,
        "front_desk/visitors.html",
        {
            "school": school,
            "rows": [v.as_dict() for v in rows[:200]],
            "inside": rows.filter(exited_at__isnull=True).count(),
            "can_edit": can_mutate(request.user),
        },
    )


@login_required
@front_desk_required
@front_desk_write_required
@require_POST
def visitor_checkin(request):
    """Log a visitor entering the premises (badge issued at the desk)."""
    school = _school_of(request)
    body, error = _parse_body(request)
    if error:
        return error
    name = str(body.get("visitor_name") or "").strip()
    if not name:
        return _bad("Visitor name is required.")
    visitor = VisitorLog.objects.create(
        school=school,
        visitor_name=name,
        contact=str(body.get("contact") or "").strip(),
        id_number=str(body.get("id_number") or "").strip(),
        purpose=body.get("purpose") or VisitorLog.Purpose.OTHER,
        whom_to_meet=str(body.get("whom_to_meet") or "").strip(),
        badge_no=str(body.get("badge_no") or "").strip(),
        entered_at=_parse_dt(body.get("entered_at")),
        notes=str(body.get("notes") or "").strip(),
        handled_by=_actor(request),
    )
    AuditLog.record(
        school, _actor(request), "visitor checked in",
        visitor.visitor_name,
        note=f"badge {visitor.badge_no or '—'} — {visitor.get_purpose_display()}",
    )
    return JsonResponse({"visitor": visitor.as_dict()})


@login_required
@front_desk_required
@front_desk_write_required
@require_POST
def visitor_checkout(request, visitor_id):
    """Record when a visitor left; badge returned at the desk."""
    school = _school_of(request)
    visitor = VisitorLog.objects.filter(school=school, pk=visitor_id).first()
    if visitor is None:
        return JsonResponse({"error": "Visitor entry not found."}, status=404)
    if visitor.exited_at is not None:
        return _bad("Visitor already checked out.")
    visitor.exited_at = timezone.now()
    visitor.save(update_fields=["exited_at"])
    AuditLog.record(
        school, _actor(request), "visitor checked out",
        visitor.visitor_name,
        note=f"inside for {visitor.exited_at - visitor.entered_at}",
    )
    return JsonResponse({"visitor": visitor.as_dict()})
# ---------- complaint / request register (shares School_Admin.Complaint) ----------


@login_required
@front_desk_required
def complaints(request):
    """The register: complaints AND requests logged at the desk, with the
    shared School_Admin rows so the principal sees the same record."""
    school = _school_of(request)
    rows = Complaint.objects.filter(school=school)
    return render(
        request,
        "front_desk/complaints.html",
        {
            "school": school,
            "rows": [c.as_dict() for c in rows],
            "open_count": rows.exclude(
                status__in=[Complaint.Status.RESOLVED, Complaint.Status.CLOSED]
            ).count(),
            "can_edit": can_mutate(request.user),
        },
    )


@login_required
@front_desk_required
@front_desk_write_required
@require_POST
def complaint_create(request):
    """Log a complaint or request into the shared register."""
    school = _school_of(request)
    body, error = _parse_body(request)
    if error:
        return error
    name = str(body.get("complainant_name") or "").strip()
    subject = str(body.get("subject") or "").strip()
    if not name or not subject:
        return _bad("Complainant name and subject are required.")
    category = body.get("category") or Complaint.Category.OTHER
    if category not in Complaint.Category.values:
        category = Complaint.Category.OTHER
    source = body.get("source") or Complaint.Source.WALK_IN
    if source not in Complaint.Source.values:
        source = Complaint.Source.WALK_IN
    complaint = Complaint.objects.create(
        school=school,
        complainant_name=name,
        contact=str(body.get("contact") or "").strip(),
        source=source,
        category=category,
        subject=subject,
        details=str(body.get("details") or "").strip(),
        assigned_to=str(body.get("assigned_to") or "").strip(),
        logged_at=timezone.now(),
    )
    AuditLog.record(
        school, _actor(request), "register entry logged",
        complaint.subject,
        note=f"{complaint.get_category_display()} — {complaint.get_status_display()}",
    )
    return JsonResponse({"complaint": complaint.as_dict()})


@login_required
@front_desk_required
@front_desk_write_required
@require_POST
def complaint_status(request, complaint_id):
    """Move a register entry: open -> in_progress; resolve/close with a
    resolution note (resolution records who and when)."""
    school = _school_of(request)
    complaint = Complaint.objects.filter(school=school, pk=complaint_id).first()
    if complaint is None:
        return JsonResponse({"error": "Register entry not found."}, status=404)
    body, error = _parse_body(request)
    if error:
        return error
    status = str(body.get("status") or "").strip()
    if status not in Complaint.Status.values:
        return _bad("Invalid status.")
    resolution = str(body.get("resolution_note") or "").strip()
    complaint.status = status
    if "assigned_to" in body:
        complaint.assigned_to = str(body.get("assigned_to") or "").strip()
    if status in (Complaint.Status.RESOLVED, Complaint.Status.CLOSED):
        complaint.resolution_note = (
            resolution or f"Marked {status} by {_actor(request)} without a note"
        )
        complaint.resolved_at = timezone.now()
    elif resolution:
        complaint.resolution_note = resolution
    complaint.save()
    AuditLog.record(
        school, _actor(request), "register entry updated",
        complaint.subject,
        note=f"{complaint.get_category_display()} → {complaint.get_status_display()}",
    )
    return JsonResponse({"complaint": complaint.as_dict()})
# ---------- gate passes ----------


@login_required
@front_desk_required
def gate_passes(request):
    """Gate-pass desk: issue, return and cancel passes. Shows the next
    auto pass number on the issue button."""
    school = _school_of(request)
    rows = GatePass.objects.filter(school=school).select_related("student")
    students = [
        {"id": s.pk, "name": f"{s.full_name} — {s.admission_no}"}
        for s in Student.objects.filter(school=school, status=Student.Status.ACTIVE)
    ]
    return render(
        request,
        "front_desk/gate_passes.html",
        {
            "school": school,
            "rows": [p.as_dict() for p in rows[:120]],
            "next_pass_no": services.next_pass_no(school),
            "students": students,
            "active_count": rows.filter(status=GatePass.Status.ACTIVE).count(),
            "can_edit": can_mutate(request.user),
        },
    )


@login_required
@front_desk_required
@front_desk_write_required
@require_POST
def gatepass_create(request):
    """Issue a gate pass (student early leave, visitor, vehicle, goods)."""
    school = _school_of(request)
    body, error = _parse_body(request)
    if error:
        return error
    reason = str(body.get("reason") or "").strip()
    if not reason:
        return _bad("Reason is required.")
    pass_type = body.get("pass_type") or GatePass.PassType.STUDENT_EARLY
    if pass_type not in GatePass.PassType.values:
        pass_type = GatePass.PassType.VISITOR
    student = None
    if pass_type == GatePass.PassType.STUDENT_EARLY:
        student_id = body.get("student_id")
        student = (
            Student.objects.filter(school=school, pk=student_id).first()
            if student_id else None
        )
        if student is None:
            return _bad("Pick the student leaving early.")
    pass_no = services.next_pass_no(school)
    gate_pass = GatePass.objects.create(
        school=school,
        pass_no=pass_no,
        pass_type=pass_type,
        student=student,
        visitor_name=str(body.get("visitor_name") or "").strip(),
        contact=str(body.get("contact") or "").strip(),
        reason=reason,
        issued_to=str(body.get("issued_to") or "").strip(),
        issued_by=_actor(request),
        expected_return=_parse_dt(body.get("expected_return")),
        remarks=str(body.get("remarks") or "").strip(),
    )
    AuditLog.record(
        school, _actor(request), "gate pass issued",
        pass_no,
        note=f"{gate_pass.get_pass_type_display()} — {gate_pass.holder_name} — {reason}",
    )
    return JsonResponse({"pass": gate_pass.as_dict(), "next_pass_no": services.next_pass_no(school)})


@login_required
@front_desk_required
@front_desk_write_required
@require_POST
def gatepass_return(request, pass_id):
    """Mark a pass as returned (holder came back through the gate)."""
    school = _school_of(request)
    gate_pass = GatePass.objects.filter(school=school, pk=pass_id).first()
    if gate_pass is None:
        return JsonResponse({"error": "Gate pass not found."}, status=404)
    if gate_pass.status != GatePass.Status.ACTIVE:
        return _bad("Only active passes can be returned.")
    body, error = _parse_body(request)
    if error:
        return error
    gate_pass.status = GatePass.Status.RETURNED
    gate_pass.returned_at = _parse_dt(body.get("returned_at"))
    remarks = str(body.get("remarks") or "").strip()
    if remarks:
        gate_pass.remarks = (gate_pass.remarks + " | " if gate_pass.remarks else "") + remarks
    gate_pass.save()
    AuditLog.record(
        school, _actor(request), "gate pass returned", gate_pass.pass_no,
        note=remarks or "returned at gate",
    )
    return JsonResponse({"pass": gate_pass.as_dict()})


@login_required
@front_desk_required
@front_desk_write_required
@require_POST
def gatepass_cancel(request, pass_id):
    """Cancel a pass that never went out / was issued in error."""
    school = _school_of(request)
    gate_pass = GatePass.objects.filter(school=school, pk=pass_id).first()
    if gate_pass is None:
        return JsonResponse({"error": "Gate pass not found."}, status=404)
    if gate_pass.status != GatePass.Status.ACTIVE:
        return _bad("Only active passes can be cancelled.")
    gate_pass.status = GatePass.Status.CANCELLED
    gate_pass.save(update_fields=["status"])
    AuditLog.record(
        school, _actor(request), "gate pass cancelled", gate_pass.pass_no,
        note="cancelled at front desk",
    )
    return JsonResponse({"pass": gate_pass.as_dict()})
# ---------- ID card printing ----------


@login_required
@front_desk_required
def id_cards(request):
    """ID card desk: draft cards await printing; printed cards re-print
    anytime from the snapshot columns."""
    school = _school_of(request)
    rows = IDCard.objects.filter(school=school).select_related("student", "staff")
    students = [
        {"id": s.pk, "name": f"{s.full_name} — {s.admission_no}"}
        for s in Student.objects.filter(school=school, status=Student.Status.ACTIVE)
    ]
    staff = [
        {"id": s.pk, "name": f"{s.full_name} — {s.designation or 'Staff'}"}
        for s in StaffMember.objects.filter(school=school, is_active=True)
    ]
    return render(
        request,
        "front_desk/id_cards.html",
        {
            "school": school,
            "rows": [c.as_dict() for c in rows],
            "next_card_no": services.next_card_no(school),
            "students": students,
            "staff": staff,
            "cards": metrics.id_card_summary(school),
            "can_edit": can_mutate(request.user),
        },
    )


@login_required
@front_desk_required
@front_desk_write_required
@require_POST
def idcard_create(request):
    """Create (or snapshot) a student/staff ID card for printing."""
    school = _school_of(request)
    body, error = _parse_body(request)
    if error:
        return error
    holder_type = body.get("holder_type") or IDCard.HolderType.STUDENT
    if holder_type not in IDCard.HolderType.values:
        holder_type = IDCard.HolderType.STUDENT
    student = staff = None
    holder_name = holder_line = admission_no = guardian_phone = ""
    if holder_type == IDCard.HolderType.STUDENT:
        student_id = body.get("student_id")
        student = (
            Student.objects.filter(school=school, pk=student_id).first()
            if student_id else None
        )
        if student is None:
            return _bad("Pick the student for this card.")
        holder_name = student.full_name
        holder_line = student.class_section.label if student.class_section_id else "Student"
        admission_no = student.admission_no
        guardian_phone = student.guardian_phone
    else:
        staff_id = body.get("staff_id")
        staff = (
            StaffMember.objects.filter(school=school, pk=staff_id).first()
            if staff_id else None
        )
        if staff is None:
            return _bad("Pick the staff member for this card.")
        holder_name = staff.full_name
        holder_line = staff.designation or "Staff"
    card_no = services.next_card_no(school)
    card = IDCard.objects.create(
        school=school,
        card_no=card_no,
        holder_type=holder_type,
        student=student,
        staff=staff,
        holder_name=holder_name,
        holder_line=holder_line,
        admission_no=admission_no,
        guardian_phone=guardian_phone,
        issued_on=_parse_date(body.get("issued_on")),
        expires_on=_parse_date(body.get("expires_on")),
        remarks=str(body.get("remarks") or "").strip(),
        created_by=_actor(request),
    )
    AuditLog.record(
        school, _actor(request), "ID card created", card_no,
        note=f"{card.get_holder_type_display()} — {holder_name}",
    )
    return JsonResponse({"card": card.as_dict(), "next_card_no": services.next_card_no(school)})


@login_required
@front_desk_required
@front_desk_write_required
@require_POST
def idcard_mark_printed(request, card_id):
    """Flip a draft card to printed (the print page calls this first)."""
    school = _school_of(request)
    card = IDCard.objects.filter(school=school, pk=card_id).first()
    if card is None:
        return JsonResponse({"error": "ID card not found."}, status=404)
    if card.status != IDCard.Status.PRINTED:
        card.status = IDCard.Status.PRINTED
        card.printed_at = timezone.now()
        card.save(update_fields=["status", "printed_at"])
        AuditLog.record(
            school, _actor(request), "ID card printed", card.card_no,
            note=f"{card.holder_name} — {card.holder_line}",
        )
    return JsonResponse({"card": card.as_dict()})


@login_required
@front_desk_required
def idcard_print(request, card_id):
    """Printable card layout (front/back). Served as its own page so the
    browser print dialog produces just the card."""
    school = _school_of(request)
    card = get_object_or_404(IDCard, school=school, pk=card_id)
    return render(
        request,
        "front_desk/id_card_print.html",
        {
            "school": school,
            "card": card,
            "fd_can_edit": can_mutate(request.user),
        },
    )
