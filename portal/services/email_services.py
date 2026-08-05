"""
Email service — unified inbox reads, actions and mailbox management.

Business operations that sit between the views and the repositories/Graph.
Everything here is user-scoped: every queryset is filtered by ``outlook_account__user``
so a user can never see or act on another user's mail.

Views must go through this service (or :mod:`portal.services.mail_composer_service`
for compose/reply/forward) and never touch models or repositories directly.
"""

import logging

from django.db import transaction
from django.utils import timezone

from portal.repositories import EmailRepository, MicrosoftAuthRepository, TaxonomyRepository
from portal.services.audit_service import AuditService
from portal.services.graph_service import GraphApiError, GraphService
from portal.services.microsoft_auth_service import MicrosoftAuthService
from portal.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

# Microsoft Graph well-known folder ids accepted by the /move endpoint.
WELL_KNOWN_FOLDERS = {
    "inbox": "inbox",
    "drafts": "drafts",
    "sentitems": "sentitems",
    "deleteditems": "deleteditems",
    "archive": "archive",
    "junkemail": "junkemail",
}


class MailActionError(Exception):
    """Raised when a Graph-backed action cannot complete."""


class EmailService:
    def __init__(
        self,
        email_repository=None,
        auth_repository=None,
        taxonomy_repository=None,
        auth_service=None,
        graph_service=None,
        audit_service=None,
        notification_service=None,
    ):
        self.email_repository = email_repository or EmailRepository()
        self.auth_repository = auth_repository or MicrosoftAuthRepository()
        self.taxonomy_repository = taxonomy_repository or TaxonomyRepository()
        self.auth_service = auth_service or MicrosoftAuthService()
        self.graph = graph_service or GraphService()
        self.audit = audit_service or AuditService()
        self.notifications = notification_service or NotificationService()

    # -------------------- read --------------------

    def list_messages(self, user, **filters):
        """Filtered, user-scoped queryset for the unified inbox / list view."""
        return self.email_repository.list_messages(user, **filters)

    def get_message(self, user, pk):
        return self.email_repository.get_for_user(user, pk)

    def get_thread(self, user, conversation_id):
        """Full ordered thread; empty list when the conversation is unknown."""
        if not conversation_id:
            return []
        return self.email_repository.thread_messages(user, conversation_id)

    def thread_count(self, user, conversation_id):
        return self.email_repository.thread_count(user, conversation_id) if conversation_id else 0

    def folder_counts(self, user):
        return self.email_repository.folder_counts(user)

    def unread_count(self, user):
        return self.email_repository.unread_count(user)

    def list_categories(self, user):
        return self.taxonomy_repository.list_categories(user)

    def list_tags(self, user):
        return self.taxonomy_repository.list_tags(user)

    def list_accounts(self, user):
        return self.auth_repository.list_active_accounts_with_tokens(user)

    def get_account_for_user(self, user, account_id):
        return self.auth_repository.get_account_or_none(account_id) if account_id else None

    # -------------------- actions --------------------

    def set_read(self, user, email, is_read, *, sync_graph=True):
        """Mark an email read/unread locally and on Microsoft Graph."""
        email.is_read = bool(is_read)
        email.save(update_fields=["is_read", "updated_at"])
        if sync_graph:
            self._graph_call(
                email, lambda token: self.graph.set_read_state(
                    token, email.graph_message_id, is_read
                ),
                action="email.mark_read" if is_read else "email.mark_unread",
            )
        return email

    def toggle_star(self, user, email, *, sync_graph=True):
        value = not email.is_starred
        email.is_starred = value
        email.save(update_fields=["is_starred", "updated_at"])
        if sync_graph:
            self._graph_call(
                email,
                lambda token: self.graph.update_message(
                    token, email.graph_message_id, {"flag": {"flagStatus": "flagged" if value else "notFlagged"}}
                ),
                action="email.star" if value else "email.unstar",
            )
        return email

    def toggle_flag(self, user, email, *, sync_graph=True):
        value = not email.is_flagged
        email.is_flagged = value
        email.save(update_fields=["is_flagged", "updated_at"])
        if sync_graph:
            self._graph_call(
                email,
                lambda token: self.graph.update_message(
                    token, email.graph_message_id, {"flag": {"flagStatus": "flagged" if value else "notFlagged"}}
                ),
                action="email.flag" if value else "email.unflag",
            )
        return email

    def archive(self, user, email, *, sync_graph=True):
        email.is_archived = True
        email.folder = "Archive"
        email.save(update_fields=["is_archived", "folder", "updated_at"])
        if sync_graph:
            self._graph_call(
                email,
                lambda token: self.graph.move_message(token, email.graph_message_id, "archive"),
                action="email.archive",
            )
        return email

    def restore(self, user, email, *, sync_graph=True):
        email.is_archived = False
        email.folder = "Inbox"
        email.save(update_fields=["is_archived", "folder", "updated_at"])
        if sync_graph:
            self._graph_call(
                email,
                lambda token: self.graph.move_message(token, email.graph_message_id, "inbox"),
                action="email.restore",
            )
        return email

    def trash(self, user, email, *, sync_graph=True):
        email.folder = "DeletedItems"
        email.save(update_fields=["folder", "updated_at"])
        if sync_graph:
            self._graph_call(
                email,
                lambda token: self.graph.move_message(token, email.graph_message_id, "deleteditems"),
                action="email.trash",
            )
        return email

    def delete(self, user, email):
        """Permanently delete (Graph + local)."""
        self._graph_call(
            email,
            lambda token: self.graph.delete_message(token, email.graph_message_id),
            action="email.delete",
        )
        email.delete()

    def move(self, user, email, destination):
        """
        Move an email into a mail folder.

        ``destination`` may be a well-known folder name ("inbox", "archive", ...)
        or an arbitrary Graph folder id. Returns the new folder name.
        """
        folder_id = WELL_KNOWN_FOLDERS.get((destination or "").lower(), destination)
        moved = self._graph_call(
            email,
            lambda token: self.graph.move_message(token, email.graph_message_id, folder_id),
            action="email.move",
        )
        folder_name = None
        if moved and isinstance(moved, dict):
            folder_name = moved.get("parentFolderId") or folder_name
        email.folder = folder_id.title() if folder_id.lower() in WELL_KNOWN_FOLDERS else email.folder
        email.save(update_fields=["folder", "updated_at"])
        return email.folder

    # -------------------- categories / tags --------------------

    def apply_category(self, user, email, category_id, *, apply=False):
        category = self.taxonomy_repository.get_category(user, category_id)
        if not category:
            raise MailActionError("Unknown category")
        if apply:
            email.categories.add(category)
        else:
            email.categories.remove(category)
        return category

    def apply_tag(self, user, email, tag_id, *, apply=False):
        tag = self.taxonomy_repository.get_tag(user, tag_id)
        if not tag:
            raise MailActionError("Unknown tag")
        if apply:
            email.tags.add(tag)
        else:
            email.tags.remove(tag)
        return tag

    # -------------------- refresh from Graph --------------------

    def refresh_message(self, user, email):
        """
        Re-fetch a single message from Microsoft Graph and update the local row.
        Returns the refreshed email, or None when the remote message is gone.
        """
        def _fetch(token):
            raw = self.graph.get_message(token, email.graph_message_id)
            if not raw or not raw.get("id"):
                return None
            normalized = self.graph._normalize_message(raw)
            normalized.setdefault("received_at", email.received_at)
            normalized.setdefault("folder", email.folder)
            normalized["is_read"] = email.is_read
            normalized["is_starred"] = email.is_starred
            normalized["is_flagged"] = email.is_flagged
            normalized["has_attachments"] = bool(
                normalized.get("has_attachments") or email.attachments.exists()
            )
            updated, _ = self.email_repository.upsert_from_graph(
                email.outlook_account,
                normalized,
                recipients=self.graph.extract_recipients(raw),
            )
            return updated

        return self._graph_call(email, _fetch, action="email.refresh")

    # -------------------- bulk --------------------

    @transaction.atomic
    def bulk_action(self, user, emails, action, **kwargs):
        """
        Apply a single action to many emails. Returns a result summary.

        Supported actions: read, unread, star, unstar, flag, unflag, archive,
        trash, delete, move (move requires ``destination``), category/tag.
        """
        count = 0
        for email in emails:
            handler = {
                "read": lambda e: self.set_read(user, e, True),
                "unread": lambda e: self.set_read(user, e, False),
                "star": lambda e: self._force(e, "is_starred", True),
                "unstar": lambda e: self._force(e, "is_starred", False),
                "flag": lambda e: self._force(e, "is_flagged", True),
                "unflag": lambda e: self._force(e, "is_flagged", False),
                "archive": lambda e: self.archive(user, e),
                "trash": lambda e: self.trash(user, e),
                "delete": lambda e: self.delete(user, e),
                "move": lambda e: self.move(user, e, kwargs.get("destination", "")),
                "category": lambda e: self.apply_category(
                    user, e, kwargs.get("category"), apply=kwargs.get("apply", True)
                ),
                "tag": lambda e: self.apply_tag(
                    user, e, kwargs.get("tag"), apply=kwargs.get("apply", True)
                ),
            }.get(action)
            if handler is None:
                raise MailActionError(f"Unknown bulk action: {action}")
            handler(email)
            count += 1
        return {"action": action, "affected": count}

    def _force(self, email, field, value):
        setattr(email, field, value)
        email.save(update_fields=[field, "updated_at"])
        return email

    # -------------------- helpers --------------------

    def _graph_call(self, email, callback, *, action):
        """
        Run ``callback(token)`` against Graph for the email's account.

        Converts authentication and Graph failures into :class:`MailActionError`
        and records an audit entry. Local state is never rolled back — the caller
        is responsible for deciding whether the local change should stand.
        """
        token = self.auth_service.get_valid_access_token(email.outlook_account)
        if not token:
            raise MailActionError(
                "No valid access token for this mailbox — please reconnect the account."
            )
        try:
            return callback(token)
        except GraphApiError as exc:
            self.audit.record(
                user=email.outlook_account.user,
                action=action,
                target=email.outlook_account.email,
                status="error",
            )
            logger.exception("Graph action %s failed", action)
            raise MailActionError(str(exc)) from exc
