"""Parent / Family dashboard views.

Access model: every view is wrapped in ``parent_required`` — the signed-in
user must hold a ``SchoolUser`` membership with the ``parent`` role (see
``Parents.utils``). All data is resolved through ``utils.current_school``,
``utils.current_profile`` and ``utils.children_of``, so a parent can only ever
see their OWN children's rows in their ONE school.

Child switching: every page renders the guardian's child list; the selected
child lives in ``?child=<student_id>`` and is persisted to the session so the
choice sticks while navigating. An id that is not one of the parent's own
children is silently ignored (falls back to the first child).

Read-only surfaces (digest, attendance, results, homework, fees list,
notices) read the teacher/principal models (``Teachers``, ``School_Admin``) —
the school stays the single source of truth. The only things a parent
creates here are ``Teachers.TeacherMessage`` rows (``sender_type=parent``)
and, when the school allows it, online fee payments.

Security note: ``Teachers.TeacherNote`` (private teacher notes) is never read
on any parent surface — the digest's "note from teacher" comes from the class
diary and replied parent messages only.
"""
import datetime
import json

from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from School_Admin.models import (
    ExamRecord,
    FeePayment,
    Notice,
    StudentFeeInvoice,
)
from Teachers.models import (
    Assignment,
    AssignmentSubmission,
    ClassDiary,
    GradeEntry,
    StudentAttendance,
    TeacherMessage,
    TimetableSlot,
)

from .utils import (
    child_for_selection,
    children_of,
    current_profile,
    current_school,
    day_code,
    is_parent,
    portal_setting,
)


def _is_parent_user(user):
    return is_parent(user)


parent_required = user_passes_test(_is_parent_user, login_url="/")


def _school_of(request):
    """The tenant scope of this parent (their ONE school)."""
    return current_school(request.user)


def _profile_of(request, school):
    """The ``Parents.ParentProfile`` of this parent (None until auth+school)."""
    return current_profile(request.user, school)


def _common(request, nav_active, **extra):
    """Shared template context: school, profile, the child switcher list and
    the currently selected child (persisted in the session)."""
    school = _school_of(request)
    profile = _profile_of(request, school)
    children = children_of(profile, school)
    child_id = request.GET.get("child")
    if child_id is not None:
        request.session["parent_child_id"] = child_id
        child_id_to_use = child_id
    else:
        child_id_to_use = request.session.get("parent_child_id")
    child = child_for_selection(children, child_id_to_use)
    ctx = {
        "school": school,
        "profile": profile,
        "children": children,
        "child": child,
        "setting": portal_setting(school),
        "nav_active": nav_active,
    }
    ctx.update(extra)
    return ctx


def _parse_body(request):
    try:
        return json.loads(request.body or "{}"), None
    except json.JSONDecodeError:
        return None, JsonResponse({"error": "Invalid request body."}, status=400)
def _outstanding(invoice):
    """Amount still owed on an invoice (Decimal, never negative)."""
    remaining = float(invoice.amount) - float(invoice.paid_amount)
    return max(remaining, 0.0)


def _attendance_summary(student):
    """(counts by mark, overall present-ish %) for one child."""
    counts = {"present": 0, "absent": 0, "late": 0, "excused": 0}
    if student is None:
        return counts, None
    for row in StudentAttendance.objects.filter(student=student):
        if row.mark in counts:
            counts[row.mark] += 1
    total = sum(counts.values())
    pct = (
        round((counts["present"] + counts["late"]) / total * 100, 1)
        if total else None
    )
    return counts, pct


def _assignments_with_state(school, student):
    """The section's assignments with THIS child's submission state.

    Reads ``Teachers.Assignment`` + ``Teachers.AssignmentSubmission`` — the
    same rows the teacher dashboard manages (parents only read them).
    """
    if student is None or student.class_section_id is None:
        return []
    assignments = Assignment.objects.filter(
        school=school, class_section=student.class_section
    ).select_related("class_section")[:100]
    submissions = {
        s.assignment_id: s
        for s in AssignmentSubmission.objects.filter(school=school, student=student)
    }
    today = datetime.date.today()
    items = []
    for a in assignments:
        sub = submissions.get(a.pk)
        submitted = sub is not None and sub.status in (
            AssignmentSubmission.Status.SUBMITTED,
            AssignmentSubmission.Status.GRADED,
        )
        items.append({
            "assignment": a,
            "submission": sub,
            "submitted": submitted,
            "graded": (
                sub is not None
                and sub.status == AssignmentSubmission.Status.GRADED
            ),
            "overdue": a.due_date < today and not submitted,
            "due_soon": today <= a.due_date <= today + datetime.timedelta(days=3),
            "assigned_today": a.assigned_on == today,
            "status": (sub.status if sub else "pending"),
        })
    return items
def _subject_teachers(school, student):
    """{subject: teacher StaffMember} resolvable from the child's timetable."""
    if student is None or student.class_section_id is None:
        return {}
    mapping = {}
    slots = (
        TimetableSlot.objects.filter(
            school=school, class_section=student.class_section,
            teacher__isnull=False,
        ).select_related("teacher")
    )
    for slot in slots:
        mapping.setdefault(slot.subject, slot.teacher)
    return mapping


def _my_message_threads(profile, children):
    """This parent's ``TeacherMessage`` rows grouped as one thread per
    child + subject (newest thread first, oldest message first inside)."""
    child_ids = {c.pk for c in children}
    if profile is None or not child_ids:
        return []
    rows = (
        TeacherMessage.objects.filter(
            school=profile.school,
            sender_type=TeacherMessage.SenderType.PARENT,
            sent_by=profile.user,
            about_student_id__in=child_ids,
        )
        .select_related("about_student", "staff")
        .order_by("about_student__full_name", "subject", "created_at")
    )
    threads = {}
    for row in rows:
        key = (row.about_student_id, (row.subject or "").strip().lower())
        thread = threads.setdefault(
            key,
            {
                "student": row.about_student,
                "subject": row.subject,
                "staff": row.staff,
                "messages": [],
                "last_at": row.created_at,
            },
        )
        thread["messages"].append(row)
        if row.created_at > thread["last_at"]:
            thread["last_at"] = row.created_at
    threads_list = list(threads.values())
    threads_list.sort(key=lambda t: t["last_at"], reverse=True)
    return threads_list


def _digest_of(school, student, today, profile):
    """One child's "today at school" digest.

    Built read-only from the Teachers / School_Admin rows the school already
    writes: today's attendance mark, today's timetable, homework given today
    (class diary + assignments), and the teacher's latest reply on this
    parent's messages about this child. ``Teachers.TeacherNote`` is NEVER
    read here (teacher/admin only).
    """
    section = student.class_section
    digest = {
        "student": student,
        "attendance": None,
        "slots": [],
        "diary": [],
        "homework": [],
        "teacher_note": None,
    }
    if section is not None:
        digest["slots"] = list(
            TimetableSlot.objects.filter(
                school=school, class_section=section, day=day_code(today)
            ).select_related("teacher").order_by("period")
        )
        digest["diary"] = list(
            ClassDiary.objects.filter(
                school=school, class_section=section, date=today
            ).select_related("recorded_by")
        )
        digest["homework"] = list(
            Assignment.objects.filter(
                school=school, class_section=section, assigned_on=today
            ).select_related("posted_by")
        )
    digest["attendance"] = (
        StudentAttendance.objects.filter(
            school=school, student=student, date=today
        ).first()
    )
    if profile is not None:
        note_row = (
            TeacherMessage.objects.filter(
                school=school,
                about_student=student,
                sender_type=TeacherMessage.SenderType.PARENT,
                sent_by=profile.user,
                reply__gt="",
            ).select_related("staff").order_by("-replied_at").first()
        )
        digest["teacher_note"] = note_row
    return digest
# ---------- home: family dashboard + today at school ----------


@login_required
@parent_required
def dashboard(request):
    """The family dashboard: a snapshot per child (siblings row) and the
    full "today at school" digest for the selected child, plus alerts and the
    latest notices addressed to parents."""
    school = _school_of(request)
    profile = _profile_of(request, school)
    children = children_of(profile, school)
    child = child_for_selection(
        children, request.GET.get("child") or request.session.get("parent_child_id")
    )
    today = datetime.date.today()
    week_ago = today - datetime.timedelta(days=7)

    digest = _digest_of(school, child, today, profile) if child else None

    # siblings snapshot: today's attendance + outstanding fees per child
    sibling_snapshots = []
    for s in children:
        att = StudentAttendance.objects.filter(
            school=school, student=s, date=today
        ).first()
        invoices = StudentFeeInvoice.objects.filter(school=school, student=s)
        owed = sum(_outstanding(inv) for inv in invoices)
        owed_count = sum(
            1 for inv in invoices
            if inv.status != StudentFeeInvoice.Status.PAID
        )
        sibling_snapshots.append({
            "student": s,
            "attendance": att,
            "owed": owed,
            "owed_count": owed_count,
        })

    # alerts across the selected child
    recent_absences = StudentAttendance.objects.filter(
        school=school, student=child, date__gte=week_ago,
        mark__in=(StudentAttendance.Mark.ABSENT, StudentAttendance.Mark.LATE),
    ).order_by("-date")[:5] if child else StudentAttendance.objects.none()

    open_assignments, overdue_assignments = [], []
    upcoming_exams = ExamRecord.objects.none()
    if child is not None:
        items = _assignments_with_state(school, child)
        open_assignments = [i for i in items if not i["submitted"] and not i["overdue"]]
        overdue_assignments = [i for i in items if i["overdue"]]
        if child.class_section_id:
            upcoming_exams = ExamRecord.objects.filter(
                school=school, class_section=child.class_section,
                average_pct__isnull=True,
            ).order_by("exam_date")[:5]

    fees_due_count = 0
    fees_due_amount = 0.0
    if child is not None:
        for inv in StudentFeeInvoice.objects.filter(school=school, student=child):
            if inv.status != StudentFeeInvoice.Status.PAID:
                fees_due_count += 1
                fees_due_amount += _outstanding(inv)

    unread_messages = 0
    if profile is not None:
        unread_messages = TeacherMessage.objects.filter(
            school=school,
            sent_by=profile.user,
            sender_type=TeacherMessage.SenderType.PARENT,
        ).exclude(reply="").count()

    notices = Notice.objects.filter(
        school=school,
        audience__in=(Notice.Audience.PARENTS, Notice.Audience.ALL),
    )[:5]

    return render(
        request,
        "Parents/dashboard.html",
        _common(
            request,
            "overview",
            digest=digest,
            sibling_snapshots=sibling_snapshots,
            recent_absences=recent_absences,
            open_count=len(open_assignments),
            overdue_assignments=overdue_assignments,
            upcoming_exams=upcoming_exams,
            fees_due_count=fees_due_count,
            fees_due_amount=fees_due_amount,
            unread_messages=unread_messages,
            notices=notices,
        ),
    )
# ---------- attendance & alerts ----------


@login_required
@parent_required
def attendance(request):
    """The selected child's month-by-month attendance (defaults to the
    current month; jump with ``?month=YYYY-MM``) plus recent absences /
    lateness alerts for the last 7 days."""
    school = _school_of(request)
    profile = _profile_of(request, school)
    children = children_of(profile, school)
    child = child_for_selection(
        children, request.GET.get("child") or request.session.get("parent_child_id")
    )
    today = datetime.date.today()
    week_ago = today - datetime.timedelta(days=7)

    month_str = request.GET.get("month") or today.strftime("%Y-%m")
    try:
        year, month = (int(p) for p in month_str.split("-"))
        if not 1 <= month <= 12:
            raise ValueError
    except ValueError:
        year, month = today.year, today.month

    records = StudentAttendance.objects.none()
    if child is not None:
        records = (
            StudentAttendance.objects.filter(
                school=school, student=child,
                date__year=year, date__month=month,
            ).select_related("class_section", "marked_by").order_by("-date")
        )

    counts = {"present": 0, "absent": 0, "late": 0, "excused": 0}
    for record in records:
        if record.mark in counts:
            counts[record.mark] += 1
    total = sum(counts.values())
    pct = (
        round((counts["present"] + counts["late"]) / total * 100, 1)
        if total else None
    )

    recent_alerts = StudentAttendance.objects.filter(
        school=school, student=child, date__gte=week_ago,
        mark__in=(StudentAttendance.Mark.ABSENT, StudentAttendance.Mark.LATE),
    ).order_by("-date")[:10] if child else StudentAttendance.objects.none()

    def _fmt(y, m):
        return f"{y:04d}-{m:02d}"

    prev_y, prev_m = (year - 1, 12) if month == 1 else (year, month - 1)
    next_y, next_m = (year + 1, 1) if month == 12 else (year, month + 1)
    month_label = datetime.date(year, month, 1).strftime("%B %Y")

    return render(
        request,
        "Parents/attendance.html",
        _common(
            request,
            "attendance",
            records=records,
            counts=counts,
            pct=pct,
            total=total,
            month_label=month_label,
            prev_month=_fmt(prev_y, prev_m),
            next_month=_fmt(next_y, next_m),
            is_current=(year, month) == (today.year, today.month),
            recent_alerts=recent_alerts,
        ),
    )


# ---------- fee status & online payment ----------


@login_required
@parent_required
def fees(request):
    """The selected child's fee status: invoices, outstanding total and the
    recent payment history. Paying is gated by the school's
    ``ParentPortalSetting.allow_online_payment`` switch."""
    school = _school_of(request)
    profile = _profile_of(request, school)
    children = children_of(profile, school)
    child = child_for_selection(
        children, request.GET.get("child") or request.session.get("parent_child_id")
    )
    setting = portal_setting(school)

    invoices = StudentFeeInvoice.objects.none()
    if child is not None:
        invoices = (
            StudentFeeInvoice.objects.filter(school=school, student=child)
            .select_related("fee_head").order_by("-due_date")
        )
    outstanding_total = sum(_outstanding(inv) for inv in invoices)
    history = (
        FeePayment.objects.filter(invoice__in=invoices)
        .select_related("invoice").order_by("-paid_on")[:10]
    )
    return render(
        request,
        "Parents/fees.html",
        _common(
            request,
            "fees",
            invoices=invoices,
            outstanding_total=outstanding_total,
            can_pay=(
                child is not None
                and setting is not None
                and setting.allow_online_payment
            ),
            payments=history,
        ),
    )
@login_required
@parent_required
@require_POST
def invoice_pay(request, invoice_id):
    """Pay a child's invoice online (simulated — records a real
    ``FeePayment`` with method ``online`` and updates the invoice status
    exactly like the student / principal flows do).

    Only allowed when the school's ``ParentPortalSetting.allow_online_payment``
    is on, only on an invoice of the parent's OWN child, and only for a
    positive amount up to the outstanding balance.
    """
    school = _school_of(request)
    profile = _profile_of(request, school)
    data, err = _parse_body(request)
    if err:
        return err
    child_id = data.get("child_id") or request.session.get("parent_child_id")
    children = children_of(profile, school)
    child = child_for_selection(children, child_id)
    setting = portal_setting(school)
    if child is None:
        return JsonResponse(
            {"error": "Pick one of your children first."}, status=400
        )
    if setting is None or not setting.allow_online_payment:
        return JsonResponse(
            {"error": "Online payment is not enabled for your school."}, status=403
        )
    invoice = StudentFeeInvoice.objects.filter(
        school=school, pk=invoice_id, student=child
    ).first()
    if invoice is None:
        return JsonResponse({"error": "Invoice not found."}, status=404)
    if invoice.status == StudentFeeInvoice.Status.PAID:
        return JsonResponse({"error": "This invoice is already paid."}, status=400)

    outstanding = _outstanding(invoice)
    try:
        amount = float(data.get("amount") or outstanding)
    except (TypeError, ValueError):
        return JsonResponse({"error": "Amount must be a number."}, status=400)
    if amount <= 0 or amount > outstanding + 0.001:
        return JsonResponse(
            {"error": f"Amount must be between 0 and {outstanding:.2f}."}, status=400
        )

    payment = FeePayment.objects.create(
        invoice=invoice,
        amount=round(amount, 2),
        paid_on=datetime.date.today(),
        method=FeePayment.Method.ONLINE,
        received_by="Parent portal (online)",
    )
    paid_total = invoice.paid_amount
    if paid_total >= float(invoice.amount) - 0.001:
        invoice.status = StudentFeeInvoice.Status.PAID
    elif paid_total > 0:
        invoice.status = StudentFeeInvoice.Status.PARTIAL
    invoice.save(update_fields=["status"])
    return JsonResponse({
        "payment": payment.as_dict(),
        "invoice": invoice.as_dict(),
        "message": "Payment recorded.",
    })


# ---------- results ----------


@login_required
@parent_required
def results(request):
    """The selected child's report card: every graded exam with the class
    average next to it, plus the upcoming (ungraded) exams for the section."""
    school = _school_of(request)
    profile = _profile_of(request, school)
    children = children_of(profile, school)
    child = child_for_selection(
        children, request.GET.get("child") or request.session.get("parent_child_id")
    )

    rows = []
    overall_obtained = overall_total = 0.0
    if child is not None:
        entries = (
            GradeEntry.objects.filter(school=school, student=child)
            .select_related("exam", "exam__class_section")
            .order_by("exam__exam_date")
        )
        for entry in entries:
            rows.append({
                "exam": entry.exam,
                "marks_obtained": entry.marks_obtained,
                "total_marks": entry.total_marks,
                "percentage": entry.percentage,
                "class_average": entry.exam.average_pct,
            })
            overall_obtained += float(entry.marks_obtained)
            overall_total += entry.total_marks
    overall_pct = (
        round(overall_obtained / overall_total * 100, 1) if overall_total else None
    )

    upcoming = ExamRecord.objects.none()
    if child is not None and child.class_section_id:
        upcoming = ExamRecord.objects.filter(
            school=school, class_section=child.class_section,
            average_pct__isnull=True,
        ).order_by("exam_date")

    return render(
        request,
        "Parents/results.html",
        _common(
            request,
            "results",
            rows=rows,
            overall_pct=overall_pct,
            overall_obtained=overall_obtained,
            overall_total=overall_total,
            upcoming=upcoming,
        ),
    )
# ---------- homework / assignments ----------


@login_required
@parent_required
def homework(request):
    """The selected child's homework / assignments with the submission state
    (read-only for parents — students submit from their own portal)."""
    school = _school_of(request)
    profile = _profile_of(request, school)
    children = children_of(profile, school)
    child = child_for_selection(
        children, request.GET.get("child") or request.session.get("parent_child_id")
    )
    items = _assignments_with_state(school, child)
    return render(
        request,
        "Parents/homework.html",
        _common(
            request,
            "homework",
            items=items,
            pending_count=sum(
                1 for i in items if not i["submitted"] and not i["overdue"]
            ),
            overdue_count=sum(1 for i in items if i["overdue"]),
        ),
    )


# ---------- notices ----------


@login_required
@parent_required
def notices(request):
    """Circulars addressed to parents (or everyone) at this school."""
    school = _school_of(request)
    items = Notice.objects.filter(
        school=school,
        audience__in=(Notice.Audience.PARENTS, Notice.Audience.ALL),
    )[:100]
    return render(
        request,
        "Parents/notices.html",
        _common(request, "notices", notices=items),
    )


# ---------- message a teacher (one thread per child/subject) ----------


@login_required
@parent_required
def messages(request):
    """The parent's conversations with teachers — grouped into one thread per
    child + subject, newest thread first. Composing creates a
    ``Teachers.TeacherMessage`` row (sender_type=parent, sent_by=this user)
    that lands in the teacher's existing inbox; the teacher's reply is stored
    on the same row and rendered back here as the conversation."""
    school = _school_of(request)
    profile = _profile_of(request, school)
    children = children_of(profile, school)
    child = child_for_selection(
        children, request.GET.get("child") or request.session.get("parent_child_id")
    )
    threads = _my_message_threads(profile, children)
    subject_teachers = _subject_teachers(school, child)
    return render(
        request,
        "Parents/messages.html",
        _common(
            request,
            "messages",
            threads=threads,
            subject_teachers=subject_teachers,
            can_message=(
                child is not None
                and portal_setting(school) is not None
                and portal_setting(school).allow_messaging
            ),
        ),
    )


@login_required
@parent_required
@require_POST
def message_send(request):
    """Send one parent → teacher message about a child + subject.

    Creates a ``Teachers.TeacherMessage`` row (sender_type=parent,
    sent_by=this user, about_student=child) so it lands in the teacher's
    existing inbox exactly as the TODO(integration) on that model describes.
    The recipient is the teacher mapped to the child's subject in the
    timetable.
    """
    school = _school_of(request)
    profile = _profile_of(request, school)
    children = children_of(profile, school)
    child = child_for_selection(
        children, request.POST.get("child_id") or request.session.get("parent_child_id")
    )
    setting = portal_setting(school)

    if profile is None or child is None:
        return JsonResponse(
            {"error": "Pick one of your children first."}, status=400
        )
    if setting is None or not setting.allow_messaging:
        return JsonResponse(
            {"error": "Messaging is disabled for your school."}, status=403
        )

    subject = (request.POST.get("subject") or "").strip()
    body = (request.POST.get("body") or "").strip()
    if not subject or not body:
        return JsonResponse(
            {"error": "Subject and message are required."}, status=400
        )

    teacher = _subject_teachers(school, child).get(subject)
    if teacher is None:
        return JsonResponse(
            {
                "error": (
                    f"No teacher is mapped for {child.full_name}'s "
                    f"{subject} class yet — ask the school to set the timetable."
                )
            },
            status=400,
        )

    message = TeacherMessage.objects.create(
        school=school,
        staff=teacher,
        about_student=child,
        sender_type=TeacherMessage.SenderType.PARENT,
        sender_name=(
            profile.guardian_name
            or request.user.get_full_name()
            or request.user.get_username()
        ),
        subject=subject,
        body=body,
        sent_by=request.user,
    )
    return JsonResponse(
        {"message": message.as_dict(), "ok": True}, status=201
    )
