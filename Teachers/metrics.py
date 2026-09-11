"""Metrics + smart helpers for the Teacher / Staff dashboard.

Everything here is pure queryset math so views stay thin:
- ``sync_attendance_snapshot`` — pushes per-student marks up into the
  principal dashboard's ``School_Admin.AttendanceSnapshot``;
- ``update_exam_average`` — recomputes ``School_Admin.ExamRecord``;
- ``leave_balance`` — placeholder policy vs approved leaves;
- ``substitute_candidates`` — free teachers for a given slot/date;
- ``early_warnings`` — attendance + marks trend per student;
- ``generate_report_comment`` — auto-drafted report-card comment.

TODO(placeholder): thresholds (attendance floor, weak-mark floor, trend
drop) are hardcoded constants; surface them as per-school settings when
the school-settings module exists.
"""
import datetime

from School_Admin.models import LeaveRequest, StaffMember, Student

from .models import (
    GradeEntry,
    StudentAttendance,
    SubstituteAssignment,
    TeacherNote,
    TimetableSlot,
)

# TODO(placeholder): replace with a LeavePolicy model / school settings.
LEAVE_POLICY = {"annual": 20, "sick": 10}

ATTENDANCE_FLOOR = 75.0  # % below this = falling behind on attendance
WEAK_MARK_FLOOR = 40.0   # % below this = weak marks
TREND_DROP = 15.0        # pts dropped between earlier and recent exams


def day_code(day):
    """``datetime.date`` -> TimetableSlot.Day code ("Mon" ...). The Day
    choices are exactly the ``%a`` abbreviations, so this is a straight
    mapping."""
    return day.strftime("%a")


def sync_attendance_snapshot(school, section, date):
    """Recompute the section's daily totals from per-student marks and
    upsert ``School_Admin.AttendanceSnapshot`` (present counts PRESENT+LATE,
    absent counts ABSENT+EXCUSED)."""
    from School_Admin.models import AttendanceSnapshot

    marks = StudentAttendance.objects.filter(
        school=school, class_section=section, date=date
    )
    present = marks.filter(
        mark__in=[StudentAttendance.Mark.PRESENT, StudentAttendance.Mark.LATE]
    ).count()
    absent = marks.filter(
        mark__in=[StudentAttendance.Mark.ABSENT, StudentAttendance.Mark.EXCUSED]
    ).count()
    if present == 0 and absent == 0:
        return None
    snapshot, _created = AttendanceSnapshot.objects.update_or_create(
        school=school,
        class_section=section,
        date=date,
        defaults={"present": present, "absent": absent},
    )
    return snapshot


def update_exam_average(exam):
    """Recompute ``ExamRecord.average_pct`` from its GradeEntry rows so the
    principal dashboard + reports stay in sync."""
    entries = GradeEntry.objects.filter(exam=exam)
    pcts = [e.percentage for e in entries if e.percentage is not None]
    exam.average_pct = round(sum(pcts) / len(pcts), 1) if pcts else None
    exam.save(update_fields=["average_pct"])
    return exam.average_pct


def leave_balance(school, staff, today=None):
    """(annual_used, sick_used, policy) — days are counted as inclusive
    spans of APPROVED ``School_Admin.LeaveRequest`` rows in the current
    year. TODO(placeholder): real HR policy engine (carry-forward, half
    days, monthly accrual) replaces these constants."""
    today = today or datetime.date.today()
    used = {"annual": 0, "sick": 0}
    # TODO(placeholder): LeaveRequest has no leave-type field yet — every
    # approved day is counted against the annual quota until HR adds one.
    rows = LeaveRequest.objects.filter(
        school=school, staff=staff, status=LeaveRequest.Status.APPROVED,
        from_date__year=today.year,
    )
    for row in rows:
        used["annual"] += (row.to_date - row.from_date).days + 1
    return used["annual"], used["sick"], LEAVE_POLICY


def substitute_candidates(school, slot, date):
    """Teachers who could take ``slot`` on ``date``: active staff at the
    school, not the absent teacher, not themselves teaching that period,
    not on approved leave covering the date, and not already substituting
    elsewhere that period.

    Returns a list of dicts for the template. TODO(integration): when the
    real timetable module lands, factor in room clashes + part-time hours.
    """
    day = day_code(date)
    busy_ids = set(
        TimetableSlot.objects.filter(school=school, day=day, period=slot.period)
        .exclude(teacher__isnull=True)
        .values_list("teacher_id", flat=True)
    )
    on_leave_ids = set(
        LeaveRequest.objects.filter(
            school=school,
            status=LeaveRequest.Status.APPROVED,
            from_date__lte=date,
            to_date__gte=date,
        ).values_list("staff_id", flat=True)
    )
    substituting_ids = set(
        SubstituteAssignment.objects.filter(
            school=school, date=date, slot__period=slot.period
        ).values_list("substitute_id", flat=True)
    )
    excluded = busy_ids | on_leave_ids | substituting_ids | {slot.teacher_id}
    candidates = StaffMember.objects.filter(
        school=school, is_active=True
    ).exclude(pk__in=excluded)
    return [
        {"id": t.pk, "name": t.full_name, "designation": t.designation or "—"}
        for t in candidates.order_by("full_name")
    ]


def early_warnings(school, today=None, attendance_days=30):
    """Students at risk, computed from attendance + marks trends — the
    early-warning list (NOT a term-end report).

    Flags per student:
      - ``attendance`` — marked-attendance % over the last N days is below
        ``ATTENDANCE_FLOOR``;
      - ``low_marks`` — overall average % below ``WEAK_MARK_FLOOR``;
      - ``declining`` — recent-half exam average dropped >= ~TREND_DROP
        points vs the earlier half.

    TODO(placeholder): pure-Python aggregation is fine at current scale;
    move to annotated queries / a materialised per-student snapshot when
    the student count grows (or when the real Analytics module lands).
    """
    today = today or datetime.date.today()
    since = today - datetime.timedelta(days=attendance_days)
    rows = []
    students = Student.objects.filter(
        school=school, status=Student.Status.ACTIVE
    ).select_related("class_section")
    present_marks = [StudentAttendance.Mark.PRESENT, StudentAttendance.Mark.LATE]
    for student in students:
        att = StudentAttendance.objects.filter(student=student, date__gte=since)
        total_marked = att.count()
        att_pct = None
        if total_marked:
            present = att.filter(mark__in=present_marks).count()
            att_pct = round(present / total_marked * 100, 1)
        grades = list(
            GradeEntry.objects.filter(student=student)
            .select_related("exam").order_by("exam__exam_date")
        )
        pcts = [g.percentage for g in grades if g.percentage is not None]
        avg_pct = round(sum(pcts) / len(pcts), 1) if pcts else None
        trend = None
        if len(pcts) >= 2:
            half = max(len(pcts) // 2, 1)
            earlier = sum(pcts[:half]) / half
            recent = sum(pcts[half:]) / (len(pcts) - half)
            if recent < earlier - TREND_DROP / 2:
                trend = round(recent - earlier, 1)
        flags = []
        if att_pct is not None and att_pct < ATTENDANCE_FLOOR:
            flags.append("attendance")
        if avg_pct is not None and avg_pct < WEAK_MARK_FLOOR:
            flags.append("low_marks")
        if trend is not None:
            flags.append("declining")
        if flags:
            rows.append({
                "student_id": student.pk,
                "student_name": student.full_name,
                "class_section": (
                    student.class_section.label if student.class_section_id else "—"
                ),
                "attendance_pct": att_pct,
                "avg_pct": avg_pct,
                "trend": trend,
                "flags": flags,
            })
    return rows


def generate_report_comment(student, notes_limit=5):
    """Auto-draft a report-card comment from the student's marks + private
    teacher notes. The teacher edits the draft before it goes anywhere.

    TODO(placeholder): template-based generation on purpose — swap the
    body of this function for an LLM call or a richer template engine
    later; the view + model stay unchanged.
    """
    grades = list(
        GradeEntry.objects.filter(student=student).select_related("exam")
    )
    by_subject = {}
    for g in grades:
        if g.percentage is None:
            continue
        subject = (g.exam.subject or g.exam.exam_name or "General").strip()
        by_subject.setdefault(subject, []).append(g.percentage)
    subject_avgs = {
        s: round(sum(p) / len(p), 1) for s, p in by_subject.items() if p
    }
    overall = (
        round(sum(subject_avgs.values()) / len(subject_avgs), 1)
        if subject_avgs else None
    )
    best = max(subject_avgs, key=subject_avgs.get) if subject_avgs else None
    weakest = min(subject_avgs, key=subject_avgs.get) if subject_avgs else None

    notes = list(
        TeacherNote.objects.filter(student=student).order_by("-created_at")
    )[:notes_limit]
    strengths = [n.body for n in notes if n.category == TeacherNote.Category.STRENGTH]
    concerns = [n.body for n in notes if n.category == TeacherNote.Category.CONCERN]
    behavior = [n.body for n in notes if n.category == TeacherNote.Category.BEHAVIOR]

    # qualitative band from the overall average
    if overall is None:
        band = "a steady"
    elif overall >= 80:
        band = "an excellent"
    elif overall >= 65:
        band = "a good"
    elif overall >= WEAK_MARK_FLOOR:
        band = "a satisfactory"
    else:
        band = "a concerning"

    parts = []
    opener = f"{student.full_name} has had {band} term"
    if overall is not None:
        opener += f", with an overall average of {overall}%"
    if best and weakest and best != weakest:
        opener += f" — strongest in {best}, while {weakest} needs attention"
    opener += "."
    parts.append(opener)
    if strengths:
        parts.append("In class, teachers have noted: " + "; ".join(strengths[:2]) + ".")
    if behavior:
        parts.append("Behaviour observed: " + "; ".join(behavior[:2]) + ".")
    if concerns:
        parts.append("Areas to work on next term: " + "; ".join(concerns[:2]) + ".")
    if overall is not None and overall < WEAK_MARK_FLOOR:
        parts.append("We recommend a structured catch-up plan and closer home follow-up.")
    parts.append("With continued support, we look forward to further progress.")

    return {
        "text": " ".join(parts),
        "overall": overall,
        "subject_avgs": subject_avgs,
        "notes_used": len(notes),
    }



