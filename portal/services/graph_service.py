"""
Microsoft Graph integration.

Thin HTTP wrapper around the Microsoft Graph API. It is transport-only: it
performs authenticated REST calls and normalizes the JSON payloads; it never
touches Django models or repositories.
"""

import base64
import logging
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)


def _u(value):
    """URL-encode a Graph id for safe use inside a path segment."""
    return quote(str(value), safe="")


class GraphApiError(Exception):
    """Raised when a Microsoft Graph REST call fails in a non-recoverable way."""

    def __init__(self, message, *, method="", url="", status_code=None, details=None):
        super().__init__(message)
        self.method = method
        self.url = url
        self.status_code = status_code
        self.details = details or {}


class GraphService:
    def __init__(self, base_url="https://graph.microsoft.com/v1.0"):
        self.base_url = base_url

    # -------------------- helpers --------------------

    def _headers(self, access_token, content_type=None):
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def _get(self, access_token, url, params=None):
        """Perform a GET and return parsed JSON, or None on failure."""
        try:
            response = requests.get(url, headers=self._headers(access_token), params=params, timeout=60)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error("Graph GET %s failed: %s", url, e)
            return None

    def _request(self, method, access_token, url, payload=None):
        try:
            response = requests.request(
                method,
                url,
                headers=self._headers(access_token),
                json=payload,
                timeout=60,
            )
            response.raise_for_status()
            if response.status_code == 204 or not response.content:
                return {}
            return response.json()
        except requests.RequestException as e:
            logger.error("Graph %s %s failed: %s", method, url, e)
            return None

    def _request_or_raise(self, method, access_token, url, payload=None, expected_status=(200,)):
        """
        Perform an authenticated Graph call that MUST succeed.

        Raises :class:`GraphApiError` with Graph's error body on any failure so
        callers can surface a useful message to the user (unlike ``_request``
        which swallows failures and returns None).
        """
        try:
            response = requests.request(
                method,
                url,
                headers=self._headers(access_token),
                json=payload,
                timeout=60,
            )
        except requests.RequestException as e:
            logger.exception("Graph %s %s raised: %s", method, url, e)
            raise GraphApiError(
                f"Network error talking to Microsoft Graph: {e}",
                method=method,
                url=url,
            ) from e

        if response.status_code in (expected_status + (204,)):
            if response.status_code == 204 or not response.content:
                return {}
            return response.json()

        status = response.status_code
        details = {}
        try:
            body = response.json()
            details = body.get("error", body)
        except ValueError:
            body = {}
        message = details.get("message") if isinstance(details, dict) else ""
        raise GraphApiError(
            message or f"Microsoft Graph returned HTTP {status}",
            method=method,
            url=url,
            status_code=status,
            details=details,
        )

    # -------------------- profile --------------------

    def get_user_profile(self, access_token):
        profile = self._get(access_token, f"{self.base_url}/me")
        return profile

    # -------------------- emails / delta --------------------

    _MESSAGE_FIELDS = {
        "graph_message_id": "id",
        "subject": "subject",
        "body_html": ("body", "content"),
        "from_name": ("from", "emailAddress", "name"),
        "from_email": ("from", "emailAddress", "address"),
        "ccRecipients": ("ccRecipients",),
        "bccRecipients": ("bccRecipients",),
        "toRecipients": ("toRecipients",),
        "reply_to": ("replyTo",),
        "conversation_id": "conversationId",
        "internet_message_id": "internetMessageId",
        "in_reply_to": "inReplyTo",
        "has_attachments": "hasAttachments",
        "received_at": "receivedDateTime",
        "importance": "importance",
        "is_read": "isRead",
    }

    _RECIPIENT_FIELDS = {
        "toRecipients": "to",
        "ccRecipients": "cc",
        "bccRecipients": "bcc",
    }

    @staticmethod
    def _dig(data, path):
        for key in path:
            if not isinstance(data, dict) or key not in data:
                return None
            data = data[key]
        return data

    def _normalize_message(self, raw):
        """Map a Graph message dict onto Email model field names.

        Only fields present in the Graph response are included so that delta
        responses (which omit unchanged properties) don't clobber stored data.
        """
        out = {}
        # Body: Graph provides a single ``body`` dict with a contentType of
        # either text or html. Route it to the matching local column and leave
        # the preview/summary for the text body when available.
        body = raw.get("body") if isinstance(raw.get("body"), dict) else None
        if body:
            content = body.get("content", "")
            content_type = (body.get("contentType") or "").lower()
            if content_type == "text":
                out["body_text"] = content
            else:
                out["body_html"] = content

        preview = raw.get("bodyPreview")
        if preview is not None:
            out["preview_text"] = (preview or "")[:255]

        for model_key, graph_path in self._MESSAGE_FIELDS.items():
            if model_key in ("body_html",):
                continue
            value = self._dig(raw, graph_path if isinstance(graph_path, tuple) else (graph_path,))
            if value is None:
                continue
            if model_key in ("ccRecipients", "bccRecipients", "toRecipients", "reply_to"):
                value = ", ".join(
                    r.get("emailAddress", {}).get("address", "")
                    for r in value
                    if isinstance(r, dict)
                )
            elif model_key == "importance":
                value = str(value).lower()
            out[model_key] = value
        # Detect deletions signalled by the delta endpoint.
        removed = raw.get("@removed", {})
        if removed:
            out["_removed"] = True
        return out

    @classmethod
    def extract_recipients(cls, raw):
        """
        Return a flat list of recipient dicts ``{type, name, address, position}``
        parsed from a raw Graph message. Used to persist ``EmailRecipient`` rows.
        """
        recipients = []
        for field, rtype in cls._RECIPIENT_FIELDS.items():
            for i, entry in enumerate(raw.get(field) or []):
                addr = entry.get("emailAddress") or {}
                recipients.append(
                    {
                        "recipient_type": rtype,
                        "name": addr.get("name", ""),
                        "address": addr.get("address", ""),
                        "position": i,
                    }
                )
        return recipients

    def fetch_message_delta(self, access_token, delta_link=None, resource=None):
        """
        Fetch one page of the delta feed.

        ``resource`` defaults to the Inbox messages delta endpoint. Returns a
        tuple ``(messages, next_link, next_delta_link)`` where messages is a
        list of normalized dicts, ``next_link`` is the URL for the following
        page (if any) and ``next_delta_link`` is the stable link for the next
        incremental sync.
        """
        resource = resource or "me/mailFolders/Inbox/messages"
        url = delta_link or f"{self.base_url}/{resource}/delta"
        data = self._get(access_token, url)
        if data is None:
            return [], None, delta_link
        raw_messages = data.get("value", [])
        messages = [self._normalize_message(m) for m in raw_messages]
        return (
            messages,
            data.get("@odata.nextLink"),
            data.get("@odata.deltaLink", delta_link),
        )

    def get_user_emails(self, access_token):
        """Backwards-compatible one-shot fetch of the latest Inbox messages."""
        messages, _, _ = self.fetch_message_delta(access_token)
        return messages

    # -------------------- attachments --------------------

    def list_attachments(self, access_token, message_id):
        """List attachments metadata for a message."""
        data = self._get(
            access_token,
            f"{self.base_url}/me/messages/{_u(message_id)}/attachments",
        )
        return data.get("value", []) if data else []

    def download_attachment(self, access_token, message_id, attachment_id):
        """Download attachment binary content (bytes), or None on failure."""
        try:
            response = requests.get(
                f"{self.base_url}/me/messages/{_u(message_id)}/attachments/{_u(attachment_id)}/$value",
                headers=self._headers(access_token),
                timeout=120,
            )
            response.raise_for_status()
            return response.content
        except requests.RequestException as e:
            logger.error("Attachment download failed (%s): %s", attachment_id, e)
            return None

    # -------------------- single message / folders --------------------

    def get_message(self, access_token, message_id, *, expand_attachments=True):
        """Fetch a single message with full details. Raises GraphApiError."""
        params = {}
        if expand_attachments:
            params["$expand"] = "attachments"
        url = f"{self.base_url}/me/messages/{_u(message_id)}"
        return self._request_or_raise(
            "GET", access_token, url, expected_status=(200,)
        )

    def list_mail_folders(self, access_token):
        """List the user's mail folders (well-known names + ids)."""
        data = self._request_or_raise(
            "GET", access_token, f"{self.base_url}/me/mailFolders", expected_status=(200,)
        )
        return data.get("value", [])

    def get_message_headers(self, access_token, message_id):
        """Fetch the raw internet message headers (list of name/value dicts)."""
        from urllib.parse import quote

        url = (
            f"{self.base_url}/me/messages/{quote(str(message_id))}"
            "?$select=id,internetMessageHeaders"
        )
        data = self._request_or_raise("GET", access_token, url, expected_status=(200,))
        return data.get("internetMessageHeaders", [])

    # -------------------- create / update / send --------------------

    def create_message(self, access_token, message):
        """Create a draft message and return the full created message JSON."""
        return self._request_or_raise(
            "POST", access_token, f"{self.base_url}/me/messages", payload=message,
            expected_status=(201,),
        )

    def update_message(self, access_token, message_id, patch):
        """Patch an existing (draft) message. Returns updated message JSON."""
        return self._request_or_raise(
            "PATCH", access_token, f"{self.base_url}/me/messages/{_u(message_id)}",
            payload=patch, expected_status=(200,),
        )

    def send_draft(self, access_token, message_id):
        """Send a previously-created draft message (202 on success)."""
        return self._request_or_raise(
            "POST", access_token, f"{self.base_url}/me/messages/{_u(message_id)}/send",
            expected_status=(202,),
        )

    def send_new(self, access_token, message, save_to_sent=True):
        """Send a brand-new message via /me/sendMail (202 on success)."""
        payload = {"message": message, "saveToSentItems": save_to_sent}
        return self._request_or_raise(
            "POST", access_token, f"{self.base_url}/me/sendMail", payload=payload,
            expected_status=(202,),
        )

    # -------------------- reply / forward drafts --------------------

    def create_reply(self, access_token, message_id):
        """Create an editable reply draft; returns the draft message JSON."""
        return self._request_or_raise(
            "POST", access_token,
            f"{self.base_url}/me/messages/{_u(message_id)}/createReply",
            expected_status=(201,),
        )

    def create_reply_all(self, access_token, message_id):
        """Create an editable reply-all draft; returns the draft message JSON."""
        return self._request_or_raise(
            "POST", access_token,
            f"{self.base_url}/me/messages/{_u(message_id)}/createReplyAll",
            expected_status=(201,),
        )

    def create_forward(self, access_token, message_id, to_recipients):
        """Create an editable forward draft; returns the draft message JSON."""
        payload = {"toRecipients": to_recipients}
        return self._request_or_raise(
            "POST", access_token,
            f"{self.base_url}/me/messages/{_u(message_id)}/createForward",
            payload=payload, expected_status=(201,),
        )

    # -------------------- management / actions --------------------

    def delete_message(self, access_token, message_id):
        """Permanently delete a message (hard delete)."""
        return self._request_or_raise(
            "DELETE", access_token, f"{self.base_url}/me/messages/{_u(message_id)}",
            expected_status=(204,),
        )

    def move_message(self, access_token, message_id, destination_folder_id):
        """Move a message into another folder; returns the moved message."""
        return self._request_or_raise(
            "POST", access_token, f"{self.base_url}/me/messages/{_u(message_id)}/move",
            payload={"destinationId": destination_folder_id}, expected_status=(201,),
        )

    def set_read_state(self, access_token, message_id, is_read):
        """Mark a message as read (True) or unread (False)."""
        return self._request_or_raise(
            "PATCH", access_token, f"{self.base_url}/me/messages/{_u(message_id)}",
            payload={"isRead": bool(is_read)}, expected_status=(200,),
        )

    # -------------------- attachments (write) --------------------

    def add_file_attachment(
        self,
        access_token,
        message_id,
        *,
        name,
        content_bytes,
        content_type="application/octet-stream",
        is_inline=False,
        content_id="",
    ):
        """Attach a binary file to a draft message. Returns attachment JSON."""
        attachment = {
            "@odata.type": "#microsoft.graph.fileAttachment",
            "name": name,
            "contentBytes": base64.b64encode(content_bytes).decode("ascii"),
            "contentType": content_type,
            "size": len(content_bytes),
            "isInline": bool(is_inline),
        }
        if content_id:
            attachment["contentId"] = content_id
        return self._request_or_raise(
            "POST", access_token,
            f"{self.base_url}/me/messages/{_u(message_id)}/attachments",
            payload=attachment, expected_status=(201,),
        )

    def remove_attachment(self, access_token, message_id, attachment_id):
        """Delete an attachment from a draft message."""
        return self._request_or_raise(
            "DELETE", access_token,
            f"{self.base_url}/me/messages/{_u(message_id)}/attachments/{_u(attachment_id)}",
            expected_status=(204,),
        )

    # -------------------- webhook subscriptions --------------------

    def create_subscription(self, access_token, *, notification_url, resource, expiration_dt, client_state="", change_type="created"):
        """Create a Microsoft Graph change notification subscription."""
        payload = {
            "changeType": change_type,
            "notificationUrl": notification_url,
            "resource": resource,
            "expirationDateTime": expiration_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "clientState": client_state,
        }
        return self._request("POST", access_token, f"{self.base_url}/subscriptions", payload)

    def renew_subscription(self, access_token, subscription_id, expiration_dt):
        """Extend an existing subscription's expiration date."""
        payload = {"expirationDateTime": expiration_dt.strftime("%Y-%m-%dT%H:%M:%SZ")}
        return self._request(
            "PATCH", access_token, f"{self.base_url}/subscriptions/{subscription_id}", payload
        )

    def delete_subscription(self, access_token, subscription_id):
        return self._request("DELETE", access_token, f"{self.base_url}/subscriptions/{subscription_id}")