"""
Management command: run the system health check and print a summary.
"""

from django.core.management.base import BaseCommand

from portal.services.sync_services import SyncService
from portal.utils.tasks import broker_healthy, queue_depth


class Command(BaseCommand):
    help = "Run infrastructure health checks for the sync engine."

    def handle(self, *args, **options):
        healthy = broker_healthy()
        depth = queue_depth()
        metrics = SyncService().sync_metrics()

        self.stdout.write(f"Redis reachable:   {healthy}")
        self.stdout.write(f"Queue depth:       {depth}")
        self.stdout.write(f"Total accounts:    {metrics['total_accounts']}")
        self.stdout.write(f"Active accounts:   {metrics['active_accounts']}")
        self.stdout.write(f"Paused accounts:   {metrics['paused_accounts']}")
        self.stdout.write(f"Needs reauth:      {metrics['needs_reauthorization']}")
        self.stdout.write(f"Failed syncs:      {metrics['failed_syncs']}")
        self.stdout.write(f"Queued jobs:       {metrics['queued_jobs']}")
        self.stdout.write(f"Running jobs:      {metrics['running_jobs']}")

        if not healthy:
            self.stderr.write(self.style.ERROR("Health check FAILED: Redis unreachable."))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS("Health check OK."))