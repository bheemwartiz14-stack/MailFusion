"""
Unified Inbox module views.

End-to-end email client backed by Microsoft Graph: unified inbox (infinite
scroll + filters + bulk actions), full email viewer with conversation threads,
compose / reply / reply-all / forward with Graph-backed drafts, drafts, sent
items, cross-mailbox search, attachment download/preview and live unread
counts.

Security model:
    * every view is ``LoginRequiredMixin``;
    * every service call is user-scoped (ownership checked in the service);
    * destructive/write endpoints are POST-only (405 on GET);
    * a lightweight Redis-backed rate limiter guards write endpoints;
    * email HTML is sanitized before rendering.
"""

import io
import json
import logging
from datetime import date, datetime, time, timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.cache import cache
from django.http import FileResponse, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views import View

from portal.base_view import PortalView
from portal.repositories import MicrosoftAuthRepository
from portal.services import (
    AttachmentService,
    EmailService,
    MailComposerService,
    SearchService,
)
from portal.services.email_services import MailActionError
from portal.services.mail_composer_service import MailComposeError
from portal.utils.html import sanitize_html

logger = logging.getLogger(__name__)

PAGE_SIZE = 25
RATE_LIMIT = (20, 60)  # 20 writes per 60 seconds per user


class EmailNotFound(Exception):
    pass


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

FOLDER_MAP = {
    "": {},
    "all": {},
    "inbox": {"folder": "Inbox"},
    "sent": {"folder": "SentItems"},
    "drafts": {"folder": "Drafts", "include_drafts": True},
    "archive": {"folder": "Archive"},
    "starred": {"starred": True},
    "flagged": {"flagged": True},
    "unread": {"read": False},
    "trash": {"folder": "DeletedItems"},
}


def _parse_filters(request, folder=""):
    """Parse inbox query-string filters into repository keyword arguments."""
    filters = dict(FOLDER_MAP.get((folder or "").lower(), {}))

    read = request.GET.get("read", "")
    if read == "read":
        filters["read"] = True
    elif read == "unread":
        filters["read"] = False

    q = (request.GET.get("q", "") or "").strip()
    if q:
        filters["q"] = q

    account = request.GET.get("account", "")
    if account:
        repo = MicrosoftAuthRepository()
        obj = repo.get_account_or_none(account)
        if obj and obj.user_id == request.user.pk:
            filters["account"] = obj

    if request.GET.get("attachments", "") == "1":
        filters["attachments"] = True

    importance = request.GET.get("importance", "")
    if importance in ("low", "normal", "high"):
        filters["importance"] = importance

    if request.GET.get("flagged", "") == "1":
        filters["flagged"] = True
    if request.GET.get("starred", "") == "1":
        filters["starred"] = True

    category = request.GET.get("category", "")
    if category:
        filters["category"] = category

    sender = request.GET.get("sender", "")
    if sender:
        filters["sender"] = sender

    dfrom = parse_date(request.GET.get("date_from", "") or "")
    dto = parse_date(request.GET.get("date_to", "") or "")
    if dfrom:
        filters["date_from"] = timezone.make_aware(datetime.combine(dfrom, time.min))
    if dto:
        filters["date_to"] = timezone.make_aware(datetime.combine(dto, time.max))
    return filters


def _preserve_querystring(request, **overrides):
    """Rebuild the current querystring with ``overrides`` applied."""
    params = request.GET.copy()
    for key, value in overrides.items():
        if value:
            params[key] = value
        else:
            params.pop(key, None)
    encoded = params.urlencode()
    return f"?{encoded}" if encoded else ""


def _rate_limited(request):
    """Redis-backed write limiter. Returns True when the request is allowed."""
    key = f"rate:{request.user.pk}:{request.resolver_match.view_name}"
    pipe = cache.client.get_client() if hasattr(cache, "client") else None
    if pipe is None:
        return True
    try:
        current = pipe.incr(key)
        if current == 1:
            pipe.expire(key, RATE_LIMIT[1])
        return current <= RATE_LIMIT[0]
    except Exception:  # noqa: BLE001 - never block on Redis failures
        logger.debug("Rate limiter unavailable; allowing request")
        return True


def _referer(request, fallback="inbox"):
    return request.META.get("HTTP_REFERER") or reverse(fallback)


# --------------------------------------------------------------------------
# Inbox
# --------------------------------------------------------------------------



class InboxView(LoginRequiredMixin, PortalView):
    """The unified inbox: every mailbox, every message, one feed."""

    template_name = "inbox/inbox.html"
    title = "Unified Inbox"
    breadcrumbs = [{"label": "Unified Inbox"}]
    active_page = "inbox"

    def get(self, request):
        service = EmailService()
        folder = request.GET.get("folder", "all")
        filters = _parse_filters(request, folder=folder)
        filters.setdefault("include_drafts", folder.lower() == "drafts")

        emails = service.list_messages(request.user, **filters)
        total = emails.count()
        page = list(emails[0:PAGE_SIZE])
        has_more = total > len(page)
        context = self.get_context_data()
        context.update(
            emails=page,
            total=total,
            has_more=has_more,
            next_offset=PAGE_SIZE,
            folder=folder,
            filters=filters,
            folders=service.folder_counts(request.user),
            accounts=service.list_accounts(request.user),
            categories=service.list_categories(request.user),
            tags=service.list_tags(request.user),
            querystring=_preserve_querystring(request),
            page_size=PAGE_SIZE,
            now=timezone.now(),
        )
        return render(request, self.template_name, context)


class EmailListView(LoginRequiredMixin, View):
    """HTMX partial: the next page of email rows for infinite scroll."""

    def get(self, request):
        service = EmailService()
        folder = request.GET.get("folder", "all")
        filters = _parse_filters(request, folder=folder)
        filters.setdefault("include_drafts", folder.lower() == "drafts")

        try:
            offset = max(0, int(request.GET.get("offset", 0)))
        except (TypeError, ValueError):
            offset = 0

        emails = service.list_messages(request.user, **filters)
        total = emails.count()
        page = list(emails[offset:offset + PAGE_SIZE])
        has_more = total > offset + len(page)

        context = {
            "emails": page,
            "total": total,
            "has_more": has_more,
            "next_offset": offset + PAGE_SIZE,
            "folder": folder,
            "mode": request.GET.get("mode", "inbox"),
            "querystring": _preserve_querystring(request),
            "now": timezone.now(),
        }
        return render(request, "inbox/partials/email_list.html", context)


class EmailDetailView(LoginRequiredMixin, PortalView):
    """Full email viewer: headers, body, attachments, thread."""

    template_name = "inbox/email_viewer.html"
    active_page = "inbox"

    def get(self, request, email_id):
        service = EmailService()
        email = service.get_message(request.user, email_id)
        if email is None:
            messages.error(request, "Email not found.")
            return redirect("inbox")

        if not email.is_read:
            try:
                service.set_read(request.user, email, True)
            except MailActionError:
                pass  # local state is already updated; Graph sync optional

        thread = service.get_thread(request.user, email.conversation_id)
        for item in thread:
            item._safe_body = sanitize_html(item.body_html)

        context = self.get_context_data(
            title=email.subject or "(no subject)",
            breadcrumbs=[
                {"label": "Unified Inbox", "url": reverse("inbox")},
                {"label": email.subject or "(no subject)"},
            ],
        )
        context.update(
            email=email,
            safe_body=sanitize_html(email.body_html),
            thread=thread,
            thread_count=len(thread),
            accounts=service.list_accounts(request.user),
            folders=service.folder_counts(request.user),
            categories=service.list_categories(request.user),
            attachments=email.attachments.all(),
        )
        return render(request, self.template_name, context)


class EmailThreadPartialView(LoginRequiredMixin, View):
    """HTMX partial: messages in a conversation, oldest first."""

    def get(self, request, email_id):
        service = EmailService()
        email = service.get_message(request.user, email_id)
        if email is None:
            return HttpResponse(status=404)
        thread = service.get_thread(request.user, email.conversation_id)
        return render(
            request,
            "inbox/partials/thread.html",
            {"thread": thread, "current_email_id": str(email.pk)},
        )


class EmailHeadersPartialView(LoginRequiredMixin, View):
    """HTMX partial: raw internet message headers fetched from Graph."""

    def get(self, request, email_id):
        service = EmailService()
        email = service.get_message(request.user, email_id)
        if email is None:
            return HttpResponse(status=404)
        try:
            token = service.auth_service.get_valid_access_token(email.outlook_account)
            headers = (
                service.graph.get_message_headers(token, email.graph_message_id)
                if token
                else []
            )
        except Exception:  # noqa: BLE001 - headers are best-effort
            logger.exception("Failed to fetch internet headers for %s", email_id)
            headers = []
        return render(
            request,
            "inbox/partials/internet_headers.html",
            {"email": email, "headers": headers},
        )


# --------------------------------------------------------------------------
# Compose
# --------------------------------------------------------------------------


def _prefill_recipients(request, email, mode):
    """Build the initial To/CC recipient strings for reply / reply-all."""
    account = email.outlook_account
    if mode == "reply":
        return f'{email.from_name} <{email.from_email}>', "", ""
    if mode == "reply_all":
        mine = account.email.lower()
        to = []
        cc = []
        if email.from_email and email.from_email.lower() != mine:
            to.append(f'{email.from_name} <{email.from_email}>')
        for recipient_type, text in (("to", email.toRecipients), ("cc", email.ccRecipients)):
            for raw in (text or "").split(","):
                addr = raw.strip()
                if not addr or addr.lower() == mine:
                    continue
                (to if recipient_type == "to" else cc).append(addr)
        return ", ".join(to), ", ".join(cc), ""
    return "", "", ""


class ComposeView(LoginRequiredMixin, PortalView):
    """
    Compose a new email, continue an existing draft, or prefill a
    reply / reply-all / forward composer. POST submits via
    :class:`ComposeSubmitView`.
    """

    template_name = "inbox/compose.html"
    active_page = "inbox"

    def get(self, request, draft_id=None, email_id=None, mode="new"):
        service = EmailService()
        accounts = service.list_accounts(request.user)
        if not accounts:
            messages.warning(request, "Connect an Outlook account before composing.")
            return redirect("accounts")

        if email_id:
            original = service.get_message(request.user, email_id)
            if original is None:
                messages.error(request, "Email not found.")
                return redirect("inbox")
        else:
            original = None

        draft = None
        if draft_id:
            draft = service.get_message(request.user, draft_id)
            if draft is None or not draft.is_draft:
                messages.error(request, "Draft not found.")
                return redirect("drafts")

        prefill = {
            "to": "", "cc": "", "bcc": "", "subject": "", "body_html": "",
            "body_text": "", "importance": "normal",
        }
        if draft:
            prefill.update(
                to=draft.toRecipients, cc=draft.ccRecipients, bcc=draft.bccRecipients,
                subject=draft.subject, body_html=draft.body_html,
                body_text=draft.body_text, importance=draft.importance,
            )
        elif original and mode in ("reply", "reply_all", "forward"):
            to, cc, _ = _prefill_recipients(request, original, mode)
            prefix = {"reply": "Re: ", "reply_all": "Re: ", "forward": "Fwd: "}[mode]
            subject = original.subject
            if not subject.lower().startswith(prefix.lower()):
                subject = prefix + subject
            quoted = _quote_body(original, mode)
            prefill.update(to=to, cc=cc, subject=subject, body_html=quoted)

        default_account = next((a for a in accounts if a.is_default), accounts[0])

        context = self.get_context_data(
            title="Compose",
            breadcrumbs=[
                {"label": "Unified Inbox", "url": reverse("inbox")},
                {"label": "Compose"},
            ],
        )
        context.update(
            accounts=accounts,
            default_account=default_account,
            draft=draft,
            original=original,
            mode=mode,
            **prefill,
        )
        return render(request, self.template_name, context)


def _quote_body(email, mode):
    """Build the quoted original message for reply/forward bodies."""
    lines = []
    if mode == "forward":
        lines.append("-------- Forwarded message --------")
    else:
        lines.append("")
    lines.append(f"On {email.received_at:%A, %B %d, %Y at %I:%M %p}, {email.sender_display} wrote:")
    lines.append("")
    if email.body_html:
        return (
            "<br>".join(lines[:1]) + "<br><br>"
            f"<blockquote style='border-left:2px solid #ccc;margin:0 0 0 8px;padding:0 0 0 12px;'>{email.body_html}</blockquote>"
        )
    return "\n".join(lines[:1]) + "\n\n" + f"> {email.body_text or ''}"


class ComposeSubmitView(LoginRequiredMixin, View):
    """POST: send or save a compose / reply / forward."""

    def post(self, request):
        if not _rate_limited(request):
            return HttpResponse("Too many requests", status=429)

        composer = MailComposerService()
        service = EmailService()
        account_id = request.POST.get("account", "")
        account = service.get_account_for_user(request.user, account_id)
        if account is None:
            messages.error(request, "Pick a valid sending account.")
            return redirect("compose")

        data = {
            "to": request.POST.get("to", "").strip(),
            "cc": request.POST.get("cc", "").strip(),
            "bcc": request.POST.get("bcc", "").strip(),
            "subject": request.POST.get("subject", "").strip(),
            "body_html": request.POST.get("body_html", ""),
            "body_text": request.POST.get("body_text", ""),
            "importance": request.POST.get("importance", "normal"),
        }
        attachments = _read_uploaded_files(request)
        action = request.POST.get("submit", "send")
        mode = request.POST.get("mode", "new")
        draft_id = request.POST.get("draft_id", "")
        original_id = request.POST.get("original_id", "")
        original = service.get_message(request.user, original_id) if original_id else None

        try:
            if action == "draft":
                if mode in ("reply", "reply_all") and original:
                    created = composer.save_reply_draft(
                        request, request.user, original,
                        body_html=data["body_html"], body_text=data["body_text"],
                        subject=data["subject"], attachments=attachments,
                        as_reply_all=(mode == "reply_all"),
                    )
                elif mode == "forward" and original:
                    created = composer.save_forward_draft(
                        request, request.user, original, to=data["to"],
                        body_html=data["body_html"], body_text=data["body_text"],
                        subject=data["subject"], attachments=attachments,
                    )
                else:
                    draft = service.get_message(request.user, draft_id) if draft_id else None
                    created = composer.save_draft(
                        request, request.user, account, draft=draft, **data
                    )
                messages.success(request, "Draft saved.")
                return redirect("compose", draft_id=created.pk)

            # send
            if mode in ("reply", "reply_all") and original:
                composer.send_reply(
                    request, request.user, original,
                    body_html=data["body_html"], body_text=data["body_text"],
                    subject=data["subject"], attachments=attachments,
                    as_reply_all=(mode == "reply_all"),
                )
            elif mode == "forward" and original:
                composer.send_forward(
                    request, request.user, original, to=data["to"],
                    body_html=data["body_html"], body_text=data["body_text"],
                    subject=data["subject"], attachments=attachments,
                )
            else:
                draft = service.get_message(request.user, draft_id) if draft_id else None
                if draft and draft.is_draft:
                    # Continue-from-draft: sync the latest edits then send.
                    composer.save_draft(request, request.user, account, draft=draft, **data)
                    composer.send_draft(request, request.user, draft)
                else:
                    composer.send_new(
                        request, request.user, account, attachments=attachments, **data
                    )
            messages.success(request, "Email sent.")
        except (MailComposeError, MailActionError) as exc:
            messages.error(request, str(exc))
            return redirect(request.POST.get("next", "inbox"))
        except Exception:  # noqa: BLE001
            logger.exception("Compose submit failed")
            messages.error(request, "Could not send the email. Please try again.")
            return redirect(request.POST.get("next", "inbox"))

        return redirect("sent_items")


class ComposeAutosaveView(LoginRequiredMixin, View):
    """POST (JSON): background auto-save of a draft."""

    def post(self, request):
        composer = MailComposerService()
        service = EmailService()
        account = service.get_account_for_user(request.user, request.POST.get("account", ""))
        if account is None:
            return JsonResponse({"ok": False, "error": "Invalid account"}, status=400)
        draft = service.get_message(request.user, request.POST.get("draft_id", "")) if request.POST.get("draft_id") else None
        try:
            created = composer.save_draft(
                request, request.user, account, draft=draft,
                to=request.POST.get("to", ""), cc=request.POST.get("cc", ""),
                bcc=request.POST.get("bcc", ""), subject=request.POST.get("subject", ""),
                body_html=request.POST.get("body_html", ""),
                body_text=request.POST.get("body_text", ""),
                importance=request.POST.get("importance", "normal"),
            )
        except (MailComposeError, MailActionError) as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        return JsonResponse({
            "ok": True, "draft_id": str(created.pk),
            "saved_at": timezone.now().isoformat(),
        })


class ComposeModalView(LoginRequiredMixin, View):
    """HTMX: load the composer inside a modal on the inbox page."""

    def get(self, request, email_id=None, mode="new"):
        service = EmailService()
        accounts = service.list_accounts(request.user)
        original = None
        if email_id:
            original = service.get_message(request.user, email_id)
            if original is None:
                return HttpResponse(status=404)
        default_account = next((a for a in accounts if a.is_default), accounts[0])
        prefill = {"to": "", "cc": "", "bcc": "", "subject": "", "body_html": ""}
        if original and mode in ("reply", "reply_all"):
            to, cc, _ = _prefill_recipients(request, original, mode)
            subject = original.subject
            prefix = "Re: "
            if not subject.lower().startswith(prefix.lower()):
                subject = prefix + subject
            prefill = {
                "to": to, "cc": cc, "bcc": "", "subject": subject,
                "body_html": _quote_body(original, mode),
            }
        elif original and mode == "forward":
            subject = original.subject
            if not subject.lower().startswith("fwd:"):
                subject = "Fwd: " + subject
            prefill = {
                "to": "", "cc": "", "bcc": "", "subject": subject,
                "body_html": _quote_body(original, "forward"),
            }
        return render(
            request,
            "inbox/compose_modal.html",
            {
                "accounts": accounts, "default_account": default_account,
                "original": original, "mode": mode, **prefill,
            },
        )


def _read_uploaded_files(request):
    """Extract ``[(name, bytes, content_type), ...]`` from a multipart POST."""
    files = []
    for key in request.FILES:
        uploaded = request.FILES.getlist(key)
        for f in uploaded:
            if f.size <= 0:
                continue
            files.append((f.name, f.read(), getattr(f, "content_type", "") or ""))
    return files


# --------------------------------------------------------------------------
# Attachments on drafts / messages
# --------------------------------------------------------------------------


class ComposeAttachmentUploadView(LoginRequiredMixin, View):
    """POST: attach uploaded files to a draft; returns an attachment item row."""

    def post(self, request):
        if not _rate_limited(request):
            return HttpResponse("Too many requests", status=429)
        composer = MailComposerService()
        service = EmailService()
        draft = service.get_message(request.user, request.POST.get("draft_id", ""))
        if draft is None or not draft.is_draft:
            return JsonResponse({"ok": False, "error": "Draft not found"}, status=404)
        uploaded = _read_uploaded_files(request)
        if not uploaded:
            return JsonResponse({"ok": False, "error": "No files uploaded"}, status=400)
        rows = []
        try:
            for name, content, content_type in uploaded:
                composer.add_attachment(
                    request, request.user, draft, name=name,
                    content=content, content_type=content_type,
                )
                rows.append(name)
        except (MailComposeError, MailActionError) as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        draft.refresh_from_db()
        return render(
            request,
            "inbox/partials/attachment_rows.html",
            {"draft": draft, "added": rows},
        )


class ComposeAttachmentRemoveView(LoginRequiredMixin, View):
    """POST: detach a Graph attachment from a draft."""

    def post(self, request, draft_id, attachment_id):
        composer = MailComposerService()
        service = EmailService()
        draft = service.get_message(request.user, draft_id)
        if draft is None or not draft.is_draft:
            return HttpResponse(status=404)
        try:
            composer.remove_attachment(request, request.user, draft, attachment_id)
        except (MailComposeError, MailActionError) as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        return JsonResponse({"ok": True})


class AttachmentDownloadView(LoginRequiredMixin, View):
    """GET: stream a single attachment with a safe filename."""

    def get(self, request, email_id, attachment_id):
        service = EmailService()
        attachment_service = AttachmentService()
        email = service.get_message(request.user, email_id)
        if email is None:
            return HttpResponse(status=404)
        attachment = attachment_service.get_attachment(request.user, email, attachment_id)
        if attachment is None:
            return HttpResponse(status=404)
        try:
            content = attachment_service.download(attachment)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Attachment download failed")
            messages.error(request, str(exc))
            return redirect("email_detail", email_id=email_id)
        response = HttpResponse(content, content_type=attachment_service.content_type(attachment))
        filename = attachment_service.safe_filename(attachment)
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class AttachmentPreviewView(LoginRequiredMixin, View):
    """GET: inline preview for images and PDFs."""

    PREVIEWABLE = ("image/", "application/pdf")

    def get(self, request, email_id, attachment_id):
        service = EmailService()
        attachment_service = AttachmentService()
        email = service.get_message(request.user, email_id)
        if email is None:
            return HttpResponse(status=404)
        attachment = attachment_service.get_attachment(request.user, email, attachment_id)
        if attachment is None:
            return HttpResponse(status=404)
        ctype = attachment_service.content_type(attachment)
        if not ctype.lower().startswith(self.PREVIEWABLE):
            return HttpResponse(status=403)
        content = attachment_service.download(attachment)
        response = HttpResponse(content, content_type=ctype)
        filename = attachment_service.safe_filename(attachment)
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        return response


class AttachmentDownloadAllView(LoginRequiredMixin, View):
    """GET: download all file attachments of an email as a ZIP."""

    def get(self, request, email_id):
        service = EmailService()
        attachment_service = AttachmentService()
        email = service.get_message(request.user, email_id)
        if email is None:
            return HttpResponse(status=404)
        content = attachment_service.download_all(request.user, email)
        response = HttpResponse(content, content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="{email.subject or "email"}.zip"'
        return response


class EmailDownloadEmlView(LoginRequiredMixin, View):
    """GET: export a message as a standard .eml file."""

    def get(self, request, email_id):
        from email.message import EmailMessage

        service = EmailService()
        email = service.get_message(request.user, email_id)
        if email is None:
            return HttpResponse(status=404)

        msg = EmailMessage()
        msg["Subject"] = email.subject or ""
        msg["From"] = (
            f"{email.from_name} <{email.from_email}>" if email.from_name else email.from_email or ""
        )
        msg["To"] = email.toRecipients
        if email.ccRecipients:
            msg["Cc"] = email.ccRecipients
        if email.reply_to:
            msg["Reply-To"] = email.reply_to
        if email.internet_message_id:
            msg["Message-ID"] = email.internet_message_id
        msg["Date"] = email.received_at.strftime("%a, %d %b %Y %H:%M:%S %z")

        if email.body_html:
            import re

            plain = re.sub(r"<[^>]+>", " ", email.body_html)
            plain = re.sub(r"\s+", " ", plain).strip() or email.body_text
            msg.set_content(plain or "")
            msg.add_alternative(email.body_html, subtype="html")
        else:
            msg.set_content(email.body_text or "")

        response = HttpResponse(msg.as_bytes(), content_type="message/rfc822")
        response["Content-Disposition"] = f'attachment; filename="{email.subject or "message"}.eml"'
        return response


# --------------------------------------------------------------------------
# Folders: drafts / sent / search
# --------------------------------------------------------------------------


class DraftsView(LoginRequiredMixin, PortalView):
    template_name = "inbox/draft_list.html"
    title = "Drafts"
    breadcrumbs = [{"label": "Drafts"}]
    active_page = "inbox"

    def get(self, request):
        service = EmailService()
        filters = _parse_filters(request, folder="drafts")
        filters["folder"] = "Drafts"
        filters["include_drafts"] = True
        emails = service.list_messages(request.user, **filters)
        total = emails.count()
        page = list(emails[0:PAGE_SIZE])
        context = self.get_context_data()
        context.update(
            emails=page, total=total, has_more=total > len(page), next_offset=PAGE_SIZE,
            folder="drafts", mode="drafts", filters=filters,
            folders=service.folder_counts(request.user),
            accounts=service.list_accounts(request.user),
            categories=service.list_categories(request.user),
            querystring=_preserve_querystring(request), page_size=PAGE_SIZE,
            now=timezone.now(),
        )
        return render(request, self.template_name, context)


class SentItemsView(LoginRequiredMixin, PortalView):
    template_name = "inbox/sent_items.html"
    title = "Sent Items"
    breadcrumbs = [{"label": "Sent Items"}]
    active_page = "inbox"

    def get(self, request):
        service = EmailService()
        filters = _parse_filters(request, folder="sent")
        filters["folder"] = "SentItems"
        emails = service.list_messages(request.user, **filters)
        total = emails.count()
        page = list(emails[0:PAGE_SIZE])
        context = self.get_context_data()
        context.update(
            emails=page, total=total, has_more=total > len(page), next_offset=PAGE_SIZE,
            folder="sent", mode="sent", filters=filters,
            folders=service.folder_counts(request.user),
            accounts=service.list_accounts(request.user),
            categories=service.list_categories(request.user),
            querystring=_preserve_querystring(request), page_size=PAGE_SIZE,
            now=timezone.now(),
        )
        return render(request, self.template_name, context)


class SearchView(LoginRequiredMixin, PortalView):
    template_name = "inbox/search.html"
    title = "Search"
    breadcrumbs = [{"label": "Search"}]
    active_page = "inbox"

    def get(self, request):
        service = EmailService()
        search_service = SearchService()
        q = (request.GET.get("q", "") or "").strip()
        filters = _parse_filters(request, folder="all")
        filters["q"] = q or ""
        results = search_service.search(request.user, q, **filters)
        total = results.count()
        page = list(results[0:PAGE_SIZE])
        suggestions = search_service.suggestions(request.user, q) if q else []
        context = self.get_context_data()
        context.update(
            q=q, emails=page, total=total, has_more=total > len(page),
            next_offset=PAGE_SIZE, folder="search", mode="search", filters=filters,
            suggestions=suggestions, folders=service.folder_counts(request.user),
            accounts=service.list_accounts(request.user),
            categories=service.list_categories(request.user),
            querystring=_preserve_querystring(request), page_size=PAGE_SIZE,
            now=timezone.now(),
        )
        return render(request, self.template_name, context)


# --------------------------------------------------------------------------
# Actions (single + bulk)
# --------------------------------------------------------------------------


class EmailActionView(LoginRequiredMixin, View):
    """POST: single or bulk email actions. Returns a redirect + toast."""

    def post(self, request):
        if not _rate_limited(request):
            return HttpResponse("Too many requests", status=429)
        service = EmailService()
        action = request.POST.get("action", "")
        raw_ids = request.POST.getlist("email_ids") or request.POST.getlist("ids")
        if not raw_ids:
            email_id = request.POST.get("email_id", "")
            raw_ids = [email_id] if email_id else []

        emails = []
        for raw in raw_ids:
            email = service.get_message(request.user, raw)
            if email:
                emails.append(email)

        if not emails:
            messages.error(request, "No emails selected.")
            return redirect(_referer(request))

        destination = request.POST.get("destination", "")
        category = request.POST.get("category", "")
        tag = request.POST.get("tag", "")
        try:
            summary = service.bulk_action(
                request.user, emails, action,
                destination=destination, category=category, tag=tag,
            )
            messages.success(request, f"Applied '{action}' to {summary['affected']} message(s).")
        except MailActionError as exc:
            messages.error(request, str(exc))
        except Exception:  # noqa: BLE001
            logger.exception("Email action failed")
            messages.error(request, "Action failed. Please try again.")
        return redirect(_referer(request))


# --------------------------------------------------------------------------
# Live updates
# --------------------------------------------------------------------------


class UnreadCountPartialView(LoginRequiredMixin, View):
    """HTMX partial: live unread + folder counts for the inbox sidebar."""

    def get(self, request):
        service = EmailService()
        folders = service.folder_counts(request.user)
        return render(
            request,
            "inbox/partials/unread_counts.html",
            {"folders": folders, "unread": folders["Inbox"]["unread"]},
        )



class DemoInboxView(LoginRequiredMixin, PortalView):
    def get(self, request, *args, **kwargs):
        return HttpResponse("Demo inbox is not implemented yet.", status=501)