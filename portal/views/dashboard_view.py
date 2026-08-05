
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from portal.base_view import PortalView
class DashboardView(LoginRequiredMixin, PortalView):
    template_name = "dashboard/index.html"
    title = "Dashboard"
    breadcrumbs = [{"label": "Dashboard"}]
    active_page = "dashboard"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        name = self.request.user.get_full_name().strip() or self.request.user.get_username()
        messages.success(self.request, f"Welcome back, {name}. All syncs are healthy.")
        stats = [
            {"label": "Connected Accounts", "value": "4 of 5", "icon": "bi-envelope-paper", "tone": "primary", "trend": "+1 this week"},
            {"label": "Total Emails", "value": "12,483", "icon": "bi-envelope-open", "tone": "info", "trend": "+2.4% this week"},
            {"label": "Unread Emails", "value": "26", "icon": "bi-envelope-exclamation", "tone": "warning", "trend": "-8 since yesterday"},
            {"label": "Emails Today", "value": "142", "icon": "bi-inboxes", "tone": "success", "trend": "+12% vs avg"},
        ]
        context.update(
            stats=stats,
        )
        return context