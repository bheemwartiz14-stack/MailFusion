from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.http import HttpResponse
from portal.base_view import (
    PortalView,
)
from portal.services import AuditService
from portal.utils.querystring import _page_size, _page_size_options, _querystring
class AuditLogsView(LoginRequiredMixin, PortalView):
    template_name = "logs/list.html"
    title = "Audit Logs"
    breadcrumbs = [{"label": "Audit Logs"}]
    active_page = "audit_logs"
    page_size = 15

    service = AuditService()
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        status = self.request.GET.get("status", "")
        q = self.request.GET.get("q", "").strip()
        qs = self.service.search(status=status, query=q)
        page_obj = Paginator(qs, _page_size(self.request, self.page_size)).get_page(self.request.GET.get("page"))
        context.update(
            page_obj=page_obj,
            logs=page_obj.object_list,
            current_status=status,
            query=q,
            page_size_options=_page_size_options(),
            extra_querystring=_querystring(self.request),
        )
        return context


class AuditLogExportView(LoginRequiredMixin, PortalView):
    http_method_names = ["get"]

    def get(self, request, *args, **kwargs):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="audit-logs.csv"'
        import csv
        writer = csv.writer(response)
        writer.writerow(["timestamp", "actor", "action", "target", "ip", "status"])
        for log in AuditService().all():
            writer.writerow([log.timestamp, log.actor, log.action, log.target, log.ip, log.status])
        return response