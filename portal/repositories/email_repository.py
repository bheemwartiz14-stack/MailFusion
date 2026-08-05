"""
Email repository.

Data access for the ``Email`` model only. This layer contains pure database
queries and persistence; it must never contain business logic.

Dependency rule: repositories may access models, nothing else.
"""

import uuid

from django.db.models import Count, Q

from portal.models import Email, EmailRecipient

from django.utils import timezone

# Folders excluded from the default unified Inbox view.
SYSTEM_OUT_FOLDERS = ("SentItems", "Drafts", "Archive", "DeletedItems")


class EmailRepository:
    """Persistence layer for synced emails."""

    # -------------------- unified inbox --------------------

    def list_messages(
        self,
        user,
        *,
        q="",
        folder="",
        account=None,
        read=None,
        attachments=None,
        importance=None,
        flagged=None,
        starred=None,
        category=None,
        tag=None,
        sender=None,
        date_from=None,
        date_to=None,
        include_drafts=False,
    ):
        """
        Return the user's emails (across every connected mailbox) newest first.

        ``folder`` mirrors the mail folder name ("Inbox", "SentItems", ...).
        When empty the unified view is returned (system folders excluded unless
        ``include_drafts`` is set). All other arguments are optional tri-state /
        value filters.
        """
        qs = Email.objects.filter(outlook_account__user=user).select_related(
            "outlook_account"
        )
        folder = (folder or "").strip()
        if folder:
            if folder.lower() in ("inbox",):
                qs = qs.filter(folder="Inbox")
            else:
                qs = qs.filter(folder=folder)
        else:
            # Unified inbox: drop system folders (drafts stay out unless asked).
            excluded = list(SYSTEM_OUT_FOLDERS)
            if include_drafts:
                excluded = [f for f in excluded if f != "Drafts"]
            qs = qs.exclude(folder__in=excluded)

        if account is not None:
            qs = qs.filter(outlook_account=account, outlook_account__user=user)
        if read is True:
            qs = qs.filter(is_read=True)
        elif read is False:
            qs = qs.filter(is_read=False)
        if attachments is True:
            qs = qs.filter(has_attachments=True)
        elif attachments is False:
            qs = qs.filter(has_attachments=False)
        if importance:
            qs = qs.filter(importance=importance)
        if flagged is True:
            qs = qs.filter(is_flagged=True)
        elif flagged is False:
            qs = qs.filter(is_flagged=False)
        if starred is True:
            qs = qs.filter(is_starred=True)
        elif starred is False:
            qs = qs.filter(is_starred=False)
        if sender:
            qs = qs.filter(
                Q(from_name__icontains=sender) | Q(from_email__icontains=sender)
            )
        if date_from:
            qs = qs.filter(received_at__gte=date_from)
        if date_to:
            qs = qs.filter(received_at__lte=date_to)
        if category:
            qs = qs.filter(categories__id=category)
        if tag:
            qs = qs.filter(tags__id=tag)
        q = (q or "").strip()
        if q:
            qs = qs.filter(
                Q(subject__icontains=q)
                | Q(from_name__icontains=q)
                | Q(from_email__icontains=q)
                | Q(preview_text__icontains=q)
                | Q(toRecipients__icontains=q)
                | Q(body_html__icontains=q)
            )
        return qs.order_by("-received_at", "-id")

    def unread_count(self, user):
        """Unread count across all of the user's mailboxes."""
        return Email.objects.filter(
            outlook_account__user=user, is_read=False
        ).exclude(folder__in=SYSTEM_OUT_FOLDERS).count()

    def folder_counts(self, user):
        """Per-folder counts for the sidebar (Inbox, Drafts, Sent, Archived)."""
        rows = (
            Email.objects.filter(outlook_account__user=user)
            .values("folder")
            .annotate(total=Count("id"))
        )
        counts = {row["folder"]: row["total"] for row in rows}
        unread = (
            Email.objects.filter(outlook_account__user=user, is_read=False)
            .values("folder")
            .annotate(total=Count("id"))
        )
        unread_map = {row["folder"]: row["total"] for row in unread}
        return {
            "Inbox": {"total": counts.get("Inbox", 0), "unread": unread_map.get("Inbox", 0)},
            "Drafts": {"total": counts.get("Drafts", 0), "unread": None},
            "SentItems": {"total": counts.get("SentItems", 0), "unread": None},
            "Archive": {
                "total": counts.get("Archive", 0) + counts.get("archive", 0),
                "unread": None,
            },
        }

    # -------------------- single / thread --------------------

    def get_for_user(self, user, pk):
        """Return a single email the user owns (with relations), or None."""
        return (
            Email.objects.filter(pk=pk, outlook_account__user=user)
            .select_related("outlook_account")
            .prefetch_related("recipients", "attachments", "categories", "tags")
            .first()
        )

    def get_by_graph_id(self, account, graph_message_id):
        return (
            Email.objects.filter(
                outlook_account=account, graph_message_id=graph_message_id
            ).first()
        )

    def conversation_root(self, user, email):
        """Return the oldest message of a thread (used to anchor ordering)."""
        return (
            Email.objects.filter(
                outlook_account__user=user,
                conversation_id=email.conversation_id,
            )
            .order_by("received_at")
            .first()
        )

    def thread_messages(self, user, conversation_id, *, include_self=True):
        """Every message in a conversation, oldest first, for the thread view."""
        qs = Email.objects.filter(
            outlook_account__user=user, conversation_id=conversation_id
        ).select_related("outlook_account")
        if not include_self:
            qs = qs.exclude(conversation_id="")
        return list(qs.order_by("received_at", "id"))

    def thread_base_queryset(self, user, conversation_id):
        """QuerySet of a conversation for bulk actions (final reply, read, ...)."""
        return Email.objects.filter(
            outlook_account__user=user, conversation_id=conversation_id
        )

    def thread_count(self, user, conversation_id):
        return Email.objects.filter(
            outlook_account__user=user, conversation_id=conversation_id
        ).count()

    # -------------------- persistence / state --------------------

    def set_read(self, queryset, is_read):
        """Bulk set read state; returns affected count."""
        return queryset.update(is_read=is_read)

    def bulk_toggle_field(self, queryset, field, value):
        return queryset.update(**{field: value})

    def move_to_folder(self, queryset, folder):
        return queryset.update(folder=folder)

    def bulk_delete(self, queryset):
        emails = list(queryset)
        count, _ = Email.objects.filter(pk__in=[e.pk for e in emails]).delete()
        return count

    def create_draft(self, *, account, subject="", body_html="", body_text="",
                     to_recipients="", cc_recipients="", bcc_recipients="",
                     graph_message_id=""):
        """Persist a local draft that may or may not have a Graph id yet."""
        from django.utils import timezone

        graph_id = graph_message_id or f"local-draft-{uuid.uuid4()}"
        return Email.objects.create(
            outlook_account=account,
            graph_message_id=graph_id,
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            toRecipients=to_recipients,
            ccRecipients=cc_recipients,
            bccRecipients=bcc_recipients,
            folder="Drafts",
            is_draft=True,
            received_at=timezone.now(),
        )

    def save_local_draft(self, pk, *, subject="", body_html="", body_text="",
                         to_recipients="", cc_recipients="", bcc_recipients=""):
        """Update an existing draft in place; returns the Email or None."""
        draft = Email.objects.filter(pk=pk, is_draft=True).first()
        if not draft:
            return None
        draft.subject = subject
        draft.body_html = body_html
        draft.body_text = body_text
        draft.toRecipients = to_recipients
        draft.ccRecipients = cc_recipients
        draft.bccRecipients = bcc_recipients
        draft.save(update_fields=[
            "subject", "body_html", "body_text", "toRecipients",
            "ccRecipients", "bccRecipients", "updated_at",
        ])
        return draft

    # -------------------- recipients --------------------

    def replace_recipients(self, email, recipient_dicts):
        """Replace an email's TO/CC/BCC recipient rows from Graph payloads."""
        email.recipients.all().delete()
        created = []
        for item in recipient_dicts or []:
            if not item.get("address"):
                continue
            created.append(
                EmailRecipient(
                    email=email,
                    recipient_type=item["recipient_type"],
                    name=item.get("name", ""),
                    address=item["address"],
                    position=item.get("position", 0),
                )
            )
        if created:
            EmailRecipient.objects.bulk_create(created)
        return created

    # -------------------- graph round-trip --------------------

    def upsert_from_graph(self, account, normalized, recipients=None):
        """
        Persist a normalized Graph message dict (see ``GraphService``) keyed by
        ``(account, graph_message_id)``. Optionally replaces TO/CC/BCC rows.
        Returns the ``(email, created)`` tuple.
        """
        graph_id = normalized.get("graph_message_id")
        defaults = {
            k: v
            for k, v in normalized.items()
            if k not in ("graph_message_id", "_removed")
        }
        defaults.setdefault("folder", "Inbox")
        email, created = Email.objects.update_or_create(
            outlook_account=account,
            graph_message_id=graph_id,
            defaults=defaults,
        )
        if recipients:
            self.replace_recipients(email, recipients)
        return email, created