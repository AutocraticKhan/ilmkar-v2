"""Services for the Front Desk / Admissions dashboard.

Small, pure helpers for the numbered references used across the desk:
per-school sequential ``pass_no`` / ``card_no`` values (year-scoped so the
printed numbers read naturally, e.g. ``GP-2026-0001`` / ``IC-2026-0001``).
"""
import datetime


def _next_number(school, prefix, field, manager, today=None):
    """Next ``prefix-YYYY-NNNN`` by scanning the highest existing sequence
    number for the current year on one school's rows."""
    today = today or datetime.date.today()
    year = str(today.year)
    prefix_dash = prefix + "-"
    highest = 0
    for number in manager.values_list(field, flat=True):
        if number.startswith(prefix_dash):
            parts = number.split("-")
            if len(parts) == 3 and parts[1] == year:
                try:
                    highest = max(highest, int(parts[2]))
                except ValueError:
                    continue
    return f"{prefix}-{year}-{highest + 1:04d}"


def next_pass_no(school, today=None):
    """Next gate-pass number, e.g. ``GP-2026-0001``."""
    return _next_number(school, "GP", "pass_no", school.fd_gate_passes.all(), today=today)


def next_card_no(school, today=None):
    """Next ID-card number, e.g. ``IC-2026-0001``."""
    return _next_number(school, "IC", "card_no", school.fd_id_cards.all(), today=today)