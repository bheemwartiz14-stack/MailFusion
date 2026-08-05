"""
Custom template tags and filters for the Portal UI.
Presentation helpers only - no business logic.
"""

from django import template
from django.utils.safestring import mark_safe

register = template.Library()

# Bootstrap Icons -> Material Symbols (Outlined) mapping.
BI_TO_MS = {
    "activity": "monitoring",
    "archive": "archive",
    "arrow-clockwise": "refresh",
    "arrow-left": "arrow_back",
    "arrow-repeat": "sync",
    "arrow-right": "arrow_forward",
    "bell": "notifications",
    "bell-check": "notifications_active",
    "bell-exclamation": "notification_important",
    "bell-slash": "notifications_off",
    "box-arrow-in-right": "login",
    "box-arrow-right": "logout",
    "calendar3": "calendar_today",
    "check2": "check",
    "check2-all": "done_all",
    "check2-circle": "check_circle",
    "check-circle": "check_circle",
    "check-circle-fill": "check_circle",
    "check-lg": "check",
    "chevron-left": "chevron_left",
    "chevron-right": "chevron_right",
    "circle-fill": "circle",
    "clock-history": "history",
    "cloud-arrow-up": "cloud_upload",
    "cloud-check": "cloud_done",
    "cloud-slash": "cloud_off",
    "compass": "explore",
    "cpu": "memory",
    "dot": "circle",
    "download": "download",
    "envelope": "mail",
    "envelope-check-fill": "mark_email_read",
    "envelope-dash": "mail_off",
    "envelope-open": "mark_email_unread",
    "envelope-paper": "mail",
    "envelope-paper-fill": "mail",
    "envelope-x": "mark_email_read",
    "eraser": "auto_fix",
    "exclamation-circle": "error",
    "exclamation-circle-fill": "error",
    "exclamation-triangle": "warning",
    "exclamation-triangle-fill": "warning",
    "eye": "visibility",
    "file-earmark": "description",
    "file-earmark-arrow-down": "file_download",
    "file-earmark-excel": "table_chart",
    "file-earmark-image": "image",
    "file-earmark-pdf": "picture_as_pdf",
    "file-earmark-ppt": "slideshow",
    "file-earmark-word": "description",
    "file-earmark-zip": "folder_zip",
    "flag": "flag",
    "flag-fill": "flag",
    "forward": "forward",
    "funnel": "filter_list",
    "grid-1x2": "dashboard",
    "grid-1x2-fill": "dashboard",
    "hdd-network": "dns",
    "heart-pulse": "monitor_heart",
    "hourglass-split": "hourglass",
    "house-door": "home",
    "inbox": "inbox",
    "inbox-fill": "inbox",
    "incognito": "incognito",
    "journal-text": "article",
    "key": "key",
    "life-preserver": "support",
    "lightning-charge": "bolt",
    "link-45deg": "link",
    "list": "list",
    "list-check": "checklist",
    "list-columns": "view_column",
    "list-ol": "format_list_numbered",
    "list-ul": "format_list_bulleted",
    "lock": "lock",
    "paperclip": "attach_file",
    "patch-check-fill": "verified",
    "pause-circle": "pause_circle",
    "pause-fill": "pause",
    "pencil": "edit",
    "pencil-square": "edit",
    "people": "group",
    "person": "person",
    "phone": "phone",
    "play-circle": "play_circle",
    "play-fill": "play_arrow",
    "plus-circle": "add_circle",
    "plus-lg": "add",
    "printer": "print",
    "quote": "format_quote",
    "reply": "reply",
    "reply-all": "reply_all",
    "save": "save",
    "search": "search",
    "send": "send",
    "send-fill": "send",
    "share": "share",
    "shield": "shield",
    "shield-check": "verified_user",
    "shield-exclamation": "gpp_maybe",
    "shield-lock": "gpp_good",
    "shield-lock-fill": "gpp_good",
    "shield-x": "gpp_bad",
    "stack": "layers",
    "star": "star",
    "star-fill": "star",
    "three-dots": "more_vert",
    "tools": "construction",
    "trash": "delete",
    "trash3": "delete_forever",
    "type-bold": "format_bold",
    "type-italic": "format_italic",
    "type-underline": "format_underlined",
    "wrench-adjustable-circle": "tune",
    "x": "close",
    "x-circle": "cancel",
    "x-circle-fill": "cancel",
    "x-lg": "close",
    "x-octagon": "cancel",
    "x-octagon-fill": "cancel",
}


@register.filter
def ms_icon(value):
    """Map a Bootstrap Icons name (with or without the 'bi-' prefix) to a Material Symbols name."""
    name = str(value or "").replace("bi-", "").split(" ")[0].strip()
    return mark_safe(BI_TO_MS.get(name, name))


@register.filter
def initials(value):
    """Return up to two initials from a full name."""
    parts = str(value or "").split()
    if not parts:
        return "?"
    letters = parts[0][0]
    if len(parts) > 1:
        letters += parts[1][0]
    return letters.upper()


@register.filter
def add_class(field, css_class):
    """Render a form field with an extra CSS class (for error states)."""
    return field.as_widget(attrs={"class": css_class})


@register.filter
def unread_badge(count):
    """Format an unread count for a badge (e.g. 1250 -> 1.2k)."""
    try:
        count = int(count)
    except (TypeError, ValueError):
        return ""
    if count <= 0:
        return ""
    if count < 1000:
        return str(count)
    if count < 1000000:
        return f"{count / 1000:.1f}k".replace(".0k", "k")
    return f"{count / 1000000:.1f}M".replace(".0M", "M")


@register.filter
def account_avatar(email):
    """Render an avatar based on the account email address."""
    initials = (email or "A")[0].upper()
    return mark_safe(
        f'<span class="account-avatar" data-hue="{initials!r}">{initials}</span>'
    )


@register.simple_tag
def nav_is_active(request, *patterns):
    """Mark a nav item active when the current path matches any prefix."""
    path = request.path
    for pattern in patterns:
        if path == pattern or path.startswith(pattern.rstrip("/") + "/"):
            return "active"
    return ""


@register.filter
def filter_attr(queryset, filter_spec):
    """
    Filter a queryset by attribute:value.
    Usage: queryset|filter_attr:"status:active"
    """
    if not queryset:
        return queryset
    try:
        attr, value = filter_spec.split(":", 1)
        return [obj for obj in queryset if getattr(obj, attr, None) == value]
    except (ValueError, AttributeError):
        return queryset


@register.filter
def sum_attr(queryset, attr):
    """Sum a numeric attribute across a queryset."""
    if not queryset:
        return 0
    try:
        return sum(getattr(obj, attr, 0) for obj in queryset)
    except (TypeError, AttributeError):
        return 0


@register.filter
def display_type(attachment):
    """Coarse attachment category used to pick an icon/thumb in the UI."""
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
    return "file"


@register.filter
def is_previewable(attachment):
    """True when the browser can preview the attachment inline."""
    ctype = (attachment.content_type or "").lower()
    return ctype.startswith("image/") or ctype == "application/pdf"


@register.filter
def recipient_rows(recipients, rtype):
    """Filter a recipient queryset by recipient_type."""
    return [r for r in recipients if r.recipient_type == rtype]
