"""
Microsoft Auth service.

Business operations around Microsoft Graph OAuth 2.0 authorization code flow.
Uses MSAL (Microsoft Authentication Library) for token management.

Views must go through this service and must never touch the models or
repositories directly.
"""

import logging
import secrets
from datetime import timedelta
from urllib.parse import urlencode

import msal
import requests
from django.conf import settings
from django.utils import timezone

from portal.repositories import MicrosoftAuthRepository
from portal.services.audit_service import AuditService
from portal.services.graph_service import GraphService
from portal.services.notification_service import NotificationService
from portal.utils.encryption import decrypt_text, encrypt_text

logger = logging.getLogger(__name__)


class MicrosoftAuthService:
    """Business operations for Microsoft Outlook account connections."""

    # Microsoft Graph scopes for email access.
    # MSAL rejects reserved values like offline_access in the scope list for
    # interactive auth requests, so we rely on the standard Graph scopes only.
    SCOPES = [
        "https://graph.microsoft.com/Mail.Read",
        "https://graph.microsoft.com/Mail.ReadWrite",
        "https://graph.microsoft.com/Mail.Send",
        "https://graph.microsoft.com/User.Read",
    ]
    def __init__(
        self,
        repository=None,
        audit_service=None,
        notification_service=None,
        graph_service=None,
    ):
        self.repository = repository or MicrosoftAuthRepository()
        self.audit = audit_service or AuditService()
        self.graph = graph_service or GraphService()
        self.notifications = notification_service or NotificationService()
        # MSAL confidential client for web app
        self._msal_app = msal.ConfidentialClientApplication(
            client_id=settings.MICROSOFT_CLIENT_ID,
            client_credential=settings.MICROSOFT_CLIENT_SECRET,
            authority=f"https://login.microsoftonline.com/{settings.MICROSOFT_TENANT_ID}",
        )

    # -------------------- OAuth Flow --------------------

    def build_auth_url(self, request, state=None):
        """
        Generate the Microsoft OAuth authorization URL.

        Returns a tuple of (auth_url, state) where state is a CSRF token.
        """
        if state is None:
            state = secrets.token_urlsafe(32)

        # Store state in session for validation on callback
        request.session["microsoft_oauth_state"] = state
        request.session["microsoft_oauth_next"] = request.GET.get("next", "/accounts/")

        auth_url = self._msal_app.get_authorization_request_url(
            scopes=self.SCOPES,
            state=state,
            redirect_uri=settings.MICROSOFT_REDIRECT_URI,
            prompt="select_account",
        )
        logger.info("Generated Microsoft OAuth auth URL")
        return auth_url, state

    def handle_callback(self, request):
        """
        Handle the OAuth callback from Microsoft.

        Exchanges authorization code for tokens, creates/updates account,
        and records audit log.
        """
        # Validate state parameter (CSRF protection)
        state = request.GET.get("state")
        session_state = request.session.pop("microsoft_oauth_state", None)
        next_url = request.session.pop("microsoft_oauth_next", "/accounts/")

        if not state or state != session_state:
            self.audit.record(
                request=request,
                action="oauth.callback_failed",
                target="state_mismatch",
                status="error",
            )
            logger.error("OAuth callback state mismatch")
            raise ValueError("Invalid OAuth state parameter")

        # Check for error response from Microsoft
        error = request.GET.get("error")
        error_description = request.GET.get("error_description")
        if error:
            self.audit.record(
                request=request,
                action="oauth.callback_failed",
                target=error,
                status="error",
            )
            logger.error("OAuth callback error: %s - %s", error, error_description)
            raise ValueError(f"OAuth error: {error_description or error}")

        # Exchange authorization code for tokens
        code = request.GET.get("code")
        if not code:
            self.audit.record(
                request=request,
                action="oauth.callback_failed",
                target="missing_code",
                status="error",
            )
            raise ValueError("Missing authorization code")

        token_result = self._exchange_code_for_tokens(request, code)        
        if not token_result:
            self.audit.record(
                request=request,
                action="oauth.token_exchange_failed",
                target="token_exchange",
                status="error",
            )
            raise ValueError("Failed to exchange authorization code for tokens")
        # Get user profile from Microsoft Graph
        profile = self.graph.get_user_profile(token_result["access_token"])
        if not profile:
            self.audit.record(
                request=request,
                action="oauth.profile_fetch_failed",
                target="graph_profile",
                status="error",
            )
            raise ValueError("Failed to fetch user profile from Microsoft Graph")

        # Create or update the account
        account = self._create_or_update_account(request.user, profile, token_result)

        # Record successful audit log
        self.audit.record(
            request=request,
            user=request.user,
            action="oauth.callback_success",
            target=account.email,
            status="success",
        )

        # Send notification
        self.notifications.notify(
            title="Outlook account connected",
            detail=f"Successfully connected {account.email}",
            icon="bi-envelope-check",
            tone="success",
        )

        logger.info("OAuth callback successful for %s", account.email)
        return account, next_url

    def _exchange_code_for_tokens(self, request, code):
        """Exchange authorization code for access/refresh tokens via MSAL."""
        result = self._msal_app.acquire_token_by_authorization_code(
            code=code,
            scopes=self.SCOPES,
            redirect_uri=self._get_redirect_uri(request),
        )

        if "error" in result:
            logger.error("Token exchange failed: %s - %s", result.get("error"), result.get("error_description"))
            return None

        return {
            "access_token": result["access_token"],
            "refresh_token": result.get("refresh_token", ""),
            "id_token": result.get("id_token", ""),
            "expires_in": result.get("expires_in", 3600),
            "token_type": result.get("token_type", "Bearer"),
            "scope": " ".join(result.get("scope", [])),
        }
    def _create_or_update_account(self, user, profile, token_result):
        """Create or update OutlookAccount with tokens."""
        email = profile.get("mail") or profile.get("userPrincipalName")
        name = profile.get("displayName") or email
        nickname = (email.split("@")[0])[:40] if email else ""
        # Encrypt tokens before storage
        access_encrypted = encrypt_text(token_result["access_token"])
        refresh_encrypted = encrypt_text(token_result.get("refresh_token", ""))
        id_encrypted = encrypt_text(token_result.get("id_token", ""))
        expires_at = timezone.now() + timedelta(seconds=token_result["expires_in"])
        # Check if account already exists
        existing = self.repository.get_account_by_email(user, email)
        if existing:
            # Update existing account
            existing.name = name
            existing.status = "active"
            existing.oauth_status = "connected"
            existing.sync_error = ""
            existing.save(update_fields=["name", "status", "oauth_status", "sync_error", "updated_at"])
            # Update or create token
            token = self.repository.get_token(existing)
            if token:
                self.repository.update_token(
                    token,
                    access_token_encrypted=access_encrypted,
                    refresh_token_encrypted=refresh_encrypted,
                    id_token_encrypted=id_encrypted,
                    token_type=token_result["token_type"],
                    scope=token_result["scope"],
                    expires_at=expires_at,
                )
            else:
                self.repository.create_token(
                    account=existing,
                    access_token_encrypted=access_encrypted,
                    refresh_token_encrypted=refresh_encrypted,
                    id_token_encrypted=id_encrypted,
                    token_type=token_result["token_type"],
                    scope=token_result["scope"],
                    expires_at=expires_at,
                )
            account = existing
        else:
            # Create new account
            account = self.repository.create_account(
                user=user,
                name=name,
                email=email,
                nickname=nickname,
                status="active",
                oauth_status="connected",
            )
            self.repository.create_token(
                account=account,
                access_token_encrypted=access_encrypted,
                refresh_token_encrypted=refresh_encrypted,
                id_token_encrypted=id_encrypted,
                token_type=token_result["token_type"],
                scope=token_result["scope"],
                expires_at=expires_at,
            )

        return account

    def _get_redirect_uri(self, request):
        """Build the OAuth redirect URI."""
        return request.build_absolute_uri("/accounts/callback/")

    # -------------------- Token Management --------------------

    def get_valid_access_token(self, account):
        """
        Get a valid access token for an account, refreshing if necessary.

        Returns the decrypted access token string, or None if unavailable.
        """
        token = self.repository.get_token(account)
        if not token:
            logger.warning("No token found for account %s", account.email)
            return None
        # Check if token is expired
        if token.is_expired():
            logger.info("Access token expired for %s, attempting refresh", account.email)
            return self.refresh_token(account)
        return decrypt_text(token.access_token_encrypted)

    def refresh_token(self, account):
        """
        Refresh the access token using the refresh token.

        Returns the new decrypted access token, or None if refresh fails.
        """
        token = self.repository.get_token(account)
        if not token or not token.refresh_token_encrypted:
            logger.error("No refresh token available for %s", account.email)
            self._mark_account_oauth_error(account, "No refresh token available")
            return None

        refresh_token = decrypt_text(token.refresh_token_encrypted)

        result = self._msal_app.acquire_token_by_refresh_token(
            refresh_token=refresh_token,
            scopes=self.SCOPES,
        )

        if "error" in result:
            logger.error("Token refresh failed for %s: %s", account.email, result.get("error_description"))
            self._mark_account_oauth_error(account, f"Token refresh failed: {result.get('error_description')}")
            self.audit.record(
                user=account.user,
                action="oauth.token_refresh_failed",
                target=account.email,
                status="error",
            )
            self.notifications.notify(
                title="OAuth token refresh failed",
                detail=f"Failed to refresh token for {account.email}. Reconnection required.",
                icon="bi-shield-exclamation",
                tone="danger",
            )
            return None

        # Update tokens
        new_access = result["access_token"]
        new_refresh = result.get("refresh_token", refresh_token)  # May rotate
        new_id = result.get("id_token", "")
        expires_in = result.get("expires_in", 3600)
        expires_at = timezone.now() + timedelta(seconds=expires_in)

        self.repository.update_token(
            token,
            access_token_encrypted=encrypt_text(new_access),
            refresh_token_encrypted=encrypt_text(new_refresh),
            id_token_encrypted=encrypt_text(new_id) if new_id else token.id_token_encrypted,
            expires_at=expires_at,
        )

        # Update account status
        self.repository.update_account(account, oauth_status="connected", sync_error="")

        # Audit and notification
        self.audit.record(
            user=account.user,
            action="oauth.token_refreshed",
            target=account.email,
            status="success",
        )
        self.notifications.notify(
            title="OAuth token refreshed",
            detail=f"Token for {account.email} refreshed successfully",
            icon="bi-arrow-clockwise",
            tone="success",
        )

        logger.info("Token refreshed successfully for %s", account.email)
        return new_access

    def _mark_account_oauth_error(self, account, error_msg):
        """Mark account as having OAuth error."""
        self.repository.update_account(
            account,
            oauth_status="error",
            status="error",
            sync_error=error_msg,
        )

    # -------------------- Account Management --------------------

    def disconnect_account(self, request, account):
        """Disconnect an Outlook account (delete tokens, mark as disconnected)."""
        email = account.email

        # Delete tokens
        token = self.repository.get_token(account)
        if token:
            self.repository.delete_token(token)

        # Update account status
        self.repository.update_account(
            account,
            oauth_status="revoked",
            status="paused",
            sync_error="Disconnected by user",
        )

        # Audit and notification
        self.audit.record(
            request=request,
            user=request.user,
            action="account.disconnect",
            target=email,
            status="success",
        )
        self.notifications.notify(
            title="Outlook account disconnected",
            detail=f"{email} has been disconnected",
            icon="bi-envelope-x",
            tone="warning",
        )

        logger.info("Account disconnected: %s", email)

    def reconnect_account(self, request, account):
        """
        Initiate reconnection for an existing account.

        Returns the auth URL to redirect the user to.
        """
        # Update account status to pending
        self.repository.update_account(account, oauth_status="pending", status="active")

        # Generate new auth URL
        auth_url, state = self.build_auth_url(request)

        # Audit
        self.audit.record(
            request=request,
            user=request.user,
            action="oauth.reconnect_started",
            target=account.email,
            status="success",
        )

        logger.info("Reconnection initiated for %s", account.email)
        return auth_url

    def get_account_profile(self, account):
        """Fetch the latest profile info from Microsoft Graph."""
        access_token = self.get_valid_access_token(account)
        if not access_token:
            return None
        return self.graph.get_user_profile(access_token)

    def sync_account(self, account):
        """
        Trigger a sync for an account.

        Dispatches the work to the Celery worker (background). Returns True if
        a sync was queued, False otherwise.
        """
        from portal.tasks import sync_account

        access_token = self.get_valid_access_token(account)
        if not access_token:
            self._mark_account_oauth_error(account, "No valid access token")
            return False
        sync_account.delay(account.pk, requested_by="web")
        self.repository.update_account(account, last_sync_at=timezone.now())
        return True

    # -------------------- Utility --------------------

    def validate_token(self, access_token):
        """Validate an access token by calling Graph /me endpoint."""
        if not access_token:
            return False
        profile = self.graph.get_user_profile(access_token)
        return profile is not None

    