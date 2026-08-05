from types import SimpleNamespace
from unittest.mock import Mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .models import Notification
from .services.microsoft_auth_service import MicrosoftAuthService
from .views.accounts_views import AccountsCallbackView


class NotificationUrlTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="tester",
            email="tester@example.com",
            password="secret123",
        )
        self.client.force_login(self.user)
        self.notification = Notification.objects.create(title="Test notification")

    def test_toggle_url_resolves_for_uuid_primary_key(self):
        url = reverse("notification_toggle", args=[self.notification.pk])
        self.assertEqual(url, f"/notifications/{self.notification.pk}/toggle/")


class AccountsViewImportTests(TestCase):
    def test_accounts_callback_view_imports(self):
        self.assertTrue(AccountsCallbackView.__name__ == "AccountsCallbackView")


class MicrosoftAuthServiceScopeTests(SimpleTestCase):
    def test_build_auth_url_uses_graph_scopes_without_reserved_values(self):
        service = MicrosoftAuthService.__new__(MicrosoftAuthService)
        service._msal_app = Mock()
        service._msal_app.get_authorization_request_url.return_value = "https://example.test"

        request = SimpleNamespace(
            GET={},
            session={},
            build_absolute_uri=lambda path: f"http://testserver{path}",
        )
        service.build_auth_url(request)

        scopes = service._msal_app.get_authorization_request_url.call_args.kwargs["scopes"]
        self.assertIn("https://graph.microsoft.com/User.Read", scopes)
        self.assertNotIn("offline_access", scopes)
