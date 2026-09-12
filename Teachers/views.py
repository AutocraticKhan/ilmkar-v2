"""Teacher / Staff dashboard views.

Access model: every view is wrapped in ``teacher_required`` — the
signed-in user must hold a ``SchoolUser`` membership with the ``teacher``
or ``principal`` role (see ``Teachers.utils``; principals get a
read-through so they can use the private notes / report comments in
parent meetings). All data is resolved through ``utils.current_school``
and ``utils.current_staff_member``, so a teacher can only ever see and
affect their ONE school.

Every mutating view takes a JSON POST body (same pattern as
``School_Admin.views``) and answers ``JsonResponse``.
"""
import datetime
import json

from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_POST

from School_Admin.models import (
    ClassSection,
    ExamRecord,
    LeaveRequest,
    Notice,
    StaffMember,
    Student,
)

from . import metrics
from .models import (
    Assignment,
    AssignmentSubmission,
    ClassDiary,
    GradeEntry,
    LessonPlan,
    Payslip,
    ReportCardComment,
    SharedResource,
    StudentAttendance,
    SubstituteAssignment,
    TeacherMessage,
    TeacherNote,
    TimetableSlot,
)
from .utils import current_school, current_staff_member, is_teacher, teacher_sections


def _school_of(request):
    """The tenant scope of this teacher (their ONE school)."""
    return current_school(request.user)


def _staff_of(request, school):
    """The StaffMember HR row of this teacher (may be None until linked)."""
    return current_staff_member(request.user, school)


def _is_teacher(user):
    return is_teacher(user)


teacher_required = user_passes_test(_is_teacher, login_url="/")


def _parse_body(request):
    try:
        return json.loads(request.body or "{}"), None
    except json.JSONDecodeError:
        return None, JsonResponse({"error": "Invalid request body."}, status=400)


def _section_of(school, section_id):
    """Resolve a ClassSection by id, ONLY within the tenant scope."""
    try:
        return ClassSection.objects.get(school=school, pk=int(section_id))
    except (ClassSection.DoesNotExist, TypeError, ValueError):
        return None


def _student_of(school, student_id):
    try:
        return Student.objects.get(school=school, pk=int(student_id))
    except (Student.DoesNotExist, TypeError, ValueError):
        return None


def _common(request, nav_active, **extra):
    """Shared template context: school, staff link, sidebar badge."""
    school = _school_of(request)
    staff = _staff_of(request, school)
    ctx = {
        "school": school,
        "staff": staff,
        "profile": getattr(request.user, "teacher_profile", None),
        "nav_active": nav_active,
        "unread_count": (
            TeacherMessage.objects.filter(staff=staff, is_read=False).count()
            if staff else 0
        ),
    }
    ctx.update(extra)
    return ctx


# ---------- home: today at a glance ----------


@login_required
@teacher_required
def dashboard(request):
    """Today's classes at a glance, one-tap attendance entry, counts for
    the quick-action cards and the latest staff notices."""
    school = _school_of(request)
    staff = _staff_of(request, school)
    today = datetime.date.today()
    day = metrics.day_code(today)

    slots = (
        TimetableSlot.objects.filter(school=school, teacher=staff, day=day)
        .select_related("class_section", "teacher")
        if staff
        else TimetableSlot.objects.none()
    )

    today_slots = []
    attendance_done = True
    for slot in slots:
        total = Student.objects.filter(
            school=school,
            class_section=slot.class_section,
            status=Student.Status.ACTIVE,
        ).count()
        marked = StudentAttendance.objects.filter(
            school=school, class_section=slot.class_section, date=today
        ).count()
        if marked < total:
            attendance_done = False
        today_slots.append({
            "slot": slot,
            "marked_summary": f"{marked}/{total} marked" if total else "no students yet",
        })

    annual_used, _sick_used, policy = (
        metrics.leave_balance(school, staff, today=today)
        if staff else (0, 0, metrics.LEAVE_POLICY)
    )
    warnings = metrics.early_warnings(school, today=today)

    # assignments awaiting review (submitted, not graded)
    pending_submissions = AssignmentSubmission.objects.filter(
        school=school, status=AssignmentSubmission.Status.SUBMITTED
    )
    if staff:
        pending_submissions = pending_submissions.filter(assignment__posted_by=staff)

    notices = Notice.objects.filter(
        school=school, audience__in=[Notice.Audience.STAFF, Notice.Audience.ALL]
    )[:5]

    return render(
        request,
        "Teachers/dashboard.html",
        _common(
            request,
            "overview",
            today=today,
            today_slots=today_slots,
            attendance_done=attendance_done,
            pending_submissions=pending_submissions.count(),
            warnings_count=len(warnings),
            leave_used=annual_used,
            leave_left=max(policy["annual"] - annual_used, 0),
            leave_quota=policy["annual"],
            notices=notices,
        ),
    )


# ---------- one-tap attendance ----------


@login_required
@teacher_required
def attendance(request):
    """One-tap attendance: pick a class, "Mark all present", fix the
    exceptions, save. Saving upserts the principal dashboard's
    AttendanceSnapshot for the section."""
    school = _school_of(request)
    staff = _staff_of(request, school)
    today = datetime.date.today()

    sections = teacher_sections(school, staff)
    section = _section_of(school, request.GET.get("section"))

    if request.method == "POST":
        body, error = _parse_body(request)
        if error:
            return error
        section = _section_of(school, (body or {}).get("section_id"))
        marks = (body or {}).get("marks") or {}
        if section is None or not isinstance(marks, dict) or not marks:
            return JsonResponse(
                {"error": "Pick a class and at least one mark."}, status=400
            )
        valid = set(StudentAttendance.Mark.values)
        saved = 0
        for student_id, mark in marks.items():
            student = _student_of(school, student_id)
            if student is None or mark not in valid:
                continue
            StudentAttendance.objects.update_or_create(
                school=school,
                class_section=section,
                student=student,
                date=today,
                defaults={"mark": mark, "marked_by": staff},
            )
            saved += 1
        snapshot = metrics.sync_attendance_snapshot(school, section, today)
        return JsonResponse({
            "ok": True,
            "saved": saved,
            "present": snapshot.present if snapshot else 0,
            "absent": snapshot.absent if snapshot else 0,
        })

    roster = []
    if section:
        marks_by_student = {
            a.student_id: a.mark
            for a in StudentAttendance.objects.filter(
                school=school, class_section=section, date=today
            )
        }
        for student in Student.objects.filter(
            school=school, class_section=section, status=Student.Status.ACTIVE
        ).order_by("full_name"):
            roster.append({
                "student_id": student.pk,
                "name": student.full_name,
                "admission_no": student.admission_no,
                "mark": marks_by_student.get(student.pk, StudentAttendance.Mark.PRESENT),
            })

    return render(
        request,
        "Teachers/attendance.html",
        _common(
            request,
            "attendance",
            sections=sections,
            section=section,
            roster=roster,
            today=today,
            day_display=today.strftime("%A"),
            mark_choices=list(StudentAttendance.Mark.choices),
        ),
    )


# ---------- marks / grades grid ----------


@login_required
@teacher_required
def marks(request):
    """Simple marks grid per exam. Saving recomputes the exam's class
    average on ``School_Admin.ExamRecord`` so the principal's dashboard
    and reports stay in sync."""
    school = _school_of(request)
    staff = _staff_of(request, school)

    # placeholder default total — the real Exams module will carry
    # per-paper totals (TODO: move to ExamRecord when it lands).
    exams = list(ExamRecord.objects.filter(school=school))
    for e in exams:
        e.total_marks_default = 100

    exam = None
    if request.GET.get("exam"):
        try:
            exam = next(e for e in exams if e.pk == int(request.GET["exam"]))
        except (StopIteration, TypeError, ValueError):
            exam = None

    grid = []
    section = None
    if exam is not None:
        section = exam.class_section
        entries_by_student = {
            g.student_id: g
            for g in GradeEntry.objects.filter(school=school, exam=exam)
        }
        students = Student.objects.filter(
            school=school, status=Student.Status.ACTIVE
        )
        if section is not None:
            students = students.filter(class_section=section)
        for student in students.order_by("full_name"):
            entry = entries_by_student.get(student.pk)
            grid.append({
                "student_id": student.pk,
                "name": student.full_name,
                "marks": (
                    entry.marks_obtained if entry else None
                ),
                "total": entry.total_marks if entry else exam.total_marks_default,
                "remarks": entry.remarks if entry else "",
            })

    if request.method == "POST":
        body, error = _parse_body(request)
        if error:
            return error
        try:
            exam = ExamRecord.objects.get(
                school=school, pk=int((body or {}).get("exam_id"))
            )
        except (ExamRecord.DoesNotExist, TypeError, ValueError):
            return JsonResponse({"error": "Unknown exam."}, status=400)
        entries = (body or {}).get("entries") or []
        saved = 0
        for row in entries:
            if not isinstance(row, dict):
                continue
            student = _student_of(school, row.get("student_id"))
            if student is None or row.get("marks_obtained") in (None, ""):
                continue
            try:
                marks_obtained = round(float(row["marks_obtained"]), 2)
            except (TypeError, ValueError):
                continue
            total = int(row.get("total_marks") or 100)
            GradeEntry.objects.update_or_create(
                school=school,
                exam=exam,
                student=student,
                defaults={
                    "marks_obtained": marks_obtained,
                    "total_marks": max(total, 1),
                    "remarks": (row.get("remarks") or "")[:200],
                    "entered_by": staff,
                },
            )
            saved += 1
        average = metrics.update_exam_average(exam)
        return JsonResponse({"ok": True, "saved": saved, "average_pct": average})

    return render(
        request,
        "Teachers/marks.html",
        _common(
            request,
            "marks",
            exams=exams,
            exam=exam,
            section=section,
            grid=grid,
        ),
    )


# ---------- assignments / homework ----------


@login_required
@teacher_required
def assignments(request):
    """Post homework + see at a glance how many students submitted."""
    school = _school_of(request)
    staff = _staff_of(request, school)

    if request.method == "POST":
        body, error = _parse_body(request)
        if error:
            return error
        section = _section_of(school, (body or {}).get("section_id"))
        title = ((body or {}).get("title") or "").strip()
        subject = ((body or {}).get("subject") or "").strip()
        due = (body or {}).get("due_date") or ""
        if section is None or not title or not due:
            return JsonResponse(
                {"error": "Class, title and due date are required."}, status=400
            )
        try:
            due_date = datetime.date.fromisoformat(due)
        except ValueError:
            return JsonResponse({"error": "Invalid due date."}, status=400)
        assignment = Assignment.objects.create(
            school=school,
            posted_by=staff,
            class_section=section,
            subject=subject or "General",
            title=title[:200],
            description=(body.get("description") or "").strip(),
            assigned_on=datetime.date.today(),
            due_date=due_date,
        )
        # Pre-create pending submission rows so the teacher immediately
        # gets a who-has-submitted checklist.
        for student in Student.objects.filter(
            school=school, class_section=section, status=Student.Status.ACTIVE
        ):
            AssignmentSubmission.objects.get_or_create(
                assignment=assignment, student=student
            )
        return JsonResponse({"ok": True, "id": assignment.pk})

    qs = Assignment.objects.filter(school=school).select_related(
        "class_section", "posted_by"
    )
    if staff:
        qs = qs.filter(posted_by=staff) | Assignment.objects.filter(
            school=school, posted_by__isnull=True
        )
    rows = []
    for a in qs.distinct()[:50]:
        d = a.as_dict()
        subs = a.submissions
        d["total"] = subs.count()
        d["submitted"] = subs.exclude(
            status=AssignmentSubmission.Status.PENDING
        ).count()
        rows.append(d)

    return render(
        request,
        "Teachers/assignments.html",
        _common(
            request,
            "assignments",
            assignments=rows,
            sections=teacher_sections(school, staff),
        ),
    )


@login_required
@teacher_required
def assignment_submissions(request, assignment_id):
    """Who submitted, mark received / grade / revert."""
    school = _school_of(request)
    staff = _staff_of(request, school)
    try:
        assignment = Assignment.objects.get(school=school, pk=assignment_id)
    except Assignment.DoesNotExist:
        assignment = None

    if request.method == "POST":
        body, error = _parse_body(request)
        if error:
            return error
        try:
            submission = AssignmentSubmission.objects.get(
                school=school,
                pk=int((body or {}).get("submission_id")),
            )
        except (AssignmentSubmission.DoesNotExist, TypeError, ValueError):
            return JsonResponse({"error": "Unknown submission."}, status=400)
        action = (body or {}).get("action")
        if action == "submitted":
            submission.status = AssignmentSubmission.Status.SUBMITTED
            submission.submitted_at = timezone.now()
        elif action == "grade":
            grade = (body or {}).get("grade")
            try:
                submission.grade = round(float(grade), 2)
            except (TypeError, ValueError):
                return JsonResponse({"error": "Invalid grade."}, status=400)
            submission.status = AssignmentSubmission.Status.GRADED
            submission.feedback = (body.get("feedback") or "").strip()
        elif action == "revert":
            submission.status = AssignmentSubmission.Status.PENDING
            submission.submitted_at = None
            submission.grade = None
        else:
            return JsonResponse({"error": "Unknown action."}, status=400)
        submission.save()
        return JsonResponse({"ok": True, "status": submission.status})

    rows = []
    if assignment is not None:
        subs = {
            s.student_id: s
            for s in assignment.submissions.select_related("student")
        }
        for student in Student.objects.filter(
            school=school,
            class_section=assignment.class_section,
            status=Student.Status.ACTIVE,
        ).order_by("full_name"):
            sub = subs.get(student.pk)
            if sub is None:  # student admitted after posting — create now
                sub = AssignmentSubmission.objects.create(
                    school=school, assignment=assignment, student=student
                )
            rows.append(sub.as_dict())

    return render(
        request,
        "Teachers/assignment_submissions.html",
        _common(
            request,
            "assignments",
            assignment=assignment,
            submissions=rows,
        ),
    )


# ---------- class diary ----------


@login_required
@teacher_required
def diary(request):
    """What was taught today — visible to the principal and (when the
    parent portal lands) to parents."""
    school = _school_of(request)
    staff = _staff_of(request, school)
    today = datetime.date.today()

    if request.method == "POST":
        body, error = _parse_body(request)
        if error:
            return error
        section = _section_of(school, (body or {}).get("section_id"))
        subject = ((body or {}).get("subject") or "").strip()
        taught = ((body or {}).get("taught") or "").strip()
        date_raw = (body or {}).get("date") or today.isoformat()
        try:
            date = datetime.date.fromisoformat(date_raw)
        except ValueError:
            return JsonResponse({"error": "Invalid date."}, status=400)
        if section is None or not subject or not taught:
            return JsonResponse(
                {"error": "Class, subject and what was taught are required."},
                status=400,
            )
        entry, _created = ClassDiary.objects.update_or_create(
            school=school,
            class_section=section,
            subject=subject[:100],
            date=date,
            defaults={
                "taught": taught,
                "homework": (body.get("homework") or "").strip(),
                "recorded_by": staff,
            },
        )
        return JsonResponse({"ok": True, "id": entry.pk})

    entries = ClassDiary.objects.filter(school=school).select_related(
        "class_section", "recorded_by"
    )
    if staff:
        entries = entries.filter(recorded_by=staff) | ClassDiary.objects.filter(
            school=school, recorded_by__isnull=True
        )
    entries = entries.distinct()[:30]

    return render(
        request,
        "Teachers/diary.html",
        _common(
            request,
            "diary",
            entries=[e.as_dict() for e in entries],
            sections=teacher_sections(school, staff),
            today=today,
        ),
    )


# ---------- lesson plan / curriculum tracker ----------


@login_required
@teacher_required
def lesson_plans(request):
    """Plan topics per week and track progress (draft → in progress →
    completed)."""
    school = _school_of(request)
    staff = _staff_of(request, school)

    if request.method == "POST":
        body, error = _parse_body(request)
        if error:
            return error
        topic = ((body or {}).get("topic") or "").strip()
        subject = ((body or {}).get("subject") or "").strip()
        if not topic or not subject:
            return JsonResponse(
                {"error": "Subject and topic are required."}, status=400
            )
        section = _section_of(school, (body or {}).get("section_id"))
        plan = LessonPlan.objects.create(
            school=school,
            teacher=staff,
            class_section=section,
            subject=subject[:100],
            week_label=((body.get("week_label") or "Week 1").strip())[:60],
            topic=topic[:200],
            objectives=(body.get("objectives") or "").strip(),
        )
        return JsonResponse({"ok": True, "id": plan.pk})

    qs = LessonPlan.objects.filter(school=school).select_related(
        "class_section", "teacher"
    )
    if staff:
        qs = qs.filter(teacher=staff) | LessonPlan.objects.filter(
            school=school, teacher__isnull=True
        )
    plans = qs.distinct()[:50]

    return render(
        request,
        "Teachers/lesson_plans.html",
        _common(
            request,
            "lesson_plans",
            plans=[p.as_dict() for p in plans],
            sections=teacher_sections(school, staff),
        ),
    )


@login_required
@teacher_required
@require_POST
def lesson_plan_status(request, plan_id):
    """Move a lesson plan along its tracker (draft / in_progress /
    completed)."""
    school = _school_of(request)
    body, error = _parse_body(request)
    if error:
        return error
    try:
        plan = LessonPlan.objects.get(school=school, pk=plan_id)
    except LessonPlan.DoesNotExist:
        return JsonResponse({"error": "Unknown lesson plan."}, status=404)
    status = (body or {}).get("status")
    if status not in LessonPlan.Status.values:
        return JsonResponse({"error": "Unknown status."}, status=400)
    plan.status = status
    plan.save(update_fields=["status"])
    return JsonResponse({"ok": True, "status": plan.status})


# ---------- shared resource library ----------


@login_required
@teacher_required
def resources(request):
    """Shared lesson materials between teachers of the same subject."""
    school = _school_of(request)
    staff = _staff_of(request, school)

    if request.method == "POST":
        body, error = _parse_body(request)
        if error:
            return error
        subject = ((body or {}).get("subject") or "").strip()
        title = ((body or {}).get("title") or "").strip()
        if not subject or not title:
            return JsonResponse(
                {"error": "Subject and title are required."}, status=400
            )
        link = ((body or {}).get("link") or "").strip()
        # TODO(placeholder): file uploads (FileField + storage) will fix
        # later — for now a link is required as the material's location.
        if not link:
            return JsonResponse(
                {"error": "A link is required until file uploads land."}, status=400
            )
        resource = SharedResource.objects.create(
            school=school,
            subject=subject[:100],
            title=title[:200],
            description=(body.get("description") or "").strip(),
            link=link,
            shared_by=staff,
        )
        return JsonResponse({"ok": True, "id": resource.pk})

    subject_filter = (request.GET.get("subject") or "").strip()
    qs = SharedResource.objects.filter(school=school).select_related("shared_by")
    if subject_filter:
        qs = qs.filter(subject__iexact=subject_filter)
    subjects = list(
        SharedResource.objects.filter(school=school)
        .values_list("subject", flat=True)
        .distinct()
    )

    return render(
        request,
        "Teachers/resources.html",
        _common(
            request,
            "resources",
            resources=[r.as_dict() for r in qs[:60]],
            subjects=subjects,
            subject_filter=subject_filter,
        ),
    )


# ---------- messages inbox ----------


@login_required
@teacher_required
def inbox(request):
    """One inbox: admin/parent messages + read-only staff notices."""
    school = _school_of(request)
    staff = _staff_of(request, school)

    if request.method == "POST":
        body, error = _parse_body(request)
        if error:
            return error
        action = (body or {}).get("action")
        try:
            message = TeacherMessage.objects.get(
                school=school, pk=int((body or {}).get("id"))
            )
        except (TeacherMessage.DoesNotExist, TypeError, ValueError):
            return JsonResponse({"error": "Unknown message."}, status=404)
        if action == "read":
            message.is_read = True
            message.save(update_fields=["is_read"])
            return JsonResponse({"ok": True})
        if action == "reply":
            # Routing is live: for parent-sent rows the reply is stored on
            # the same row and rendered back in the parent's message
            # thread at /parent/messages. Admin-sent rows have no admin
            # inbox surface yet — their replies are stored but unread.
            message.reply = ((body.get("reply") or "").strip())
            if not message.reply:
                return JsonResponse({"error": "Reply is empty."}, status=400)
            message.replied_at = timezone.now()
            message.is_read = True
            message.save(update_fields=["reply", "replied_at", "is_read"])
            return JsonResponse({"ok": True})
        return JsonResponse({"error": "Unknown action."}, status=400)

    messages = (
        TeacherMessage.objects.filter(school=school, staff=staff)
        if staff
        else TeacherMessage.objects.none()
    )
    notices = Notice.objects.filter(
        school=school, audience__in=[Notice.Audience.STAFF, Notice.Audience.ALL]
    )[:10]

    return render(
        request,
        "Teachers/inbox.html",
        _common(
            request,
            "inbox",
            messages=[m.as_dict() for m in messages],
            notices=[n.as_dict() for n in notices],
            staff_missing=staff is None,
        ),
    )


# ---------- leave request + balance ----------


@login_required
@teacher_required
def leave(request):
    """Submit a leave request (the PRINCIPAL approves it on the existing
    School_Admin approvals page) and see the leave balance + history."""
    school = _school_of(request)
    staff = _staff_of(request, school)
    today = datetime.date.today()

    if request.method == "POST":
        body, error = _parse_body(request)
        if error:
            return error
        if staff is None:
            # TODO(integration): until the staff link exists the request
            # can't be attached to School_Admin.LeaveRequest (it needs a
            # StaffMember FK) — link the account in the admin console.
            return JsonResponse(
                {"error": "Your teacher account is not linked to a staff record yet."}, status=400
            )
        try:
            from_date = datetime.date.fromisoformat((body or {}).get("from_date") or "")
            to_date = datetime.date.fromisoformat((body or {}).get("to_date") or "")
        except (TypeError, ValueError):
            return JsonResponse({"error": "Valid dates are required."}, status=400)
        if to_date < from_date:
            return JsonResponse(
                {"error": "End date cannot be before start date."}, status=400
            )
        # Overlap guard against pending/approved requests.
        clash = LeaveRequest.objects.filter(
            school=school, staff=staff,
            status__in=[LeaveRequest.Status.PENDING, LeaveRequest.Status.APPROVED],
            from_date__lte=to_date, to_date__gte=from_date,
        ).exists()
        if clash:
            return JsonResponse(
                {"error": "You already have a request overlapping these dates."}, status=400
            )
        # NOTE: this lands in the PRINCIPAL's approvals feed —
        # School_Admin.views.leave_decide approves/rejects it.
        row = LeaveRequest.objects.create(
            school=school,
            staff=staff,
            from_date=from_date,
            to_date=to_date,
            reason=((body.get("reason") or "").strip())[:300],
        )
        return JsonResponse({"ok": True, "id": row.pk})

    annual_used, sick_used, policy = (
        metrics.leave_balance(school, staff, today=today)
        if staff else (0, 0, metrics.LEAVE_POLICY)
    )
    rows = (
        LeaveRequest.objects.filter(school=school, staff=staff)
        if staff else LeaveRequest.objects.none()
    )

    return render(
        request,
        "Teachers/leave.html",
        _common(
            request,
            "leave",
            requests=[r.as_dict() for r in rows[:30]],
            annual_used=annual_used,
            sick_used=sick_used,
            policy=policy,
            annual_left=max(policy["annual"] - annual_used, 0),
            today=today,
            staff_missing=staff is None,
        ),
    )


# ---------- payslips ----------


@login_required
@teacher_required
def payslips(request):
    """Own payslip / salary history (read-only).

    TODO(placeholder): rows are created from the Django admin console
    until the Payroll module lands — see ``Teachers.models.Payslip``.
    """
    school = _school_of(request)
    staff = _staff_of(request, school)
    slips = (
        Payslip.objects.filter(school=school, staff=staff)
        if staff else Payslip.objects.none()
    )
    totals = {"net": 0.0, "paid": 0}
    rows = [s.as_dict() for s in slips]
    for r in rows:
        totals["net"] += r["net_pay"]
        if r["paid_on"]:
            totals["paid"] += r["net_pay"]

    return render(
        request,
        "Teachers/payslips.html",
        _common(
            request,
            "payslips",
            payslips=rows,
            totals=totals,
            staff_missing=staff is None,
        ),
    )


# ---------- private teacher notes (teachers/admin ONLY) ----------


@login_required
@teacher_required
def notes(request):
    """PRIVATE per-student notes (behaviour / strengths / concerns).

    SECURITY: these rows are NEVER shown to parents — see
    ``Teachers.models.TeacherNote``. The parent portal must not read this
    model. If a parent-facing summary is needed, generate a sanitized
    ``ReportCardComment`` instead.
    """
    school = _school_of(request)
    staff = _staff_of(request, school)

    if request.method == "POST":
        body, error = _parse_body(request)
        if error:
            return error
        student = _student_of(school, (body or {}).get("student_id"))
        text = ((body or {}).get("body") or "").strip()
        category = (body or {}).get("category")
        if student is None or not text:
            return JsonResponse(
                {"error": "Pick a student and write the note."}, status=400
            )
        if category not in TeacherNote.Category.values:
            category = TeacherNote.Category.GENERAL
        note = TeacherNote.objects.create(
            school=school,
            student=student,
            author=staff,
            category=category,
            body=text,
        )
        return JsonResponse({"ok": True, "id": note.pk})

    # The pick-list is scoped to the classes this teacher teaches (all
    # sections for the principal preview).
    sections = teacher_sections(school, staff)
    students = Student.objects.filter(
        school=school, class_section__in=sections, status=Student.Status.ACTIVE
    ).order_by("full_name")

    student = _student_of(school, request.GET.get("student"))
    if student is not None and student.class_section_id and \
            student.class_section_id not in set(s.pk for s in sections):
        student = None  # outside this teacher's scope

    rows = []
    if student is not None:
        rows = [n.as_dict() for n in student.teacher_notes.select_related("author")]

    return render(
        request,
        "Teachers/notes.html",
        _common(
            request,
            "notes",
            sections=sections,
            student=student,
            note_rows=rows,
            categories=list(TeacherNote.Category.choices),
            student_list=list(students.order_by("full_name")),
        ),
    )


# ---------- auto-generated report card comments ----------


@login_required
@teacher_required
def report_comments(request):
    """Generate a report-card comment DRAFT from marks + private notes;
    the teacher edits it before marking final. TODO(placeholder): the
    generator lives in ``metrics.generate_report_comment`` — swap its body
    for an LLM call later without touching this view."""
    school = _school_of(request)
    staff = _staff_of(request, school)
    # TODO(placeholder): derive the active term from an academic-calendar
    # model when it exists — for now a free label (will fix later).
    term = (request.GET.get("term") or "").strip() or (
        f"Term 1 {datetime.date.today().year}"
    )

    if request.method == "POST":
        body, error = _parse_body(request)
        if error:
            return error
        student = _student_of(school, (body or {}).get("student_id"))
        post_term = ((body or {}).get("term") or term).strip()[:60]
        if student is None:
            return JsonResponse({"error": "Pick a student."}, status=400)
        generated = metrics.generate_report_comment(student)
        comment, _created = ReportCardComment.objects.update_or_create(
            school=school,
            student=student,
            term=post_term,
            defaults={
                "draft": generated["text"],
                "notes_used": generated["notes_used"],
                "overall_pct": generated["overall"],
                "created_by": staff,
                "status": ReportCardComment.Status.DRAFT,
            },
        )
        return JsonResponse({
            "ok": True,
            "id": comment.pk,
            "draft": comment.draft,
            "overall": generated["overall"],
            "notes_used": generated["notes_used"],
        })

    sections = teacher_sections(school, staff)
    students = Student.objects.filter(
        school=school, class_section__in=sections, status=Student.Status.ACTIVE
    ).order_by("full_name")
    student = _student_of(school, request.GET.get("student"))
    comment = None
    if student is not None:
        comment = ReportCardComment.objects.filter(
            school=school, student=student, term=term
        ).first()

    return render(
        request,
        "Teachers/report_comments.html",
        _common(
            request,
            "report_comments",
            student=student,
            comment=comment.as_dict() if comment else None,
            term=term,
            student_list=list(students),
        ),
    )


@login_required
@teacher_required
@require_POST
def report_comment_save(request, comment_id):
    """Save the edited draft and/or mark it final (visible to parents via
    the report module once it lands)."""
    school = _school_of(request)
    body, error = _parse_body(request)
    if error:
        return error
    try:
        comment = ReportCardComment.objects.get(school=school, pk=comment_id)
    except ReportCardComment.DoesNotExist:
        return JsonResponse({"error": "Unknown comment."}, status=404)
    draft = (body or {}).get("draft")
    if draft is not None:
        comment.draft = draft.strip()
    if (body or {}).get("final"):
        comment.final = ((body.get("final") or comment.draft) or "").strip()
        comment.status = ReportCardComment.Status.FINAL
    comment.save()
    return JsonResponse({"ok": True, "status": comment.status})


# ---------- substitute-teacher finder ----------


@login_required
@teacher_required
def substitute(request):
    """Find free teachers for the periods of teachers who are on approved
    leave on a date, and arrange the cover."""
    school = _school_of(request)
    staff = _staff_of(request, school)
    today = datetime.date.today()
    date_raw = request.GET.get("date") or today.isoformat()
    try:
        date = datetime.date.fromisoformat(date_raw)
    except ValueError:
        date = today
    day = metrics.day_code(date)

    if request.method == "POST":
        body, error = _parse_body(request)
        if error:
            return error
        try:
            slot = TimetableSlot.objects.get(
                school=school, pk=int((body or {}).get("slot_id"))
            )
        except (TimetableSlot.DoesNotExist, TypeError, ValueError):
            return JsonResponse({"error": "Unknown timetable slot."}, status=404)
        try:
            sub = StaffMember.objects.get(
                school=school, is_active=True, pk=int((body or {}).get("substitute_id"))
            )
        except (StaffMember.DoesNotExist, TypeError, ValueError):
            return JsonResponse({"error": "Unknown substitute."}, status=400)
        try:
            cover_date = datetime.date.fromisoformat((body or {}).get("date") or "")
        except (TypeError, ValueError):
            return JsonResponse({"error": "Invalid date."}, status=400)
        assignment, _created = SubstituteAssignment.objects.update_or_create(
            school=school,
            slot=slot,
            date=cover_date,
            defaults={
                "original_teacher": slot.teacher,
                "substitute": sub,
                "arranged_by": request.user if request.user.is_authenticated else None,
            },
        )
        # TODO(integration): notify the substitute (SMS/push) when the
        # notification module lands.
        return JsonResponse({"ok": True, "id": assignment.pk})

    # Staff on approved leave covering this date -> their slots that day.
    on_leave = LeaveRequest.objects.filter(
        school=school,
        status=LeaveRequest.Status.APPROVED,
        from_date__lte=date,
        to_date__gte=date,
    ).select_related("staff")
    absent_ids = {lr.staff_id for lr in on_leave}

    gaps = []
    if absent_ids:
        slots = (
            TimetableSlot.objects.filter(
                school=school, day=day, teacher_id__in=absent_ids
            )
            .select_related("class_section", "teacher")
        )
        existing = {
            (sa.slot_id): sa
            for sa in SubstituteAssignment.objects.filter(
                school=school, date=date
            ).select_related("substitute")
        }
        for slot in slots:
            candidates = metrics.substitute_candidates(school, slot, date)
            covered = existing.get(slot.pk)
            gaps.append({
                "slot": slot.as_dict(),
                "teacher": slot.teacher.full_name if slot.teacher_id else "—",
                "covered_by": covered.substitute.full_name if covered else None,
                "candidates": candidates,
            })

    substitutes = [
        {"id": t.pk, "name": t.full_name}
        for t in StaffMember.objects.filter(school=school, is_active=True)
        .order_by("full_name")
    ]

    return render(
        request,
        "Teachers/substitute.html",
        _common(
            request,
            "substitute",
            date=date,
            day_display=date.strftime("%A"),
            gaps=gaps,
            substitutes=substitutes,
        ),
    )


# ---------- early-warning analytics ----------


@login_required
@teacher_required
def analytics(request):
    """Which students are falling behind: attendance + marks-trend
    early warnings — actionable early, not a term-end report."""
    school = _school_of(request)
    warnings = metrics.early_warnings(school)
    counts = {"attendance": 0, "low_marks": 0, "declining": 0}
    for w in warnings:
        for flag in w["flags"]:
            counts[flag] = counts.get(flag, 0) + 1
    return render(
        request,
        "Teachers/analytics.html",
        _common(
            request,
            "analytics",
            warnings=warnings,
            counts=counts,
        ),
    )










