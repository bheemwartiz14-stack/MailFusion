"""
Notification service.

Coordinates business notifications. Views must go through this service and
must never touch the ``Notification`` model or repository directly.
"""

import logging

from portal.repositories import NotificationRepository

logger = logging.getLogger(__name__)


class NotificationService:
    """Business operations around the notification center."""

    def __init__(self, repository=None):
        self.repository = repository or NotificationRepository()

    def notify(self, *, title, detail="", icon="bi-bell", tone="primary"):
        """Create a business notification."""
        notification = self.repository.create(
            title=title, detail=detail, icon=icon, tone=tone
        )
        logger.info("Notification created: %s", title)
        return notification

    def unread_count(self):
        """Number of unread notifications (navbar badge)."""
        return self.repository.count_unread()

    def total_count(self):
        """Total number of notifications."""
        return self.repository.count_total()

    def recent(self, limit=4):
        """Latest notifications as shell-friendly dicts."""
        return [
            {
                "title": n.title,
                "detail": n.detail,
                "time": self._time_ago(n.created_at),
                "icon": n.icon or "bi-bell",
                "tone": n.tone,
            }
            for n in self.repository.list_recent(limit)
        ]

    def list(self, status=""):
        """QuerySet filtered by ``status`` (all|unread|read)."""
        if status == "unread":
            return self.repository.list_unread()
        if status == "read":
            return self.repository.list_read()
        return self.repository.list_all()

    def toggle_read(self, pk):
        """Flip read state for the notification with ``pk``; return it."""
        notification = self.repository.get(pk)
        if notification.is_read:
            return self.repository.mark_unread(notification)
        return self.repository.mark_read(notification)

    def delete(self, pk):
        """Delete the notification with ``pk``."""
        self.repository.delete(self.repository.get(pk))

    def mark_all_read(self):
        """Mark every notification as read."""
        return self.repository.mark_all_read()

    def bulk(self, pks, action):
        """Bulk ``mark_read`` or ``delete`` over ``pks``; return affected count."""
        if action == "mark_read":
            return self.repository.bulk_mark_read(pks)
        if action == "delete":
            deleted, _ = self.repository.bulk_delete(pks)
            return deleted
        return 0

    def _time_ago(self, dt):
        from django.utils.timesince import timesince

        return f"{timesince(dt)} ago" if dt else ""
