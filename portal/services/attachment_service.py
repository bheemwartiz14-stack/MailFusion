"""
Attachment service — download, cache and safe streaming of email attachments.

Binary content is downloaded lazily from Microsoft Graph on first access and
cached in the ``Attachment.content`` column so repeat downloads do not hit the
Graph API. Content is served through Django views which enforce login + the
attachment's owning email is owned by the requesting user.
"""

import logging
import os
import re
import zipfile
from io import BytesIO

from portal.models import Attachment
from portal.repositories import EmailRepository, MicrosoftAuthRepository
from portal.services.audit_service import AuditService
from portal.services.graph_service import GraphService
from portal.services.microsoft_auth_service import MicrosoftAuthService

logger = logging.getLogger(__name__)

_ILLEGAL = re.compile(r"[\\/:*?\"<>|\x00-\x1f]")


class AttachmentError(Exception):
    """Raised when an attachment cannot be served."""


class AttachmentService:
    def __init__(
        self,
        email_repository=None,
        auth_repository=None,
        auth_service=None,
        graph_service=None,
        audit_service=None,
    ):
        self.email_repository = email_repository or EmailRepository()
        self.auth_repository = auth_repository or MicrosoftAuthRepository()
        self.auth_service = auth_service or MicrosoftAuthService()
        self.graph = graph_service or GraphService()
        self.audit = audit_service or AuditService()

    def get_attachment(self, user, email, attachment_id):
        """Return an attachment the user may access, or None."""
        return Attachment.objects.filter(
            pk=attachment_id, email=email, email__outlook_account__user=user
        ).first()

    def download(self, attachment):
        """
        Return the attachment's binary content as bytes.

        Uses the locally cached copy when available; otherwise fetches it from
        Microsoft Graph and stores it for next time.
        """
        if attachment.content is not None and attachment.is_downloaded:
            return bytes(attachment.content)

        account = attachment.email.outlook_account
        token = self.auth_service.get_valid_access_token(account)
        if not token:
            raise AttachmentError("Mailbox is not authenticated — please reconnect the account.")
        content = self.graph.download_attachment(
            token, attachment.email.graph_message_id, attachment.graph_attachment_id
        )
        if content is None:
            raise AttachmentError("Failed to download attachment from Microsoft Graph.")
        attachment.content = content
        attachment.is_downloaded = True
        attachment.download_error = ""
        attachment.save(update_fields=["content", "is_downloaded", "download_error", "updated_at"])
        return content

    def download_all(self, user, email):
        """
        Stream every file attachment of an email as a ZIP archive (bytes).
        Inline (cid) images are excluded.
        """
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for attachment in email.attachments.filter(is_inline=False):
                try:
                    content = self.download(attachment)
                except AttachmentError:
                    continue
                archive.writestr(self.safe_filename(attachment), content)
        return buffer.getvalue()

    @staticmethod
    def safe_filename(attachment):
        """Sanitize an attachment name for Content-Disposition headers."""
        name = _ILLEGAL.sub("_", attachment.name or "attachment")
        return name.strip() or "attachment"

    @staticmethod
    def content_type(attachment):
        return attachment.content_type or "application/octet-stream"

    @staticmethod
    def guess_display_type(attachment):
        """Coarse category used by the UI to pick an icon/thumb."""
        name = (attachment.name or "").lower()
        if name.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg")):
            return "image"
        if name.endswith(".pdf"):
            return "pdf"
        if name.endswith((".doc", ".docx")):
            return "word"
        if name.endswith((".xls", ".xlsx")):
            return "excel"
        if name.endswith((".ppt", ".pptx")):
            return "slides"
        if name.endswith((".zip", ".rar", ".7z", ".tar", ".gz")):
            return "archive"
        return "file"
