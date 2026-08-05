"""
Inbox views (compatibility shim).

The Unified Inbox module lives in :mod:`portal.views.inbox_module_views`.
This module re-exports the same names so existing imports keep working.
"""

from .inbox_module_views import (  # noqa: F401
    AttachmentDownloadAllView,
    AttachmentDownloadView,
    AttachmentPreviewView,
    ComposeAttachmentRemoveView,
    ComposeAttachmentUploadView,
    ComposeAutosaveView,
    ComposeModalView,
    ComposeSubmitView,
    ComposeView,
    DraftsView,
    EmailActionView,
    EmailDetailView,
    EmailDownloadEmlView,
    EmailHeadersPartialView,
    EmailListView,
    EmailThreadPartialView,
    InboxView,
    SearchView,
    SentItemsView,
    UnreadCountPartialView,
)

__all__ = [
    "AttachmentDownloadAllView",
    "AttachmentDownloadView",
    "AttachmentPreviewView",
    "ComposeAttachmentRemoveView",
    "ComposeAttachmentUploadView",
    "ComposeAutosaveView",
    "ComposeModalView",
    "ComposeSubmitView",
    "ComposeView",
    "DraftsView",
    "EmailActionView",
    "EmailDetailView",
    "EmailDownloadEmlView",
    "EmailHeadersPartialView",
    "EmailListView",
    "EmailThreadPartialView",
    "InboxView",
    "SearchView",
    "SentItemsView",
    "UnreadCountPartialView",
]
