"""
Audit service.

Records security/activity events through the audit repository. Reusable
across the whole application — any flow that needs an audit trail goes
through this service, never the repository directly.
"""

import logging

from django.contrib.auth import get_user_model

from portal.repositories import AuditRepository

logger = logging.getLogger(__name__)

UserModel = get_user_model()


class AuditService:
    """Coordinates security event recording."""

    def __init__(self, repository=None):
        self.repository = repository or AuditRepository()

    def record(self, *, action, request=None, user=None, target="", status="success", actor=""):
        """
        Persist one audit entry.

        ``request`` is optional; when given, the client IP is captured.
        ``actor`` falls back to the user's display name, else "System".
        """
        entry = self.repository.create(
            user=user,
            actor=actor or self._display_name(user),
            action=action,
            target=target,
            ip=self._client_ip(request) if request else "",
            status=status,
        )
        logger.info("Audit recorded: %s %s", action, target or "")
        return entry

    def record_login(self, request, user):
        """Successful sign-in."""
        return self.record(
            request=request, user=user, action="auth.login", target=user.get_username()
        )

    def record_failed_login(self, request, username):
        """Rejected sign-in attempt."""
        return self.record(
            request=request,
            action="auth.login_failed",
            target=username or "unknown",
            status="error",
        )

    def record_logout(self, request, user):
        """Signed out."""
        return self.record(request=request, user=user, action="auth.logout")

    def record_password_change(self, request, user):
        """Password changed successfully."""
        return self.record(request=request, user=user, action="auth.password_change")

    def record_password_reset_requested(self, request, email):
        """Password reset link requested."""
        return self.record(
            request=request, action="auth.password_reset_requested", target=email
        )

    def record_password_reset(self, request, user):
        """Password reset completed."""
        return self.record(request=request, user=user, action="auth.password_reset")

    def record_profile_update(self, request, user):
        """Profile details updated."""
        return self.record(request=request, user=user, action="profile.update")

    def search(self, *, status="", query=""):
        """Filtered audit queryset for the logs page."""
        return self.repository.search(status=status, query=query)

    def all(self):
        """Every audit entry (used by the CSV export)."""
        return self.repository.list_all()

    def _display_name(self, user):
        if user is None or not user.is_authenticated:
            return "System"
        return user.get_full_name().strip() or user.get_username()

    def _client_ip(self, request):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "")
