"""
Microsoft Auth repository.

Data access for the ``OutlookAccount`` and ``OAuthToken`` models only.
This layer contains pure database queries and persistence — it must never
contain business logic.

Dependency rule: repositories may access models, nothing else.
"""

from django.db.models import Q
from django.shortcuts import get_object_or_404

from portal.models import OAuthToken, OutlookAccount


class MicrosoftAuthRepository:
    """Persistence layer for Microsoft Outlook accounts and OAuth tokens."""

    # -------------------- OutlookAccount --------------------

    def create_account(
        self,
        *,
        user,
        name,
        email,
        nickname="",
        description="",
        status="active",
        oauth_status="pending",
        is_default=True,
    ):
        """Create and return a new OutlookAccount."""
        return OutlookAccount.objects.create(
            user=user,
            name=name,
            email=email.lower(),
            nickname=nickname,
            description=description,
            status=status,
            oauth_status=oauth_status,
            is_default=is_default,
        )

    def get_account(self, pk):
        """Return a single OutlookAccount or raise DoesNotExist."""
        return OutlookAccount.objects.select_related("user", "oauth_token").get(pk=pk)

    def get_account_or_none(self, pk):
        """Return a single OutlookAccount or None if not found."""
        return (
            OutlookAccount.objects.select_related("user", "oauth_token")
            .filter(pk=pk)
            .first()
        )

    def get_account_by_email(self, user, email):
        """Return OutlookAccount for user and email, or None."""
        return OutlookAccount.objects.filter(user=user, email=email.lower()).first()

    def list_accounts(self, user):
        """Return all accounts for a user, newest first."""
        return OutlookAccount.objects.filter(user=user).select_related("oauth_token")

    def update_account(self, account, **fields):
        """Update and return an OutlookAccount with the given fields."""
        for field, value in fields.items():
            setattr(account, field, value)
        account.save(update_fields=list(fields.keys()) + ["updated_at"])
        return account

    def delete_account(self, account):
        """Delete an OutlookAccount (cascades to OAuthToken)."""
        account.delete()

    def set_default_account(self, user, account_pk):
        """Set one account as default, unset others for this user."""
        OutlookAccount.objects.filter(user=user).update(is_default=False)
        account = self.get_account(account_pk)
        account.is_default = True
        account.save(update_fields=["is_default", "updated_at"])
        return account

    def get_default_account(self, user):
        """Return the default account for a user, or the first one."""
        return (
            OutlookAccount.objects.filter(user=user, is_default=True).first()
            or OutlookAccount.objects.filter(user=user).first()
        )

    def search_accounts(self, user, query=""):
        """Filter accounts by free-text query on name, email, nickname."""
        qs = self.list_accounts(user)
        query = (query or "").strip()
        if query:
            qs = qs.filter(
                Q(name__icontains=query)
                | Q(email__icontains=query)
                | Q(nickname__icontains=query)
            )
        return qs

    # -------------------- OAuthToken --------------------

    def create_token(
        self,
        *,
        account,
        access_token_encrypted,
        refresh_token_encrypted="",
        id_token_encrypted="",
        token_type="Bearer",
        scope="",
        expires_at,
    ):
        """Create and return a new OAuthToken."""
        return OAuthToken.objects.create(
            account=account,
            access_token_encrypted=access_token_encrypted,
            refresh_token_encrypted=refresh_token_encrypted,
            id_token_encrypted=id_token_encrypted,
            token_type=token_type,
            scope=scope,
            expires_at=expires_at,
        )

    def get_token(self, account):
        """Return the OAuthToken for an account, or None."""
        return OAuthToken.objects.filter(account=account).first()

    def get_token_by_pk(self, pk):
        """Return a single OAuthToken or raise DoesNotExist."""
        return OAuthToken.objects.select_related("account", "account__user").get(pk=pk)

    def update_token(self, token, **fields):
        """Update and return an OAuthToken with the given fields."""
        for field, value in fields.items():
            setattr(token, field, value)
        token.save(update_fields=list(fields.keys()) + ["updated_at"])
        return token

    def delete_token(self, token):
        """Delete an OAuthToken."""
        token.delete()

    # -------------------- Combined queries --------------------

    def get_account_with_token(self, user, email):
        """Return account with its token for a user and email."""
        return (
            OutlookAccount.objects.filter(user=user, email=email.lower())
            .select_related("oauth_token")
            .first()
        )

    def list_active_accounts_with_tokens(self, user):
        """Return active accounts that have valid tokens."""
        return (
            OutlookAccount.objects.filter(
                user=user,
                status="active",
                oauth_status="connected",
            )
            .select_related("oauth_token")
            .all()
        )