"""
Auth service.

Business-specific operations around Django's built-in authentication.

Django's ``LoginView`` / ``LogoutView`` / ``Password*View`` continue to own
authentication, session and password logic. This service only adds the
business side-effects (audit trail + notifications) and must not re-implement
any of Django's authentication.
"""

import logging
from contextlib import contextmanager

from django.db import transaction

from portal.services.audit_service import AuditService
from portal.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


class AuthService:
    """Business side-effects for authentication events."""

    def __init__(self, audit_service=None, notification_service=None):
        self.audit = audit_service or AuditService()
        self.notifications = notification_service or NotificationService()

    @contextmanager
    def _atomic(self):
        """Run the event's writes in a single transaction."""
        try:
            with transaction.atomic():
                yield
        except Exception:
            logger.exception("Auth event failed and was rolled back")
            raise

    def record_login(self, request, user):
        """Successful login: audit + "new sign-in" notification."""
        with self._atomic():
            self.audit.record_login(request, user)
            self.notifications.notify(
                title="New sign-in",
                detail=f"Signed in to {user.get_username()}",
                icon="bi-shield-check",
                tone="primary",
            )

    def record_failed_login(self, request, username):
        """Rejected login attempt: audit only (no notification spam)."""
        with self._atomic():
            self.audit.record_failed_login(request, username)

    def record_logout(self, request, user):
        """Signed out: audit only."""
        with self._atomic():
            self.audit.record_logout(request, user)

    def record_password_change(self, request, user):
        """Password changed: audit + notification."""
        with self._atomic():
            self.audit.record_password_change(request, user)
            self.notifications.notify(
                title="Password changed",
                detail="Your account password was updated.",
                icon="bi-key",
                tone="success",
            )

    def record_password_reset_requested(self, request, email):
        """Reset link requested: audit only (recipient may not have an account)."""
        with self._atomic():
            self.audit.record_password_reset_requested(request, email)

    def record_password_reset(self, request, user):
        """Reset completed: audit + notification."""
        with self._atomic():
            self.audit.record_password_reset(request, user)
            self.notifications.notify(
                title="Password reset",
                detail="Your password was reset successfully.",
                icon="bi-shield-lock",
                tone="success",
            )

    def record_profile_update(self, request, user):
        """Profile edited: audit + notification."""
        with self._atomic():
            self.audit.record_profile_update(request, user)
            self.notifications.notify(
                title="Profile updated",
                detail="Your account details were updated.",
                icon="bi-person-check",
                tone="primary",
            )
