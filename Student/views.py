"""Student dashboard views.

Access model: every view is wrapped in ``student_required`` — the
signed-in user must hold a ``SchoolUser`` membership with the ``student``
role (see ``Student.utils``). All data is resolved through
``utils.current_school`` and ``utils.current_student``, so a student can
only ever see their OWN rows in their ONE school.

Read-only surfaces (timetable, results, attendance, notices, fee list)
read the teacher/principal models (``Teachers``, ``School_Admin``) — the
school stays the single source of truth. The only things a student
creates here are assignment submissions, quiz attempts and (when the
school allows it) online fee payments.

Every mutating view takes a JSON POST body (same pattern as
``Teachers.views``) and answers ``JsonResponse``.
"""
import datetime
import json

from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
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
    GradeEntry,
    StudentAttendance,
    TimetableSlot,
)

from .models import BookIssue, Quiz, QuizAttempt
from .utils import (
    DAY_ORDER,
    current_school,
    current_student,
    day_code,
    is_student,
    portal_setting,
)


def _school_of(request):
    """The tenant scope of this student (their ONE school)."""
    return current_school(request.user)


def _student_of(request, school):
    """The School_Admin.Student record of this student (None until linked)."""
    return current_student(request.user, school)


def _is_student(user):
    return is_student(user)


student_required = user_passes_test(_is_student, login_url="/")


def _parse_body(request):
    try:
        return json.loads(request.body or "{}"), None
    except json.JSONDecodeError:
        return None, JsonResponse({"error": "Invalid request body."}, status=400)


def _common(request, nav_active, **extra):
    """Shared template context: school, student record, portal switches."""
    school = _school_of(request)
    student = _student_of(request, school)
    ctx = {
        "school": school,
        "student": student,
        "setting": portal_setting(school),
        "nav_active": nav_active,
    }
    ctx.update(extra)
    return ctx


def _section_of(student):
    """The student's class section (may be None until the admin assigns one)."""
    return student.class_section if student is not None else None


def _assignments_with_state(school, student):
    """The section's assignments with THIS student's submission state.

    Reads ``Teachers.Assignment`` + ``Teachers.AssignmentSubmission`` —
    the same rows the teacher's dashboard manages (the student portal
    flips ``pending`` rows to ``submitted`` here, exactly as the
    TODO(integration) note on that model describes).
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
        })
    return items


def _attendance_summary(school, student):
    """(counts by mark, overall present-ish %) for the signed-in student."""
    counts = {"present": 0, "absent": 0, "late": 0, "excused": 0}
    if student is None:
        return counts, None
    for row in StudentAttendance.objects.filter(school=school, student=student):
        if row.mark in counts:
            counts[row.mark] += 1
    total = sum(counts.values())
    # late still counts towards attendance, excused days don't hurt it
    pct = (
        round((counts["present"] + counts["late"]) / total * 100, 1)
        if total else None
    )
    return counts, pct


# ---------- home: today at a glance ----------


@login_required
@student_required
def dashboard(request):
    """Today's classes, what's due, overdue library books, next quiz and
    the latest notices — the student's day in one screen."""
    school = _school_of(request)
    student = _student_of(request, school)
    today = datetime.date.today()
    section = _section_of(student)

    # today's timetable
    today_slots = []
    if section is not None:
        today_slots = list(
            TimetableSlot.objects.filter(
                school=school, class_section=section, day=day_code(today)
            ).select_related("class_section", "teacher").order_by("period")
        )

    # assignments: open + overdue counts and the next few open ones
    assignment_items = _assignments_with_state(school, student)
    open_assignments = [
        i for i in assignment_items if not i["submitted"] and not i["overdue"]
    ]
    overdue_assignments = [i for i in assignment_items if i["overdue"]]

    # attendance record
    attendance_counts, attendance_pct = _attendance_summary(school, student)

    # library: active issues + overdue count
    active_issues = overdue_books = 0
    next_due_book = None
    if student is not None:
        active = (
            BookIssue.objects.filter(
                school=school, student=student, returned_on__isnull=True
            ).select_related("book").order_by("due_date")
        )
        active_issues = active.count()
        overdue_books = sum(1 for i in active if i.is_overdue)
        next_due_book = active.first()

    # fees: outstanding invoices
    fees_due_count = fees_due_amount = 0
    next_fee_due = latest_invoice = None
    if student is not None:
        invoices = (
            StudentFeeInvoice.objects.filter(school=school, student=student)
            .exclude(status=StudentFeeInvoice.Status.PAID)
            .order_by("due_date")
        )
        fees_due_count = invoices.count()
        fees_due_amount = sum(
            float(inv.amount) - float(inv.paid_amount) for inv in invoices
        )
        next_fee_due = invoices.first()
        latest_invoice = (
            StudentFeeInvoice.objects.filter(school=school, student=student)
            .order_by("-created_at").first()
        )

    # next published quiz for the section (not yet attempted, window open)
    next_quiz = None
    if section is not None:
        attempted_ids = set(
            QuizAttempt.objects.filter(school=school, student=student)
            .values_list("quiz_id", flat=True)
        )
        now = timezone.now()
        for q in Quiz.objects.filter(
            school=school, class_section=section, published=True
        ).prefetch_related("questions"):
            if q.pk in attempted_ids:
                continue
            if q.opens_at is not None and q.opens_at > now:
                continue
            if q.closes_at is not None and q.closes_at < now:
                continue
            if not q.questions.exists():
                continue
            next_quiz = q
            break

    # latest notices for students
    notices = Notice.objects.filter(
        school=school,
        audience__in=(Notice.Audience.STUDENTS, Notice.Audience.ALL),
    )[:5]

    return render(
        request,
        "Student/dashboard.html",
        _common(
            request,
            "overview",
            today_slots=today_slots,
            open_assignments=open_assignments[:5],
            overdue_count=len(overdue_assignments),
            attendance_counts=attendance_counts,
            attendance_pct=attendance_pct,
            active_issues=active_issues,
            overdue_books=overdue_books,
            next_due_book=next_due_book,
            fees_due_count=fees_due_count,
            fees_due_amount=fees_due_amount,
            next_fee_due=next_fee_due,
            latest_invoice=latest_invoice,
            next_quiz=next_quiz,
            notices=notices,
        ),
    )


# ---------- timetable ----------


@login_required
@student_required
def timetable(request):
    """The full weekly timetable of the student's class section."""
    school = _school_of(request)
    student = _student_of(request, school)
    section = _section_of(student)

    slots = TimetableSlot.objects.none()
    if section is not None:
        slots = (
            TimetableSlot.objects.filter(school=school, class_section=section)
            .select_related("class_section", "teacher")
            .order_by("period")
        )

    week = [
        {"day": day, "slots": [s for s in slots if s.day == day]}
        for day in DAY_ORDER
    ]
    return render(
        request,
        "Student/timetable.html",
        _common(
            request,
            "timetable",
            week=week,
            today_day=day_code(datetime.date.today()),
            section=section,
        ),
    )


# ---------- assignments & submission ----------


@login_required
@student_required
def assignments(request):
    """This section's assignments with the student's submission state; the
    submit action lives on ``assignment_submit``."""
    school = _school_of(request)
    student = _student_of(request, school)
    setting = portal_setting(school)
    items = _assignments_with_state(school, student)
    can_submit = (
        student is not None
        and student.class_section_id is not None
        and setting is not None
        and setting.allow_assignment_submit
    )
    return render(
        request,
        "Student/assignments.html",
        _common(
            request,
            "assignments",
            items=items,
            can_submit=can_submit,
            pending_count=sum(
                1 for i in items if not i["submitted"] and not i["overdue"]
            ),
            overdue_count=sum(1 for i in items if i["overdue"]),
        ),
    )


@login_required
@student_required
@require_POST
def assignment_submit(request, assignment_id):
    """Flip this student's ``AssignmentSubmission`` to ``submitted``.

    Upserts the row the teacher's dashboard reads (``get_or_create`` so
    re-submitting is safe). Already-graded work cannot be overwritten —
    that would falsify the teacher's grade book.
    """
    school = _school_of(request)
    student = _student_of(request, school)
    if student is None or student.class_section_id is None:
        return JsonResponse(
            {"error": "Your account is not linked to a class section yet."},
            status=403,
        )
    setting = portal_setting(school)
    if setting is None or not setting.allow_assignment_submit:
        return JsonResponse(
            {"error": "Online submission is disabled for your school."}, status=403
        )
    assignment = Assignment.objects.filter(
        school=school, pk=assignment_id, class_section=student.class_section
    ).first()
    if assignment is None:
        return JsonResponse({"error": "Assignment not found."}, status=404)

    submission, created = AssignmentSubmission.objects.get_or_create(
        school=school,
        assignment=assignment,
        student=student,
        defaults={
            "status": AssignmentSubmission.Status.SUBMITTED,
            "submitted_at": timezone.now(),
        },
    )
    if submission.status == AssignmentSubmission.Status.GRADED:
        return JsonResponse(
            {"error": "This assignment is already graded and can't be re-submitted."},
            status=400,
        )
    submission.status = AssignmentSubmission.Status.SUBMITTED
    submission.submitted_at = timezone.now()
    submission.save(update_fields=["status", "submitted_at"])
    return JsonResponse({
        "created": created,
        "submission": submission.as_dict(),
        "message": "Assignment submitted.",
    })


# ---------- results & report card ----------


@login_required
@student_required
def results(request):
    """Report card: every graded exam for this student with the class
    average next to it, plus upcoming (ungraded) exams for the section."""
    school = _school_of(request)
    student = _student_of(request, school)
    section = _section_of(student)

    rows = []
    overall_obtained = overall_total = 0.0
    if student is not None:
        entries = (
            GradeEntry.objects.filter(school=school, student=student)
            .select_related("exam", "exam__class_section")
            .order_by("exam__exam_date")
        )
        for entry in entries:
            rows.append({
                "exam": entry.exam,
                "marks_obtained": entry.marks_obtained,
                "total_marks": entry.total_marks,
                "percentage": entry.percentage,
                # the exam's class-wide average (kept live by
                # Teachers.metrics.update_exam_average)
                "class_average": entry.exam.average_pct,
            })
            overall_obtained += float(entry.marks_obtained)
            overall_total += entry.total_marks
    overall_pct = (
        round(overall_obtained / overall_total * 100, 1) if overall_total else None
    )

    upcoming = ExamRecord.objects.none()
    if section is not None:
        upcoming = ExamRecord.objects.filter(
            school=school, class_section=section, average_pct__isnull=True
        ).order_by("exam_date")

    return render(
        request,
        "Student/results.html",
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


# ---------- attendance record ----------


@login_required
@student_required
def attendance(request):
    """The student's month-by-month attendance record (defaults to the
    current month; jump with ``?month=YYYY-MM``)."""
    school = _school_of(request)
    student = _student_of(request, school)
    today = datetime.date.today()

    month_str = request.GET.get("month") or today.strftime("%Y-%m")
    try:
        year, month = (int(p) for p in month_str.split("-"))
        if not 1 <= month <= 12:
            raise ValueError
    except ValueError:
        year, month = today.year, today.month

    records = StudentAttendance.objects.none()
    if student is not None:
        records = (
            StudentAttendance.objects.filter(
                school=school, student=student,
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

    def _fmt(y, m):
        return f"{y:04d}-{m:02d}"

    prev_y, prev_m = (year - 1, 12) if month == 1 else (year, month - 1)
    next_y, next_m = (year + 1, 1) if month == 12 else (year, month + 1)
    month_label = datetime.date(year, month, 1).strftime("%B %Y")

    return render(
        request,
        "Student/attendance.html",
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
        ),
    )


# ---------- library ----------


@login_required
@student_required
def library(request):
    """Books issued to this student: active issues with due dates
    (overdue highlighted) plus the returned history."""
    school = _school_of(request)
    student = _student_of(request, school)

    active = history = BookIssue.objects.none()
    if student is not None:
        base = BookIssue.objects.filter(school=school, student=student)
        active = (
            base.filter(returned_on__isnull=True)
            .select_related("book").order_by("due_date")
        )
        history = (
            base.filter(returned_on__isnull=False)
            .select_related("book").order_by("-returned_on")
        )
    overdue_count = sum(1 for issue in active if issue.is_overdue)

    return render(
        request,
        "Student/library.html",
        _common(
            request,
            "library",
            active=active,
            history=history,
            overdue_count=overdue_count,
        ),
    )


# ---------- fees ----------


def _outstanding(invoice):
    """Amount still owed on an invoice (Decimal, never negative)."""
    remaining = float(invoice.amount) - float(invoice.paid_amount)
    return max(remaining, 0.0)


@login_required
@student_required
def fees(request):
    """Fee status: every invoice issued to this student (view-only list;
    the pay action lives on ``invoice_pay`` and is gated by the school's
    ``PortalSetting.allow_online_payment`` switch)."""
    school = _school_of(request)
    student = _student_of(request, school)
    setting = portal_setting(school)

    invoices = StudentFeeInvoice.objects.none()
    if student is not None:
        invoices = (
            StudentFeeInvoice.objects.filter(school=school, student=student)
            .select_related("fee_head").order_by("-due_date")
        )
    outstanding_total = sum(_outstanding(inv) for inv in invoices)
    history = (
        FeePayment.objects.filter(invoice__in=invoices)
        .select_related("invoice").order_by("-paid_on")[:10]
    )
    return render(
        request,
        "Student/fees.html",
        _common(
            request,
            "fees",
            invoices=invoices,
            outstanding_total=outstanding_total,
            can_pay=(
                setting is not None and setting.allow_online_payment
            ),
            payments=history,
        ),
    )


@login_required
@student_required
@require_POST
def invoice_pay(request, invoice_id):
    """Pay an invoice online (simulated — records a real ``FeePayment``
    with method ``online`` and updates the invoice status exactly like the
    principal's ``School_Admin.views.invoice_pay`` does).

    Only allowed when the school's ``PortalSetting.allow_online_payment``
    is on, only for the student's OWN invoice, and only for a positive
    amount up to the outstanding balance.

    TODO(placeholder): this is an in-app ledger entry, not a card/wallet
    charge. When the payments gateway lands, create the charge first and
    record the ``FeePayment`` from its webhook instead.
    """
    school = _school_of(request)
    student = _student_of(request, school)
    if student is None:
        return JsonResponse(
            {"error": "Your account is not linked to a student record yet."},
            status=403,
        )
    setting = portal_setting(school)
    if setting is None or not setting.allow_online_payment:
        return JsonResponse(
            {"error": "Online payment is not enabled for your school."}, status=403
        )
    invoice = StudentFeeInvoice.objects.filter(
        school=school, pk=invoice_id, student=student
    ).first()
    if invoice is None:
        return JsonResponse({"error": "Invoice not found."}, status=404)
    if invoice.status == StudentFeeInvoice.Status.PAID:
        return JsonResponse({"error": "This invoice is already paid."}, status=400)

    data, err = _parse_body(request)
    if err:
        return err
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
        received_by="Student portal (online)",
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


# ---------- notices ----------


@login_required
@student_required
def notices(request):
    """Circulars addressed to students (or everyone) at this school."""
    school = _school_of(request)
    notices = Notice.objects.filter(
        school=school,
        audience__in=(Notice.Audience.STUDENTS, Notice.Audience.ALL),
    )[:100]
    return render(
        request,
        "Student/notices.html",
        _common(request, "notices", notices=notices),
    )


# ---------- quizzes / online tests ----------


def _quiz_of(school, student, quiz_id):
    """Resolve a published quiz for this student's section, ONLY within
    the tenant scope (None otherwise)."""
    if student is None or student.class_section_id is None:
        return None
    return Quiz.objects.filter(
        school=school,
        pk=quiz_id,
        published=True,
        class_section=student.class_section,
    ).prefetch_related("questions").first()


def _quiz_window(quiz, now):
    """(is_open, state) for the quiz at ``now``: state in
    open / upcoming / closed."""
    if quiz.opens_at is not None and quiz.opens_at > now:
        return False, "upcoming"
    if quiz.closes_at is not None and quiz.closes_at < now:
        return False, "closed"
    return True, "open"


def _quizzes_with_state(school, student):
    """Published quizzes for the section with this student's attempt state."""
    if student is None or student.class_section_id is None:
        return []
    attempts = {
        a.quiz_id: a
        for a in QuizAttempt.objects.filter(school=school, student=student)
    }
    now = timezone.now()
    items = []
    for quiz in (
        Quiz.objects.filter(
            school=school, class_section=student.class_section, published=True
        ).prefetch_related("questions")
    ):
        is_open, state = _quiz_window(quiz, now)
        attempt = attempts.get(quiz.pk)
        items.append({
            "quiz": quiz,
            "attempt": attempt,
            "is_open": is_open and attempt is None,
            "state": "done" if attempt is not None else state,
            "question_count": quiz.questions.count(),
        })
    return items


@login_required
@student_required
def quizzes(request):
    """Published online tests for this section: open to take, upcoming,
    closed, and the student's own scores."""
    school = _school_of(request)
    student = _student_of(request, school)
    items = _quizzes_with_state(school, student)
    return render(
        request,
        "Student/quizzes.html",
        _common(
            request,
            "quizzes",
            items=items,
            open_count=sum(1 for i in items if i["is_open"]),
            done_count=sum(1 for i in items if i["attempt"] is not None),
        ),
    )


@login_required
@student_required
def quiz_take(request, quiz_id):
    """Take one quiz (GET) / submit answers (POST JSON).

    Security notes:
    - the quiz must be published and belong to the student's section —
      resolved through ``_quiz_of`` (never a raw id from the request);
    - questions are sent WITHOUT the correct answers; scoring happens
      server-side here and is never trusted from the client;
    - one attempt per student per quiz (unique constraint) — a finished
      attempt redirects to the score view instead of allowing a retake.
    """
    school = _school_of(request)
    student = _student_of(request, school)
    quiz = _quiz_of(school, student, quiz_id)
    if quiz is None:
        return redirect("Student:quizzes")

    attempt = QuizAttempt.objects.filter(quiz=quiz, student=student).first()
    if request.method == "POST" and attempt is None:
        data, err = _parse_body(request)
        if err:
            return err
        now = timezone.now()
        is_open, _state = _quiz_window(quiz, now)
        if not is_open:
            return JsonResponse(
                {"error": "This quiz is not open right now."}, status=400
            )
        answers = data.get("answers")
        if not isinstance(answers, dict):
            return JsonResponse(
                {"error": "Send answers as {question_id: chosen_index}."}, status=400
            )
        score = 0
        scored_answers = []
        for question in quiz.questions.all():
            chosen = answers.get(str(question.pk), answers.get(question.pk))
            try:
                chosen = int(chosen) if chosen is not None else -1
            except (TypeError, ValueError):
                chosen = -1
            if chosen == question.correct_index:
                score += question.marks
            scored_answers.append(chosen)
        attempt = QuizAttempt.objects.create(
            school=school, quiz=quiz, student=student,
            answers=scored_answers, score=score,
        )
        if request.headers.get("Accept") == "application/json":
            return JsonResponse({"attempt": attempt.as_dict()})
        return redirect("Student:quiz-take", quiz_id=quiz.pk)

    if attempt is not None:
        # already taken: show the score (no retake — one attempt per quiz)
        return render(
            request,
            "Student/quiz_result.html",
            _common(
                request,
                "quizzes",
                quiz=quiz,
                attempt=attempt,
                total_marks=quiz.total_marks,
            ),
        )

    is_open, state = _quiz_window(quiz, timezone.now())
    if not is_open:
        return render(
            request,
            "Student/quizzes.html",
            _common(request, "quizzes", items=_quizzes_with_state(school, student)),
        )
    questions = [q.as_student_dict() for q in quiz.questions.all()]
    return render(
        request,
        "Student/quiz_take.html",
        _common(
            request,
            "quizzes",
            quiz=quiz,
            questions=questions,
            duration_minutes=quiz.duration_minutes,
            state=state,
        ),
    )