"""Models for the Student dashboard.

``Student`` is the student-facing cockpit for ONE student at ONE school:
timetable, assignments + submissions, results & report cards, the
attendance record, the school library (books issued / due dates), fee
status (view, and pay when the school allows it), notices and
quizzes / online tests.

Conventions followed here (matching Teachers / School_Admin / school_owner):
- every model is scoped to a ``SAAS_admin.School`` so the tenant boundary
  is enforced in views via ``Student.utils.current_school``;
- the signed-in user is linked to their record via ``StudentProfile``
  (mirroring ``Teachers.TeacherProfile``) with fallback matching by
  admission number / full name (see ``Student.utils.current_student``);
- the read-only surfaces (timetable, results, attendance, fees, notices)
  read the existing ``Teachers`` / ``School_Admin`` models so the school
  stays the single source of truth — nothing is duplicated here.

TODO(placeholder): ``Book`` / ``BookIssue`` stand in for the real Library
module (barcode scanning, reservations, fines). TODO(placeholder):
``Quiz`` / ``QuizQuestion`` / ``QuizAttempt`` stand in for the real
online-testing module (question banks, timers per question, negative
marking). TODO(integration): when those modules land, the teacher /
principal dashboards must be able to manage them — keep the school +
section FK shapes stable.
"""
from django.contrib.auth.models import User
from django.db import models

from SAAS_admin.models import School
from School_Admin.models import ClassSection, Student


class PortalSetting(models.Model):
    """Per-school switches for what students may do from their portal.

    TODO(placeholder): currently view-only surfaces stay view-only and the
    only actions are submitting assignments, taking quizzes and (optionally)
    paying fees online. When the parent portal lands, mirror these switches
    there (or move them into a shared school-settings model).
    """

    school = models.OneToOneField(
        School, on_delete=models.CASCADE, related_name="student_portal_setting"
    )
    allow_online_payment = models.BooleanField(default=True)
    allow_assignment_submit = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Student portal settings @ {self.school.name}"


class StudentProfile(models.Model):
    """Links a platform ``User`` (a ``SchoolUser`` with role ``student``)
    to their ``School_Admin.Student`` record.

    TODO(integration): the long-term fix is a ``user`` FK on
    ``School_Admin.Student`` itself — when that lands, migrate this link
    into it and keep ``Student.utils.current_student`` as a thin wrapper.
    Until then this row is optional; resolution falls back to
    admission-no / full-name matching (see utils.py).
    """

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="student_profiles"
    )
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="student_profile"
    )
    student = models.OneToOneField(
        Student, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="student_profile",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["user__username"]

    def __str__(self):
        who = self.student.full_name if self.student_id else self.user.get_username()
        return f"{who} (student profile)"

    def as_dict(self):
        return {
            "id": self.pk,
            "school_id": self.school_id,
            "user_id": self.user_id,
            "username": self.user.get_username(),
            "student_id": self.student_id,
            "student_name": self.student.full_name if self.student_id else None,
        }


class Book(models.Model):
    """A title in the school library catalogue.

    TODO(placeholder): replace with the real Library module (ISBN lookup,
    cover images, racks/shelves, reservation queue). TODO(integration):
    ``copies_available`` is maintained by the issue/return flow — when the
    real module lands it must keep this counter or the student dashboard's
    availability badge breaks.
    """

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="library_books"
    )
    title = models.CharField(max_length=250)
    author = models.CharField(max_length=150, blank=True, default="")
    isbn = models.CharField(max_length=20, blank=True, default="")
    category = models.CharField(max_length=80, blank=True, default="")
    copies_total = models.PositiveIntegerField(default=1)
    copies_available = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return f"{self.title} · {self.author or '—'} @ {self.school.name}"

    @property
    def label(self):
        return f"{self.title} ({self.author})" if self.author else self.title

    def as_dict(self):
        return {
            "id": self.pk,
            "title": self.title,
            "author": self.author or "—",
            "isbn": self.isbn or "—",
            "category": self.category or "—",
            "copies_total": self.copies_total,
            "copies_available": self.copies_available,
            "is_active": self.is_active,
        }


class BookIssue(models.Model):
    """One copy of a book issued to one student, with its due date.

    Powers the student dashboard's library page (books issued, due dates,
    overdue highlighting) and, later, the librarian's issue register.

    TODO(placeholder): issues are recorded from the admin console for now;
    a student "return request" action can be added when the real module
    lands. TODO(integration): overdue fines belong to the real fees
    module — when it lands, auto-generate a ``School_Admin.FeeHead``
    invoice per overdue issue instead of only flagging it here.
    """

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="book_issues"
    )
    book = models.ForeignKey(
        Book, on_delete=models.CASCADE, related_name="issues"
    )
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="book_issues"
    )
    issued_on = models.DateField()
    due_date = models.DateField()
    returned_on = models.DateField(null=True, blank=True)
    issued_by = models.CharField(max_length=120, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-issued_on", "book__title"]

    def __str__(self):
        return f"{self.book.title} → {self.student.full_name} (due {self.due_date})"

    @property
    def is_returned(self):
        return self.returned_on is not None

    @property
    def is_overdue(self):
        """Overdue = not returned and past the due date."""
        if self.returned_on is not None:
            return False
        import datetime

        return self.due_date < datetime.date.today()

    def as_dict(self):
        return {
            "id": self.pk,
            "book_id": self.book_id,
            "book": self.book.title,
            "author": self.book.author or "—",
            "issued_on": self.issued_on.isoformat(),
            "due_date": self.due_date.isoformat(),
            "returned_on": (
                self.returned_on.isoformat() if self.returned_on else None
            ),
            "is_returned": self.is_returned,
            "is_overdue": self.is_overdue,
        }


class Quiz(models.Model):
    """An online test / quiz the teacher publishes for a class section.

    TODO(placeholder): replace with the real online-testing module
    (question banks, randomized order, per-question timers, anti-cheat).
    TODO(integration): results should roll into the report card — when the
    real Exams module splits papers per term, add a link from
    ``School_Admin.ExamRecord`` here so quiz scores appear next to exam
    marks. Teachers manage quizzes from their dashboard once it lands;
    for now rows are seeded from the admin console.
    """

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="quizzes"
    )
    class_section = models.ForeignKey(
        ClassSection, on_delete=models.CASCADE, related_name="quizzes"
    )
    subject = models.CharField(max_length=100)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    opens_at = models.DateTimeField(null=True, blank=True)
    closes_at = models.DateTimeField(null=True, blank=True)
    duration_minutes = models.PositiveSmallIntegerField(default=15)
    published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.class_section.label} · {self.subject})"

    @property
    def total_marks(self):
        return sum(q.marks for q in self.questions.all())

    def as_dict(self):
        from django.utils import timezone

        return {
            "id": self.pk,
            "class_section": self.class_section.label,
            "subject": self.subject,
            "title": self.title,
            "description": self.description,
            "opens_at": (
                timezone.localtime(self.opens_at).strftime("%b %d, %Y %H:%M")
                if self.opens_at else None
            ),
            "closes_at": (
                timezone.localtime(self.closes_at).strftime("%b %d, %Y %H:%M")
                if self.closes_at else None
            ),
            "duration_minutes": self.duration_minutes,
            "published": self.published,
        }


class QuizQuestion(models.Model):
    """One multiple-choice question of a quiz.

    ``options`` is a JSON list of strings (2–6 options);
    ``correct_index`` points at the right one (0-based). The correct
    answer is NEVER sent to the student's browser — scoring happens
    server-side in ``Student.views.quiz_take``.
    """

    quiz = models.ForeignKey(
        Quiz, on_delete=models.CASCADE, related_name="questions"
    )
    text = models.TextField()
    options = models.JSONField(default=list)
    correct_index = models.PositiveSmallIntegerField(default=0)
    marks = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["quiz", "pk"]

    def __str__(self):
        return f"{self.quiz.title} · Q{self.pk}: {self.text[:60]}"

    def as_student_dict(self):
        """Shape sent to the taking-student's browser — no correct answer."""
        return {
            "id": self.pk,
            "text": self.text,
            "options": self.options,
            "marks": self.marks,
        }

    def as_dict(self):
        return {
            "id": self.pk,
            "quiz_id": self.quiz_id,
            "text": self.text,
            "options": self.options,
            "correct_index": self.correct_index,
            "marks": self.marks,
        }


class QuizAttempt(models.Model):
    """One student's finished run of a quiz: their chosen answers (a JSON
    list of 0-based option indexes aligned with the questions) and the
    server-computed score.

    One attempt per student per quiz — see the unique constraint. The
    score is computed at submit time (never trusted from the client).
    """

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="quiz_attempts"
    )
    quiz = models.ForeignKey(
        Quiz, on_delete=models.CASCADE, related_name="attempts"
    )
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="quiz_attempts"
    )
    answers = models.JSONField(default=list)
    score = models.FloatField(default=0)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-submitted_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["quiz", "student"], name="unique_attempt_per_quiz_student"
            )
        ]

    def __str__(self):
        return (
            f"{self.student.full_name} · {self.quiz.title}: "
            f"{self.score}/{self.quiz.total_marks}"
        )

    @property
    def total_marks(self):
        """Total marks the quiz was worth at attempt time."""
        return self.quiz.total_marks

    def as_dict(self):
        from django.utils import timezone

        return {
            "id": self.pk,
            "quiz_id": self.quiz_id,
            "student_id": self.student_id,
            "student_name": self.student.full_name,
            "answers": self.answers,
            "score": self.score,
            "total_marks": self.quiz.total_marks,
            "submitted_at": timezone.localtime(self.submitted_at).strftime(
                "%b %d, %Y %H:%M"
            ),
        }