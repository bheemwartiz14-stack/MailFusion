"""
Management command: renew expiring Microsoft Graph webhook subscriptions.
"""

from django.core.management.base import BaseCommand

from portal.services.sync_services import SyncService


class Command(BaseCommand):
    help = "Renew expiring Microsoft Graph change notification subscriptions."

    def handle(self, *args, **options):
        renewed, failed = SyncService().renew_webhooks(worker="cli")
        self.stdout.write(self.style.SUCCESS(f"Renewed {renewed} subscription(s), {failed} failed."))