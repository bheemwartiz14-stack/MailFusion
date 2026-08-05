"""
Notification repository.

Data access for the ``Notification`` model only. This layer contains pure
database queries and persistence — it must never contain business logic.

Dependency rule: repositories may access models, nothing else.
"""

from django.shortcuts import get_object_or_404

from portal.models import Notification


class NotificationRepository:
    """Persistence layer for the notification center."""

    def create(self, *, title, detail="", icon="bi-bell", tone="primary", is_read=False):
        """Create and return a new notification."""
        return Notification.objects.create(
            title=title,
            detail=detail,
            icon=icon,
            tone=tone,
            is_read=is_read,
        )

    def get(self, pk):
        """Return a single notification or raise Http404."""
        return get_object_or_404(Notification, pk=pk)

    def list_all(self):
        """Return all notifications, newest first (model default ordering)."""
        return Notification.objects.all()

    def list_read(self):
        """Return only read notifications."""
        return Notification.objects.filter(is_read=True)

    def list_unread(self):
        """Return only unread notifications."""
        return Notification.objects.filter(is_read=False)

    def list_recent(self, limit=4):
        """Return the ``limit`` most recent notifications."""
        return Notification.objects.all()[:limit]

    def count_total(self):
        """Total number of notifications."""
        return Notification.objects.count()

    def count_unread(self):
        """Number of unread notifications."""
        return Notification.objects.filter(is_read=False).count()

    def mark_read(self, notification):
        """Mark a single notification as read and persist it."""
        notification.is_read = True
        notification.save(update_fields=["is_read"])
        return notification

    def mark_unread(self, notification):
        """Mark a single notification as unread and persist it."""
        notification.is_read = False
        notification.save(update_fields=["is_read"])
        return notification

    def mark_all_read(self):
        """Mark every unread notification as read; return updated row count."""
        return Notification.objects.filter(is_read=False).update(is_read=True)

    def bulk_mark_read(self, pks):
        """Mark the given primary keys as read; return updated row count."""
        return Notification.objects.filter(pk__in=pks).update(is_read=True)

    def delete(self, notification):
        """Delete a single notification."""
        notification.delete()

    def bulk_delete(self, pks):
        """Delete all notifications matching ``pks``."""
        return Notification.objects.filter(pk__in=pks).delete()
