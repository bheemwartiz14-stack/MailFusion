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
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views import View

from portal.base_view import PortalView, build_shell_context, shell_user
from portal.repositories import MicrosoftAuthRepository
from portal.services import (
    AttachmentService,
    EmailService,
    MailComposerService,
)
from portal.services.email_services import MailActionError
from portal.services.graph_service import GraphApiError
from portal.services.mail_composer_service import MailComposeError
from portal.utils.html import sanitize_html

logger = logging.getLogger(__name__)

PAGE_SIZE = 25
PAGE_SIZE_OPTIONS = [10, 25, 50, 100]
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


def _page_query(request):
    """Return the current GET params (minus ``page``) as a raw query string."""
    params = request.GET.copy()
    params.pop("page", None)
    encoded = params.urlencode()
    return f"&{encoded}" if encoded else ""


def _inbox_page_size(request):
    """Read a valid ``page_size`` for the inbox list."""
    try:
        value = int(request.GET.get("page_size", PAGE_SIZE))
    except (TypeError, ValueError):
        return PAGE_SIZE
    if value not in PAGE_SIZE_OPTIONS:
        return PAGE_SIZE
    return value


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
        context = self.get_context_data()
        context.update(_inbox_context(request))
        return render(request, self.template_name, context)


def _inbox_context(request, **extra):
    """Build the shared full-page inbox context (list, sidebar, filters)."""
    service = EmailService()
    folder = request.GET.get("folder", "all")
    filters = _parse_filters(request, folder=folder)
    filters.setdefault("include_drafts", folder.lower() == "drafts")

    emails = service.list_messages(request.user, **filters)
    page_obj = Paginator(emails, _inbox_page_size(request)).get_page(request.GET.get("page"))
    context = {
        "emails": page_obj.object_list,
        "page_obj": page_obj,
        "folder": folder,
        "filters": filters,
        "folders": service.folder_counts(request.user),
        "accounts": service.list_accounts(request.user),
        "categories": service.list_categories(request.user),
        "tags": service.list_tags(request.user),
        "extra_querystring": _page_query(request),
        "page_size_options": PAGE_SIZE_OPTIONS,
        "page_size": PAGE_SIZE,
        "now": timezone.now(),
    }
    context.update(extra)
    return context

class EmailListView(LoginRequiredMixin, View):
    """HTMX partial: a page of email rows (numbered pagination)."""

    def get(self, request):
        service = EmailService()
        folder = request.GET.get("folder", "all")
        filters = _parse_filters(request, folder=folder)
        filters.setdefault("include_drafts", folder.lower() == "drafts")

        emails = service.list_messages(request.user, **filters)
        page_obj = Paginator(emails, _inbox_page_size(request)).get_page(request.GET.get("page"))

        context = {
            "emails": page_obj.object_list,
            "page_obj": page_obj,
            "folder": folder,
            "mode": request.GET.get("mode", "inbox"),
            "extra_querystring": _page_query(request),
            "page_size_options": PAGE_SIZE_OPTIONS,
            "now": timezone.now(),
        }
        return render(request, "inbox/partials/email_list.html", context)


class EmailReplyView(LoginRequiredMixin, View):
    def post(self, request, email_id):
        """POST: send a reply / reply-all to the message identified by url."""
        
    
        if not _rate_limited(request):
            return HttpResponse("Too many requests", status=429)

        service = EmailService()
        original = service.get_message(request.user, email_id)
        if original is None:
            messages.error(request, "The message you are replying to could not be found.")
            return redirect("inbox")

        mode = request.POST.get("mode", "reply")
        composer = MailComposerService()
        data = {
            "body_html": request.POST.get("body_html", ""),
            "body_text": request.POST.get("body_text", ""),
            "subject": request.POST.get("subject", "").strip(),
        }
        print('EmailReplyView data ' , data )
        attachments = _read_uploaded_files(request)
        try:
            composer.send_reply(
                request, request.user, original,
                body_html=data["body_html"], body_text=data["body_text"],
                subject=data["subject"], attachments=attachments,
                as_reply_all=(mode == "reply_all"),
            )
            messages.success(request, "Reply sent.")
        except (MailComposeError, MailActionError, GraphApiError) as exc:
            messages.error(request, str(exc))
        except Exception:  # noqa: BLE001
            logger.exception("Reply submit failed")
            messages.error(request, "Could not send the reply. Please try again.")
        return redirect("email_detail", email_id=email_id)
        # return redirect("inbox")


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
                pass 
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


class ComposeSubmitView(LoginRequiredMixin, View):
    """POST: send a reply / reply-all to an existing message."""

    def post(self, request):
        if not _rate_limited(request):
            return HttpResponse("Too many requests", status=429)

        composer = MailComposerService()
        service = EmailService()
        mode = request.POST.get("mode", "reply")
        original_id = request.POST.get("original_id", "")
        original = service.get_message(request.user, original_id) if original_id else None
        if original is None:
            messages.error(request, "The message you are replying to could not be found.")
            return redirect("inbox")

        data = {
            "body_html": request.POST.get("body_html", ""),
            "body_text": request.POST.get("body_text", ""),
            "subject": request.POST.get("subject", "").strip(),
        }
        attachments = _read_uploaded_files(request)
        try:
            composer.send_reply(
                request, request.user, original,
                body_html=data["body_html"], body_text=data["body_text"],
                subject=data["subject"], attachments=attachments,
                as_reply_all=(mode == "reply_all"),
            )
            messages.success(request, "Reply sent.")
        except (MailComposeError, MailActionError, GraphApiError) as exc:
            messages.error(request, str(exc))
        except Exception:  # noqa: BLE001
            logger.exception("Reply submit failed")
            messages.error(request, "Could not send the reply. Please try again.")
        return redirect("inbox")


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
# Folders
# --------------------------------------------------------------------------


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