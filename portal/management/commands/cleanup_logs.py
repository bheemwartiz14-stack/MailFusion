"""
Management command: purge old sync logs per the retention window.
"""

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from portal.repositories import SyncRepository


class Command(BaseCommand):
    help = "Delete sync logs older than SYNC_LOG_RETENTION_DAYS."

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=settings.SYNC_LOG_RETENTION_DAYS)
        deleted = SyncRepository().delete_older_than(cutoff)
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} log(s) older than {cutoff.isoformat()}."))