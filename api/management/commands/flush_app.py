"""
management command: flush_app
─────────────────────────────
Wipes all app-specific data while keeping Django's own system tables
(contenttypes, auth permissions, sessions, migrations).

Usage:
    python manage.py flush_app              # asks for confirmation
    python manage.py flush_app --yes        # no prompt (CI / scripts)
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Delete all Findify app data (users, reports, claims, etc.) without touching migrations."

    def add_arguments(self, parser):
        parser.add_argument(
            "--yes", "-y",
            action="store_true",
            dest="yes",
            help="Skip confirmation prompt",
        )

    def handle(self, *args, **options):
        if not options["yes"]:
            self.stdout.write(
                self.style.WARNING(
                    "\nThis will DELETE ALL app data:\n"
                    "  • AuditLog\n"
                    "  • Notification\n"
                    "  • ClaimRequest\n"
                    "  • MatchSuggestion\n"
                    "  • ReportImage\n"
                    "  • LostReport\n"
                    "  • UserProfile\n"
                    "  • All non-superuser User accounts\n"
                )
            )
            confirm = input("Type  yes  to confirm: ").strip()
            if confirm != "yes":
                self.stdout.write(self.style.ERROR("Aborted."))
                return

        from api.models import (
            AuditLog, Notification, ClaimRequest,
            MatchSuggestion, ReportImage, LostReport,
            UserProfile, User,
        )

        steps = [
            ("AuditLog",        AuditLog.objects.all()),
            ("Notifications",   Notification.objects.all()),
            ("ClaimRequests",   ClaimRequest.objects.all()),
            ("MatchSuggestions",MatchSuggestion.objects.all()),
            ("ReportImages",    ReportImage.objects.all()),
            ("LostReports",     LostReport.objects.all()),
            ("UserProfiles",    UserProfile.objects.all()),
            ("Users (non-superuser)", User.objects.filter(is_superuser=False)),
        ]

        total = 0
        for label, qs in steps:
            count = qs.count()
            qs.delete()
            total += count
            self.stdout.write(f"  ✓  Deleted {count:>5}  {label}")

        self.stdout.write(self.style.SUCCESS(f"\nDone. {total} records removed."))
        self.stdout.write("Your superuser account and migrations are untouched.\n")