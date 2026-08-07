"""
Outlook Accounts views.

Views for managing connected Microsoft mailboxes via Microsoft Graph OAuth.
All business logic is delegated to MicrosoftAuthService.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View

from ..base_view import PortalView
from ..services import MicrosoftAuthService


class AccountsListView(LoginRequiredMixin, PortalView):
    """List all connected Outlook accounts for the current user."""

    template_name = "accounts/list.html"
    title = "Outlook Accounts"
    breadcrumbs = [{"label": "Outlook Accounts"}]
    active_page = "accounts"

    def get(self, request):
        service = MicrosoftAuthService()
        accounts = service.repository.list_accounts(request.user)

        context = self.get_context_data()
        context["accounts"] = accounts
        return render(request, self.template_name, context)


class AccountsAddView(LoginRequiredMixin, PortalView):
    """Step 1: Enter account details before OAuth."""

    template_name = "accounts/connect.html"
    title = "Connect Outlook Account"
    breadcrumbs = [
        {"label": "Outlook Accounts", "url": "/accounts/"},
        {"label": "Connect Account"},
    ]
    active_page = "accounts"

    def get(self, request):
        context = self.get_context_data()
        return render(request, self.template_name, context)

    def post(self, request):
        request.session["pending_account"] = {
            "name": request.POST.get("name", "").strip(),
            "nickname": request.POST.get("nickname", "").strip(),
            "description": request.POST.get("description", "").strip(),
            "is_default": request.POST.get("is_default") == "on",
        }
        if not request.session["pending_account"]["name"]:
            messages.error(request, "Display name is required.")
            return render(request, self.template_name, self.get_context_data())
        service = MicrosoftAuthService()
        auth_url, _ = service.build_auth_url(request)
        return redirect(auth_url)


class AccountsCallbackView(View):
    """Handle OAuth callback from Microsoft."""

    def get(self, request):
        service = MicrosoftAuthService()

        try:
            account, next_url = service.handle_callback(request)
            # Store pending account details if this was a new connection
            pending = request.session.pop("pending_account", None)
            if pending:
                service.repository.update_account(
                    account,
                    name=pending["name"],
                    nickname=pending["nickname"],
                    description=pending["description"],
                    is_default=pending["is_default"],
                )
                if pending["is_default"]:
                    service.repository.set_default_account(request.user, account.pk)

            messages.success(request, f"Successfully connected {account.email}")
            return redirect(next_url)

        except ValueError as e:
            # OAuth error - show error page
            messages.error(request, str(e))
            return render(request, "accounts/callback_error.html", {"error": str(e)})


class AccountsReconnectView(LoginRequiredMixin, View):
    """Initiate reconnection for an existing account."""

    def get(self, request, account_id):
        service = MicrosoftAuthService()
        account = service.repository.get_account_or_none(account_id)

        # Verify ownership
        if not account or account.user != request.user:
            messages.error(request, "Account not found.")
            return redirect("accounts")

        auth_url = service.reconnect_account(request, account)
        return redirect(auth_url)


class AccountsDisconnectConfirmView(LoginRequiredMixin, PortalView):
    """Show confirmation page before disconnecting an account."""

    template_name = "accounts/disconnect_confirm.html"
    title = "Disconnect Account"
    breadcrumbs = [
        {"label": "Outlook Accounts", "url": "/accounts/"},
        {"label": "Disconnect"},
    ]
    active_page = "accounts"

    def get(self, request, account_id):
        service = MicrosoftAuthService()
        account = service.repository.get_account_or_none(account_id)

        if not account or account.user != request.user:
            messages.error(request, "Account not found.")
            return redirect("accounts")

        context = self.get_context_data()
        context["account"] = account
        return render(request, self.template_name, context)


class AccountsDisconnectView(LoginRequiredMixin, View):
    """Disconnect an Outlook account (POST only)."""

    def post(self, request, account_id):
        service = MicrosoftAuthService()
        account = service.repository.get_account_or_none(account_id)

        if not account or account.user != request.user:
            messages.error(request, "Account not found.")
            return redirect("accounts")

        service.disconnect_account(request, account)
        messages.success(request, f"Disconnected {account.email}")
        return redirect("accounts")

class AccountsSyncView(LoginRequiredMixin, View):
    """Trigger a manual sync for an Outlook account."""

    def post(self, request, account_id):
        service = MicrosoftAuthService()
        account = service.repository.get_account_or_none(account_id)
        if not account or account.user != request.user:
            return HttpResponse("Account not found.", status=404)
        ok = service.sync_account(account)
        if not ok:
            return HttpResponse("Sync failed. Check the account connection.", status=500)
        return HttpResponse(f"Sync initiated for {account.email}")

    def get(self, request, account_id):
        service = MicrosoftAuthService()
        account = service.repository.get_account_or_none(account_id)
        if not account or account.user != request.user:
            messages.error(request, "Account not found.")
            return redirect("accounts")
        service.sync_account(account)
        messages.success(request, f"Sync initiated for {account.email}")
        return redirect("accounts")


class AccountsSyncAllView(LoginRequiredMixin, View):
    """Trigger a manual sync for every connected account."""

    def post(self, request):
        service = MicrosoftAuthService()
        accounts = service.repository.list_active_accounts_with_tokens(request.user)
        synced = sum(1 for account in accounts if service.sync_account(account))
        if synced:
            return HttpResponse(
                f"Sync initiated for {synced} account{'s' if synced != 1 else ''}."
            )
        return HttpResponse("No accounts could be synced.", status=500)

    def get(self, request):
        service = MicrosoftAuthService()
        accounts = service.repository.list_active_accounts_with_tokens(request.user)
        synced = sum(1 for account in accounts if service.sync_account(account))
        if synced:
            messages.success(
                request,
                f"Sync initiated for {synced} account{'s' if synced != 1 else ''}.",
            )
        else:
            messages.error(request, "No accounts could be synced.")
        return redirect("accounts")


class AccountsPauseView(LoginRequiredMixin, View):
    """Pause background synchronization for an account (POST only)."""

    def post(self, request, account_id):
        service = MicrosoftAuthService()
        account = service.repository.get_account_or_none(account_id)
        if not account or account.user != request.user:
            messages.error(request, "Account not found.")
            return redirect("accounts")
        service.repository.update_account(account, is_sync_paused=True, sync_error="Paused by user")
        messages.success(request, f"Synchronization paused for {account.email}")
        return redirect("accounts")


class AccountsResumeView(LoginRequiredMixin, View):
    """Resume background synchronization for an account (POST only)."""

    def post(self, request, account_id):
        service = MicrosoftAuthService()
        account = service.repository.get_account_or_none(account_id)
        if not account or account.user != request.user:
            messages.error(request, "Account not found.")
            return redirect("accounts")
        service.repository.update_account(account, is_sync_paused=False, sync_error="")
        messages.success(request, f"Synchronization resumed for {account.email}")
        return redirect("accounts")


class AccountsRenameView(LoginRequiredMixin, View):
    """Rename an account's display name and nickname (POST only)."""

    def post(self, request, account_id):
        service = MicrosoftAuthService()
        account = service.repository.get_account_or_none(account_id)
        if not account or account.user != request.user:
            messages.error(request, "Account not found.")
            return redirect("accounts")
        name = request.POST.get("name", "").strip()
        if not name:
            messages.error(request, "Display name is required.")
            return redirect("accounts")
        service.repository.update_account(
            account,
            name=name,
            nickname=request.POST.get("nickname", "").strip()[:40],
        )
        messages.success(request, f"Account renamed to {name}")
        return redirect("accounts")
