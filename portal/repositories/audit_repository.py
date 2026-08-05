"""
Audit repository.

Data access for the ``AuditLog`` model only. This layer contains pure
database queries and persistence — it must never contain business logic.

Dependency rule: repositories may access models, nothing else.
"""

from django.db.models import Q

from portal.models import AuditLog


class AuditRepository:
    """Persistence layer for the audit trail."""

    def create(self, *, user=None, actor="", action="", target="", ip="", status="success"):
        """Create and return an audit log entry."""
        if user is not None and not user.is_authenticated:
            user = None
        return AuditLog.objects.create(
            user=user,
            actor=actor,
            action=action,
            target=target,
            ip=ip,
            status=status,
        )

    def get(self, pk):
        """Return a single audit entry or raise DoesNotExist."""
        return AuditLog.objects.select_related("user").get(pk=pk)

    def list_all(self):
        """Return all audit entries, newest first, with the actor resolved."""
        return AuditLog.objects.select_related("user").all()

    def search(self, *, status="", query=""):
        """Filter by status (success|error) and/or free-text ``query``."""
        qs = self.list_all()
        if status in ("success", "error"):
            qs = qs.filter(status=status)
        query = (query or "").strip()
        if query:
            qs = qs.filter(
                Q(actor__icontains=query)
                | Q(action__icontains=query)
                | Q(target__icontains=query)
            )
        return qs

    def count(self):
        """Total number of audit entries."""
        return AuditLog.objects.count()
