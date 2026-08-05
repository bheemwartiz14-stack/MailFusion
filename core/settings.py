"""
Portal - Cloud-Based Outlook Email Aggregation Dashboard
Django settings.

UI-only project. No Microsoft Graph API, OAuth or sync business logic.
"""

from pathlib import Path

import os

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    return os.environ.get(name, str(default)).lower() in ("1", "true", "yes", "on")


def env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return int(default)


SECRET_KEY = os.environ.get(
    "SECRET_KEY", "django-insecure-mailfusion-ui-only-demo-key"
)
DEBUG = env_bool("DEBUG", True)
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "*").split(",")
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "django.contrib.messages",
    "django.contrib.sessions",
    "django.contrib.auth",
    "django.contrib.admin",
    "django_browser_reload",
    "portal",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django_browser_reload.middleware.BrowserReloadMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "core.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "portal.core.context_processors.sidebar_menu",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "core.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "InboxFusion"),
        "USER": os.environ.get("POSTGRES_USER", "InboxFusion"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "InboxFusion"),
        "HOST": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# --- Authentication (Django built-in) ---
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "/"

# --- Sessions: timeout, remember me, automatic logout after inactivity ---
# SESSION_SAVE_EVERY_REQUEST refreshes the expiry on every request, so a
# session whose "remember me" was unchecked dies after SESSION_INACTIVITY_TIMEOUT
# of inactivity. Remembered sessions live for SESSION_COOKIE_AGE.
SESSION_COOKIE_AGE = env_int("SESSION_COOKIE_AGE", 60 * 60 * 24 * 14)  # 14 days
SESSION_INACTIVITY_TIMEOUT = env_int("SESSION_INACTIVITY_TIMEOUT", 60 * 30)  # 30 min
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

# --- Security (Django built-in middleware) ---
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = os.environ.get("SECURE_REFERRER_POLICY", "same-origin")
X_FRAME_OPTIONS = "DENY"
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", False)
SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", True)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", True)
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", False)
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax")
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", False)
CSRF_COOKIE_HTTPONLY = True

# --- Email (used by the built-in password reset flow) ---
EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = env_int("EMAIL_PORT", 587)
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "Portal <no-reply@example.com>")

MICROSOFT_CLIENT_ID = os.environ.get("MICROSOFT_CLIENT_ID", "")
MICROSOFT_CLIENT_SECRET = os.environ.get("MICROSOFT_CLIENT_SECRET", "")
MICROSOFT_TENANT_ID = os.environ.get("MICROSOFT_TENANT_ID", "common")
MICROSOFT_REDIRECT_URI = os.environ.get("MICROSOFT_REDIRECT_URI", "http://localhost:8000/accounts/callback/")
SCOPES = os.environ.get( "MICROSOFT_GRAPH_SCOPES", "offline_access User.Read Mail.Read Mail.ReadBasic Mail.ReadWrite").split(",")

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "portal/static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Redis (caching + Celery broker/result backend) ---
REDIS_URL = os.environ.get(
    "REDIS_URL",
    f"redis://{os.environ.get('REDIS_HOST', '127.0.0.1')}:{env_int('REDIS_PORT', 6379)}/0",
)

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

# --- Celery (background email synchronization engine) ---
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", REDIS_URL)
CELERY_TIMEZONE = "UTC"
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", False)
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# Retry policy for sync tasks: exponential backoff (e.g. 60, 120, 240 ...).
CELERY_TASK_DEFAULT_RETRY_DELAY = 60
CELERY_TASK_DEFAULT_MAX_RETRIES = 5

CELERY_BROKER_TRANSPORT_OPTIONS = {
    "visibility_timeout": 3600,
    "max_retries": 5,
}

# Celery Beat persistent schedule file (must live on a writable path).
CELERY_BEAT_SCHEDULE_FILENAME = os.environ.get(
    "CELERY_BEAT_SCHEDULE_FILENAME", "/tmp/celerybeat-schedule"
)

# --- Celery Beat schedule (scheduled synchronization fallback) ---
CELERY_BEAT_SCHEDULE = {
    "sync-all-accounts": {
        "task": "portal.tasks.sync_all_accounts",
        "schedule": env_int("SYNC_INTERVAL_SECONDS", 300),  # every 5 minutes
        "options": {"expires": 260},
    },
    "refresh-expired-tokens": {
        "task": "portal.tasks.refresh_expired_tokens",
        "schedule": float(os.environ.get("TOKEN_REFRESH_INTERVAL_MINUTES", 10)) * 60,
    },
    "renew-webhook-subscriptions": {
        "task": "portal.tasks.renew_webhook_subscriptions",
        "schedule": float(os.environ.get("WEBHOOK_RENEW_INTERVAL_MINUTES", 15)) * 60,
    },
    "cleanup-old-logs": {
        "task": "portal.tasks.cleanup_old_logs",
        "schedule": float(os.environ.get("LOG_CLEANUP_INTERVAL_HOURS", 24)) * 3600,
    },
    "run-health-checks": {
        "task": "portal.tasks.run_system_health_checks",
        "schedule": float(os.environ.get("HEALTH_CHECK_INTERVAL_MINUTES", 5)) * 60,
    },
}

# --- Synchronization tuning ---
SYNC_WEBHOOK_EXPIRATION_DAYS = env_int("SYNC_WEBHOOK_EXPIRATION_DAYS", 3)
SYNC_WEBHOOK_BASE_URL = os.environ.get("SYNC_WEBHOOK_BASE_URL", "")
SYNC_LOG_RETENTION_DAYS = env_int("SYNC_LOG_RETENTION_DAYS", 30)
SYNC_MAX_ATTACHMENT_BYTES = env_int("SYNC_MAX_ATTACHMENT_BYTES", 25 * 1024 * 1024)

# --- Tailwind CSS (django-tailwind) ---
TAILWIND_APP_NAME = "theme"
INTERNAL_IPS = ["127.0.0.1", "localhost"]
