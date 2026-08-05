"""
Celery version for the Portal package.

Importing this module registers the Celery app so ``celery`` CLI / beat /
worker can discover it, and so tasks are loaded at Django startup.
"""

from .celery import celery_app

__all__ = ("celery_app",)