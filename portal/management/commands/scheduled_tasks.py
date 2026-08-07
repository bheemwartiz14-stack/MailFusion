"""
Management command: run recurring background maintenance.

Replace Celery Beat. Schedule this via cron / systemd timer at whatever
cadence suits you (every minute is fine; each job is internally throttled by
its configured interval). Example crontab line:

    * * * * *  cd /path/to/app && .venv/bin/python manage.py scheduled_tasks
"""

import logging
import time

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run recurring background jobs (sync, token/webhook refresh, cleanup, health)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--once",
            action="store_true",
            help="Run every job now, regardless of interval."
            " Useful for initial runs or manual invocation.",
        )

    def _interval(self, settings_name, default):
        from django.conf import settings

        try:
            value = getattr(settings, settings_name, default)
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    def handle(self, *args, **options):
        from django.conf import settings

        from portal.tasks import (
            cleanup_old_logs,
            refresh_expired_tokens,
            renew_webhook_subscriptions,
            run_system_health_checks,
            sync_all_accounts,
        )

        cadence = {
            "sync": self._interval("TASK_SYNC_INTERVAL_SECONDS", 300),
            "tokens": self._interval("TASK_TOKEN_REFRESH_SECONDS", 600),
            "webhooks": self._interval("TASK_WEBHOOK_RENEW_SECONDS", 900),
            "cleanup": self._interval("TASK_LOG_CLEANUP_SECONDS", 86400),
            "health": self._interval("TASK_HEALTH_CHECK_SECONDS", 300),
        }

        # last-run bookkeeping in Redis so multiple cron invocations don't overlap.
        from portal.utils.tasks import _client

        client = _client()
        try:
            for key, job in (
                ("sync", sync_all_accounts),
                ("tokens", refresh_expired_tokens),
                ("webhooks", renew_webhook_subscriptions),
                ("cleanup", cleanup_old_logs),
                ("health", run_system_health_checks),
            ):
                if not options["once"] and client and not client.set(
                    f"task:last:{key}", "1", nx=True, ex=int(cadence[key])
                ):
                    continue
                self.stdout.write(f"Running {key} ...")
                try:
                    job.enqueue()
                except Exception as exc:  # noqa: BLE001
                    self.stderr.write(
                        self.style.ERROR(f"  {key} failed: {exc}")
                    )
        finally:
            if client:
                try:
                    client.close()
                except Exception:  # noqa: BLE001
                    pass

        self.stdout.write(self.style.SUCCESS("Scheduled tasks complete."))