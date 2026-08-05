"""
Search service — cross-mailbox search across every connected Outlook account.

The unified inbox search is a single Postgres query built by the repository
layer (subject, sender, recipient, body, preview, attachments name). Redis is
used only for lightweight suggestion caching; correctness lives in SQL.
"""

import logging

from django.core.cache import cache

from portal.repositories import EmailRepository, MicrosoftAuthRepository

logger = logging.getLogger(__name__)

SUGGEST_CACHE_TTL = 60 * 60  # 1 hour


class SearchService:
    def __init__(self, email_repository=None, auth_repository=None):
        self.email_repository = email_repository or EmailRepository()
        self.auth_repository = auth_repository or MicrosoftAuthRepository()

    def search(self, user, q, **filters):
        """
        Return a user-scoped queryset matching ``q`` across fields, applying the
        same filters as the inbox (folder, read state, account, dates, ...).
        """
        return self.email_repository.list_messages(user, q=q, **filters)

    def search_attachments(self, user, filename, **filters):
        """Messages whose attachments match a filename fragment."""
        from django.db.models import Q

        from portal.models import Attachment

        email_ids = (
            Attachment.objects.filter(name__icontains=filename)
            .values_list("email_id", flat=True)
            .distinct()
        )
        qs = self.email_repository.list_messages(user, **filters).filter(pk__in=email_ids)
        return qs

    def suggestions(self, user, q, limit=8):
        """
        Recent subject/sender pairs matching ``q`` for the search-as-you-type
        dropdown. Results are cached in Redis for one hour.
        """
        key = f"search:suggest:{user.pk}:{(q or '').lower()}"
        cached = cache.get(key)
        if cached is not None:
            return cached

        results = list(
            self.email_repository.list_messages(user, q=q)
            .values("subject", "from_name", "from_email")[:limit]
        )
        cache.set(key, results, SUGGEST_CACHE_TTL)
        return results

    def clear_suggestions(self, user):
        """Best-effort invalidation for a user after new mail arrives."""
        try:
            cache.delete_pattern(f"search:suggest:{user.pk}:*")
        except Exception:  # noqa: BLE001 - Redis may not be reachable
            logger.debug("Could not invalidate search suggestion cache")
