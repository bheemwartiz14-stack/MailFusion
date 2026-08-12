"""
Tests for the synchronization engine: delta sync, idempotency, token handling,
webhook renewal, pause/resume and the monitoring views.

The graph/HTTP layer is mocked; repositories and the engine run against the
test database.
"""

from dataclasses import dataclass
from unittest.mock import Mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from portal.models import (
    AccountHealth,
    Attachment,
    Email,
    EmailSyncState,
    GraphSubscription,
    OutlookAccount,
    SyncLog,
)
from portal.repositories import SyncRepository
from portal.services.sync_services import SyncService


def make_account(email="work@acme.io"):
    user = get_user_model().objects.create_user(username=email, password="pw")
    return OutlookAccount.objects.create(
        user=user,
        name=email,
        email=email,
        nickname=email.split("@")[0],
        status="active",
        oauth_status="connected",
    )


class FakeResult:
    def __init__(self, ok=True, accessed=False):
        self.ok = ok
        self.accessed = accessed


class FakeAuthService:
    """Stand-in for MicrosoftAuthService exposing only get/get_valid tokens."""

    def __init__(self, token="tok"):
        self.token = token
        self.refreshed = 0
        self.failed = 0

    def get_valid_access_token(self, account):
        return self.token if account.oauth_status != "revoked" else None

    def refresh_token(self, account):
        if account.oauth_status == "revoked":
            self.failed += 1
            return None
        self.refreshed += 1
        return "new-token"


class FakeGraphService:
    """Configurable delta responses for the Graph transport."""

    def __init__(self, pages=None, delta_link="dl-1"):
        self.pages = pages or [[]]
        self.delta_link = delta_link

    def fetch_message_delta(self, access_token, delta_link=None, resource=None):
        page = self.pages.pop(0) if self.pages else []
        return page, (self.pages[0] if self.pages else None), self.delta_link

    def download_attachment(self, access_token, message_id, attachment_id):
        return b"binary"


class SyncEngineTests(TestCase):
    def setUp(self):
        self.account = make_account()

    def _service(self, graph=None, auth=None):
        return SyncService(
            graph_service=graph or FakeGraphService(),
            auth_service=auth or FakeAuthService(),
            sync_repository=SyncRepository(),
        )

    def test_full_sync_creates_emails(self):
        page = [
            {
                "graph_message_id": "m1",
                "subject": "Hello",
                "body_html": "<p>hi</p>",
                "from_name": "Bob",
                "from_email": "bob@a.com",
                "received_at": "2026-08-01T10:00:00Z",
                "is_read": False,
                "importance": "normal",
            }
        ]
        result = self._service(graph=FakeGraphService(pages=[page])).sync_account(
            self.account, worker="test"
        )
        self.assertTrue(result.success)
        self.assertEqual(result.added, 1)
        self.assertEqual(Email.objects.filter(outlook_account=self.account).count(), 1)
        self.account.refresh_from_db()
        self.assertEqual(self.account.total_emails_synced, 1)
        self.assertTrue(SyncLog.objects.filter(account=self.account, status="completed").exists())

    def test_delta_sync_is_idempotent(self):
        msg = {"graph_message_id": "m1", "subject": "Hello", "received_at": "2026-08-01T10:00:00Z"}
        service = self._service(graph=FakeGraphService(pages=[[msg]]))
        first = service.sync_account(self.account, worker="test")
        second = service.sync_account(self.account, worker="test")
        self.assertEqual(Email.objects.filter(outlook_account=self.account).count(), 1)
        self.assertEqual(first.added, 1)
        self.assertLessEqual(second.added, 1)

    def test_delta_removal_deletes_email(self):
        Email.objects.create(
            outlook_account=self.account,
            graph_message_id="gone",
            subject="old",
            received_at=timezone.now(),
        )
        removed = {
            "graph_message_id": "gone",
            "_removed": True,
        }
        service = self._service(graph=FakeGraphService(pages=[[removed]]))
        result = service.sync_account(self.account, worker="test")
        self.assertTrue(result.success)
        self.assertEqual(result.removed, 1)
        self.assertFalse(Email.objects.filter(outlook_account=self.account).exists())

    def test_sync_skips_paused_account(self):
        self.account.is_sync_paused = True
        self.account.save()
        result = self._service().sync_account(self.account, worker="test")
        self.assertEqual(result.error, "Synchronization paused")
        self.assertEqual(SyncLog.objects.filter(account=self.account, status="failed").count(), 0)

    def test_sync_fails_without_token_and_records_log(self):
        auth = FakeAuthService(token=None)
        result = self._service(auth=auth).sync_account(self.account, worker="test")
        self.assertFalse(result.success)
        self.assertIn("No valid access token", result.error)
        self.assertTrue(
            SyncLog.objects.filter(account=self.account, status="failed").exists()
        )
        self.account.refresh_from_db()
        self.assertEqual(self.account.status, "error")


class WebhookRenewalTests(TestCase):
    def test_renew_webhooks_renews_expiring(self):
        account = make_account("renew@acme.io")
        sub = GraphSubscription.objects.create(
            account=account,
            subscription_id="sub-1",
            resource="me/mailFolders/Inbox/messages",
            notification_url="https://hooks.example.test",
            expiration_date_time=timezone.now() + timezone.timedelta(hours=6),
            status="active",
        )
        graph = FakeGraphService()
        graph.renew_subscription = Mock(return_value={"id": "sub-1"})
        service = SyncService(
            graph_service=graph,
            auth_service=FakeAuthService(),
            sync_repository=SyncRepository(),
        )
        renewed, failed = service.renew_webhooks(worker="test")
        self.assertEqual(renewed, 1)
        self.assertEqual(failed, 0)
        sub.refresh_from_db()
        self.assertGreater(sub.expiration_date_time, timezone.now() + timezone.timedelta(days=1))


class HealthTests(TestCase):
    def test_health_updated_on_success(self):
        account = make_account("health@acme.io")
        page = [{"graph_message_id": "x", "subject": "s", "received_at": "2026-08-01T10:00:00Z"}]
        self._service(account, page).sync_account(account, worker="test")
        health = AccountHealth.objects.get(account=account)
        self.assertTrue(health.oauth_ok)
        self.assertTrue(health.graph_ok)

    def _service(self, account, page):
        return SyncService(
            graph_service=FakeGraphService(pages=[page]),
            auth_service=FakeAuthService(),
            sync_repository=SyncRepository(),
        )


class AccountActionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="u1", password="pw")
        self.account = OutlookAccount.objects.create(
            user=self.user, name="Work", email="w@acme.io", oauth_status="connected"
        )
        self.client.force_login(self.user)

    def test_pause_and_resume(self):
        self.client.post(reverse("accounts_pause", args=[self.account.pk]))
        self.account.refresh_from_db()
        self.assertTrue(self.account.is_sync_paused)
        self.client.post(reverse("accounts_resume", args=[self.account.pk]))
        self.account.refresh_from_db()
        self.assertFalse(self.account.is_sync_paused)

    def test_rename(self):
        self.client.post(
            reverse("accounts_rename", args=[self.account.pk]),
            {"name": "Renamed", "nickname": "Rn"},
        )
        self.account.refresh_from_db()
        self.assertEqual(self.account.name, "Renamed")
        self.assertEqual(self.account.nickname, "Rn")

    def test_sync_views_render(self):
        for path in [
            "/system-monitor/",
            "/system-monitor/logs/",
            "/system-monitor/health/",
            "/system-monitor/queue/",
            "/system-monitor/oauth/",
        ]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)

    def test_inbox_renders_with_pagination(self):
        from datetime import timedelta

        for i in range(5):
            Email.objects.create(
                outlook_account=self.account,
                graph_message_id=f"g{i}",
                subject=f"Subject {i}",
                from_email="a@b.co",
                received_at=timezone.now() - timedelta(minutes=i),
            )
        for url in ["/inbox/", "/inbox/?page=1"]:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)

    def test_dashboard_renders(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)


class SyncLogTests(TestCase):
    def test_log_detail_renders(self):
        account = make_account("log@acme.io")
        log = SyncLog.objects.create(
            account=account, status="completed", start_time=timezone.now()
        )
        self.client.force_login(account.user)
        response = self.client.get(reverse("sync_log_detail", args=[log.pk]))
        self.assertEqual(response.status_code, 200)