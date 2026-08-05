"""
Celery application for the Portal.

Exposes a shared ``celery_app`` used by the web app, the worker and the beat
scheduler. Tasks live under ``portal.tasks`` and are auto-discovered from the
``portal`` app label.
"""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

from celery import Celery

celery_app = Celery("portal")

# Load settings namespace from the Django settings module (all CELERY_* keys).
celery_app.config_from_object("django.conf:settings", namespace="CELERY")

# Discover tasks from installed Django apps once the app registry is ready.
celery_app.autodiscover_tasks()