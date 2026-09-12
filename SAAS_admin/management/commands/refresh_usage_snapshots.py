"""Capture real usage snapshots for the operator console.

Usage:
    python manage.py refresh_usage_snapshots
    python manage.py refresh_usage_snapshots --day 2026-09-12

Replaces the dummy values previously written by ``seed_demo_data`` —
computes today's logins + active students per school from live data
(see ``SAAS_admin.services``). Cron-friendly: safe to re-run, it upserts.
"""
import datetime

from django.core.management.base import BaseCommand

from SAAS_admin.services import refresh_snapshots


class Command(BaseCommand):
    help = "Compute today's real usage snapshot (logins, active students) per school."

    def add_arguments(self, parser):
        parser.add_argument(
            "--day",
            default=None,
            help="ISO date to (re)compute; defaults to today.",
        )

    def handle(self, *args, **options):
        day = None
        if options["day"]:
            try:
                day = datetime.date.fromisoformat(options["day"])
            except ValueError:
                self.stdout.write(
                    self.style.ERROR(f"Invalid --day value: {options['day']}")
                )
                return
        snapshots = refresh_snapshots(day=day)
        self.stdout.write(
            self.style.SUCCESS(
                f"Usage snapshots refreshed for {len(snapshots)} school(s) "
                f"({(day or snapshots[0].date) if snapshots else 'no schools'})."
            )
        )