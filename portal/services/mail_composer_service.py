"""
Mail composer service — send, drafts, reply, reply-all and forward.

All outbound mail flows through Microsoft Graph as the source of truth:

* Every send first creates a Graph draft (``POST /me/messages``), attaches any
  client files, then sends it (``POST /me/messages/{id}/send``). The returned
  draft id is retained locally so sent rows can be correlated.
* Reply / reply-all use ``createReply`` / ``createReplyAll`` which preserve the
  conversation id and internet message id of the original thread.
* Forward uses ``createForward``.

Local rows are written through :class:`EmailRepository` (``upsert_from_graph``)
so drafts and sent items appear in the UI and can be edited/continued.
"""

import logging
import re
from urllib.parse import unquote

from django.utils import timezone

from portal.repositories import EmailRepository, MicrosoftAuthRepository
from portal.services.audit_service import AuditService
from portal.services.graph_service import GraphApiError, GraphService
from portal.services.microsoft_auth_service import MicrosoftAuthService
from portal.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^\s*([^<\n]+?)\s*<([^>\n]+)>\s*$")
LOCAL_DRAFT_PREFIX = "local-draft-"


class MailComposeError(Exception):
    """Raised when an outbound mail operation cannot complete."""


class MailComposerService:
    def __init__(
        self,
        email_repository=None,
        auth_repository=None,
        auth_service=None,
        graph_service=None,
        audit_service=None,
        notification_service=None,
    ):
        self.email_repository = email_repository or EmailRepository()
        self.auth_repository = auth_repository or MicrosoftAuthRepository()
        self.auth_service = auth_service or MicrosoftAuthService()
        self.graph = graph_service or GraphService()
        self.audit = audit_service or AuditService()
        self.notifications = notification_service or NotificationService()

    # -------------------- helpers --------------------

    def _token(self, account):
        token = self.auth_service.get_valid_access_token(account)
        if not token:
            raise MailComposeError(
                "No valid access token for this mailbox — please reconnect the account."
            )
        return token

    @staticmethod
    def parse_recipients(value):
        """
        Parse a comma-separated recipient string that may mix forms:
        ``a@b.com`` and ``"Name" <a@b.com>``. Returns Graph recipient dicts.
        """
        recipients = []
        for token in (value or "").split(","):
            token = token.strip()
            if not token:
                continue
            match = _EMAIL_RE.match(token)
            if match:
                name, address = match.group(1).strip(), match.group(2).strip()
            else:
                name, address = "", unquote(token.strip().strip("<>"))
            if address:
                entry = {"emailAddress": {"address": address}}
                if name:
                    entry["emailAddress"]["name"] = name
                recipients.append(entry)
        return recipients

    @staticmethod
    def _body_payload(body_html, body_text):
        if body_html and body_html.strip():
            return {"contentType": "html", "content": body_html}
        return {"contentType": "text", "content": body_text or ""}

    def _message_payload(
        self, account, *, to, cc, bcc, subject, body_html, body_text, importance="normal"
    ):
        payload = {
            "subject": (subject or "").strip(),
            "body": self._body_payload(body_html, body_text),
            "importance": importance or "normal",
        }
        if to:
            payload["toRecipients"] = self.parse_recipients(to)
        if cc:
            payload["ccRecipients"] = self.parse_recipients(cc)
        if bcc:
            payload["bccRecipients"] = self.parse_recipients(bcc)
        # Explicit from so multi-account / alias mailboxes send from the right
        # address.
        payload["from"] = {
            "emailAddress": {"name": account.name or account.email, "address": account.email}
        }
        return payload

    def _persist(self, account, raw_message, *, folder, is_draft, is_sent):
        normalized = self.graph._normalize_message(raw_message)
        normalized.setdefault("received_at", timezone.now())
        normalized.setdefault("folder", folder)
        normalized["folder"] = folder
        normalized["is_draft"] = is_draft
        normalized["is_sent"] = is_sent
        normalized["has_attachments"] = bool(raw_message.get("attachments"))
        email, _ = self.email_repository.upsert_from_graph(
            account,
            normalized,
            recipients=self.graph.extract_recipients(raw_message),
        )
        return email

    def _attach_many(self, account, graph_message_id, attachments):
        """Attach ``[(name, bytes, content_type), ...]`` to a Graph draft."""
        if not attachments:
            return
        token = self._token(account)
        for name, content, content_type in attachments:
            if not name or not content:
                continue
            self.graph.add_file_attachment(
                token,
                graph_message_id,
                name=name,
                content_bytes=content,
                content_type=content_type or "application/octet-stream",
            )

    def _ensure_graph_draft(self, account, draft):
        """Create the Graph draft if ``draft`` is still local-only. Returns (token, graph_id)."""
        token = self._token(account)
        if draft.graph_message_id.startswith(LOCAL_DRAFT_PREFIX):
            message = self._message_payload(
                account,
                to=draft.toRecipients,
                cc=draft.ccRecipients,
                bcc=draft.bccRecipients,
                subject=draft.subject,
                body_html=draft.body_html,
                body_text=draft.body_text,
                importance=draft.importance,
            )
            created = self.graph.create_message(token, message)
            draft.graph_message_id = created["id"]
            draft.save(update_fields=["graph_message_id", "updated_at"])
        return token, draft.graph_message_id

    def _finish(self, user, account, raw_message, *, action, target=""):
        self.audit.record(
            user=user, action=action, target=target or account.email, status="success"
        )

    # -------------------- new email --------------------

    def send_new(
        self, request, user, account, *, to, cc, bcc, subject, body_html,
        body_text, importance="normal", attachments=None,
    ):
        if not to:
            raise MailComposeError("Recipient (To) is required.")
        token = self._token(account)
        message = self._message_payload(
            account, to=to, cc=cc, bcc=bcc, subject=subject,
            body_html=body_html, body_text=body_text, importance=importance,
        )
        draft = self.graph.create_message(token, message)
        self._attach_many(account, draft["id"], attachments)
        self.graph.send_draft(token, draft["id"])

        raw = dict(draft)
        raw["isRead"] = True
        sent = self._persist(
            account, raw, folder="SentItems", is_draft=False, is_sent=True
        )
        recipients = ", ".join(
            r["emailAddress"]["address"] for r in self.parse_recipients(to)
        )
        self._finish(user, account, raw, action="email.send", target=recipients)
        self.notifications.notify(
            title="Email sent",
            detail=f"{subject or '(no subject)'} sent from {account.email}",
            icon="bi-send-check",
            tone="success",
        )
        return sent

    def save_draft(
        self, request, user, account, *, draft=None, to="", cc="", bcc="",
        subject="", body_html="", body_text="", importance="normal",
    ):
        """Create or update a Graph-backed draft and a local draft row."""
        token = self._token(account)
        if draft is None:
            message = self._message_payload(
                account, to=to, cc=cc, bcc=bcc, subject=subject,
                body_html=body_html, body_text=body_text, importance=importance,
            )
            created = self.graph.create_message(token, message)
            return self._persist(
                account, created, folder="Drafts", is_draft=True, is_sent=False
            )

        # Existing draft: sync to Graph if it is still local-only, then patch.
        _, graph_id = self._ensure_graph_draft(account, draft)
        patch = self._message_payload(
            account, to=to, cc=cc, bcc=bcc, subject=subject,
            body_html=body_html, body_text=body_text, importance=importance,
        )
        updated = self.graph.update_message(token, graph_id, patch)
        self.email_repository.save_local_draft(
            draft.pk,
            subject=subject, body_html=body_html, body_text=body_text,
            to_recipients=to, cc_recipients=cc, bcc_recipients=bcc,
        )
        draft.refresh_from_db()
        self._finish(user, account, updated, action="draft.save", target=draft.subject or "")
        return draft

    def send_draft(self, request, user, draft):
        account = draft.outlook_account
        token, graph_id = self._ensure_graph_draft(account, draft)
        self.graph.send_draft(token, graph_id)
        draft.is_draft = False
        draft.is_sent = True
        draft.folder = "SentItems"
        draft.save(update_fields=["is_draft", "is_sent", "folder", "updated_at"])
        self._finish(user, account, {}, action="email.send", target=draft.subject or "")
        self.notifications.notify(
            title="Draft sent",
            detail=f"{draft.subject or '(no subject)'} sent from {account.email}",
            icon="bi-send-check",
            tone="success",
        )
        return draft

    def discard_draft(self, request, user, draft):
        account = draft.outlook_account
        if not draft.graph_message_id.startswith(LOCAL_DRAFT_PREFIX):
            token = self._token(account)
            try:
                self.graph.delete_message(token, draft.graph_message_id)
            except GraphApiError:
                logger.warning("Could not delete remote draft %s", draft.graph_message_id)
        draft.delete()
        self._finish(user, account, {}, action="draft.discard", target=draft.subject or "")
        return draft

    # -------------------- reply / reply-all --------------------

    def _reply_base(self, request, user, original, *, as_reply_all):
        account = original.outlook_account
        token = self._token(account)
        raw = (
            self.graph.create_reply_all(token, original.graph_message_id)
            if as_reply_all
            else self.graph.create_reply(token, original.graph_message_id)
        )
        # Patch body/subject onto the Graph reply draft.
        return account, token, raw

    def _send_reply(self, request, user, original, *, body_html, body_text,
                    subject=None, attachments=None, as_reply_all=False):
        account, token, raw = self._reply_base(request, user, original, as_reply_all=as_reply_all)
        draft_id = raw["id"]
        patch = {
            "subject": subject if subject is not None else raw.get("subject", ""),
            "body": self._body_payload(body_html, body_text),
        }
        self.graph.update_message(token, draft_id, patch)
        self._attach_many(account, draft_id, attachments)
        self.graph.send_draft(token, draft_id)
        raw["isRead"] = True
        raw["attachments"] = attachments or []
        sent = self._persist(account, raw, folder="SentItems", is_draft=False, is_sent=True)
        self._finish(
            user, account, raw,
            action="email.reply_all" if as_reply_all else "email.reply",
            target=original.subject or "",
        )
        return sent

    def send_reply(self, request, user, original, *, body_html, body_text,
                   subject=None, attachments=None, as_reply_all=False):
        """Send a reply / reply-all to an original message."""
        return self._send_reply(
            request, user, original,
            body_html=body_html, body_text=body_text,
            subject=subject, attachments=attachments, as_reply_all=as_reply_all,
        )

    def save_reply_draft(self, request, user, original, *, body_html, body_text,
                         subject=None, attachments=None, as_reply_all=False):
        account, token, raw = self._reply_base(request, user, original, as_reply_all=as_reply_all)
        draft_id = raw["id"]
        patch = {
            "subject": subject if subject is not None else raw.get("subject", ""),
            "body": self._body_payload(body_html, body_text),
        }
        self.graph.update_message(token, draft_id, patch)
        self._attach_many(account, draft_id, attachments)
        draft = self._persist(account, raw, folder="Drafts", is_draft=True, is_sent=False)
        self._finish(user, account, raw, action="draft.save_reply", target=original.subject or "")
        return draft

    # -------------------- forward --------------------

    def _forward_draft(self, request, user, original, *, to, body_html, body_text,
                       subject=None, attachments=None, as_draft=False):
        account = original.outlook_account
        token = self._token(account)
        to_recipients = self.parse_recipients(to)
        raw = self.graph.create_forward(token, original.graph_message_id, to_recipients)
        draft_id = raw["id"]
        patch = {
            "toRecipients": to_recipients,
            "body": self._body_payload(body_html, body_text),
        }
        if subject is not None:
            patch["subject"] = subject
        self.graph.update_message(token, draft_id, patch)
        self._attach_many(account, draft_id, attachments)

        if as_draft:
            return self._persist(account, raw, folder="Drafts", is_draft=True, is_sent=False)

        raw["isRead"] = True
        raw["attachments"] = attachments or []
        sent = self._persist(account, raw, folder="SentItems", is_draft=False, is_sent=True)
        self._finish(user, account, raw, action="email.forward", target=original.subject or "")
        return sent

    def send_forward(self, request, user, original, *, to, body_html, body_text,
                     subject=None, attachments=None):
        if not to:
            raise MailComposeError("Recipient (To) is required for a forward.")
        return self._forward_draft(
            request, user, original, to=to, body_html=body_html, body_text=body_text,
            subject=subject, attachments=attachments, as_draft=False,
        )

    def save_forward_draft(self, request, user, original, *, to, body_html, body_text,
                           subject=None, attachments=None):
        return self._forward_draft(
            request, user, original, to=to, body_html=body_html, body_text=body_text,
            subject=subject, attachments=attachments, as_draft=True,
        )

    # -------------------- attachments on a draft --------------------

    def add_attachment(self, request, user, draft, *, name, content, content_type):
        account = draft.outlook_account
        token, graph_id = self._ensure_graph_draft(account, draft)
        result = self.graph.add_file_attachment(
            token, graph_id, name=name, content_bytes=content,
            content_type=content_type or "application/octet-stream",
        )
        draft.has_attachments = True
        draft.save(update_fields=["has_attachments", "updated_at"])

        from portal.models import Attachment

        Attachment.objects.update_or_create(
            email=draft,
            graph_attachment_id=result.get("id", ""),
            defaults={
                "name": name,
                "content_type": content_type or "application/octet-stream",
                "size_bytes": len(content),
                "content": content,
                "is_downloaded": True,
                "is_inline": False,
            },
        )
        self._finish(user, account, result, action="attachment.upload", target=name)
        return result

    def remove_attachment(self, request, user, draft, attachment_id):
        account = draft.outlook_account
        if draft.graph_message_id.startswith(LOCAL_DRAFT_PREFIX):
            raise MailComposeError("Attachment not uploaded to Microsoft Graph yet.")
        token = self._token(account)
        self.graph.remove_attachment(token, draft.graph_message_id, attachment_id)

        from portal.models import Attachment

        Attachment.objects.filter(
            email=draft, graph_attachment_id=attachment_id
        ).delete()
        draft.has_attachments = draft.attachments.exists()
        draft.save(update_fields=["has_attachments", "updated_at"])
        self._finish(user, account, {}, action="attachment.remove", target=attachment_id)
        return True
