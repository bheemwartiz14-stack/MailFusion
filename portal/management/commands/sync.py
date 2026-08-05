"""
Management command: trigger account synchronization from the CLI.

Usage:
    python manage.py sync --all              # sync every syncable account
    python manage.py sync --account <pk>     # sync a single account
"""

from django.core.management.base import BaseCommand, CommandError

from portal.models import OutlookAccount
from portal.services.sync_services import SyncService


class Command(BaseCommand):
    help = "Synchronize Outlook accounts via the Microsoft Graph delta feed."

    def add_arguments(self, parser):
        parser.add_argument("--all", action="store_true", dest="sync_all", help="Sync all syncable accounts")
        parser.add_argument("--account", dest="account", type=str, help="Sync a single account by UUID")
        parser.add_argument("--include-paused", action="store_true", dest="include_paused", help="Sync paused accounts too")

    def handle(self, *args, **options):
        worker = "cli"
        if options["account"]:
            account = OutlookAccount.objects.filter(pk=options["account"]).first()
            if account is None:
                raise CommandError("Account not found.")
            result = SyncService().sync_account(account, worker=worker)
            self._report(account, result)
            return

        service = SyncService()
        accounts = OutlookAccount.objects.filter(
            is_sync_paused=not options["include_paused"],
            oauth_status__in=["connected", "expired"],
            status__in=["active", "error"],
        )
        if options["sync_all"] or not options["account"]:
            for account in accounts if options["include_paused"] else accounts.filter(is_sync_paused=False):
                result = service.sync_account(account, worker=worker)
                self._report(account, result)

    def _report(self, account, result):
        if result.success:
            self.stdout.write(
                self.style.SUCCESS(
                    f"{account.email}: +{result.added} new, updated {result.updated}, removed {result.removed}"
                )
            )
        else:
            self.stderr.write(self.style.ERROR(f"{account.email}: FAILED - {result.error}"))