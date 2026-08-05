

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.shortcuts import redirect, render

from portal.utils.querystring import _querystring
from ..base_view import (
    PortalView,
)
from ..services import NotificationService


class NotificationsView(LoginRequiredMixin, PortalView):
    template_name = "notifications/list.html"
    title = "Notifications"
    breadcrumbs = [{"label": "Notifications"}]
    active_page = "notifications"
    page_size = 10
    service = NotificationService()
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        status = self.request.GET.get("status", "")
        qs = self.service.list(status)
        page_obj = Paginator(qs, self.page_size).get_page(self.request.GET.get("page"))
        unread = self.service.unread_count()
        context.update(
            page_obj=page_obj,
            notifications=page_obj.object_list,
            unread_count=unread,
            read_count=self.service.total_count() - unread,
            current_status=status,
            extra_querystring=_querystring(self.request),
        )
        return context


class NotificationActionView(LoginRequiredMixin, PortalView):
    """Mark read/unread, delete, or mark-all-read. POST only."""
    http_method_names = ["post"]

    service = NotificationService()

    def post(self, request, *args, **kwargs):
        action = kwargs.get("action")
        if action == "mark_all_read":
            self.service.mark_all_read()
            messages.success(request, "All notifications marked as read.")
        elif action == "toggle":
            note = self.service.toggle_read(kwargs["notification_id"])
            messages.success(request, f"Notification {'read' if note.is_read else 'unread'}.")
        elif action == "delete":
            self.service.delete(kwargs["notification_id"])
            messages.success(request, "Notification deleted.")
        return redirect("notifications")

class NotificationBulkActionView(LoginRequiredMixin, PortalView):
    """Bulk actions over the selected checkboxes: mark read / delete. POST only."""

    http_method_names = ["post"]

    service = NotificationService()

    def post(self, request, *args, **kwargs):
        ids = [pk for pk in request.POST.getlist("notification_ids") if pk]
        bulk = request.POST.get("bulk_action")
        if ids:
            if bulk == "mark_read":
                count = self.service.bulk(ids, "mark_read")
                messages.success(request, f"{count} notification(s) marked as read.")
            elif bulk == "delete":
                count = self.service.bulk(ids, "delete")
                messages.success(request, f"{count} notification(s) deleted.")
        else:
            messages.warning(request, "Select at least one notification.")
        return redirect("notifications")