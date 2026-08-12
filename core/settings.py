"""
Portal - Cloud-Based Outlook Email Aggregation Dashboard
Django settings.

UI-only project. No Microsoft Graph API, OAuth or sync business logic.
"""

from pathlib import Path

import os

import dj_database_url

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    return os.getenv(name, str(default)).lower() in ("1", "true", "yes", "on")


def env_int(name, default):
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return int(default)


SECRET_KEY = os.getenv(
    "SECRET_KEY", "django-insecure-mailfusion-ui-only-demo-key"
)
DEBUG = env_bool("DEBUG", True)
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "*").split(",")
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "django.contrib.messages",
    "django.contrib.sessions",
    "django.contrib.auth",
    "django.contrib.admin",
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

# --- Database ---
# Built from the DATABASE_URL env var (set in .env locally, and by Render via
# the DATABASE_URL service binding). Requires DATABASE_URL to be present.
DATABASES = {
    "default": dj_database_url.parse(os.getenv("DATABASE_URL"))
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
SECURE_REFERRER_POLICY = os.getenv("SECURE_REFERRER_POLICY", "same-origin")
X_FRAME_OPTIONS = "DENY"
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", False)
SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", True)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", True)
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", False)
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", False)
CSRF_COOKIE_HTTPONLY = True

# --- Email (used by the built-in password reset flow) ---
EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = env_int("EMAIL_PORT", 587)
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "Portal <no-reply@example.com>")

MICROSOFT_CLIENT_ID = os.getenv("MICROSOFT_CLIENT_ID", "")
MICROSOFT_CLIENT_SECRET = os.getenv("MICROSOFT_CLIENT_SECRET", "")
MICROSOFT_TENANT_ID = os.getenv("MICROSOFT_TENANT_ID", "common")
MICROSOFT_REDIRECT_URI = os.getenv("MICROSOFT_REDIRECT_URI", "http://localhost:8000/accounts/callback/")
SCOPES = os.getenv( "MICROSOFT_GRAPH_SCOPES", "offline_access User.Read Mail.Read Mail.ReadBasic Mail.ReadWrite").split(",")

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

# --- Redis (caching + task coordination) ---
REDIS_URL = os.getenv(
    "REDIS_URL",
    f"redis://{os.getenv('REDIS_HOST', '127.0.0.1')}:{env_int('REDIS_PORT', 6379)}/0",
)

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

# --- Tasks (Django background tasks) ---
# Tasks are defined in ``portal/tasks`` via ``@task``. The built-in
# ``immediate`` backend runs them synchronously in-process (no worker process
# or broker). Recurring jobs are invoked externally (e.g. a scheduled
# management command driven by cron / systemd timer).
TASKS = {
    "default": {
        "BACKEND": "django.tasks.backends.immediate.ImmediateBackend",
    }
}

# --- Task scheduling (recurring jobs, run via `manage.py scheduled_tasks`) ---
# Intervals expressed in seconds; override via env for systemd/cron cadence.
TASK_SYNC_INTERVAL_SECONDS = env_int("SYNC_INTERVAL_SECONDS", 300)
TASK_TOKEN_REFRESH_SECONDS = float(
    os.getenv("TOKEN_REFRESH_INTERVAL_MINUTES", 10)
) * 60
TASK_WEBHOOK_RENEW_SECONDS = float(
    os.getenv("WEBHOOK_RENEW_INTERVAL_MINUTES", 15)
) * 60
TASK_LOG_CLEANUP_SECONDS = float(
    os.getenv("LOG_CLEANUP_INTERVAL_HOURS", 24)
) * 3600
TASK_HEALTH_CHECK_SECONDS = float(
    os.getenv("HEALTH_CHECK_INTERVAL_MINUTES", 5)
) * 60

# --- Synchronization tuning ---
SYNC_WEBHOOK_EXPIRATION_DAYS = env_int("SYNC_WEBHOOK_EXPIRATION_DAYS", 3)
SYNC_WEBHOOK_BASE_URL = os.getenv("SYNC_WEBHOOK_BASE_URL", "")
SYNC_LOG_RETENTION_DAYS = env_int("SYNC_LOG_RETENTION_DAYS", 30)
SYNC_MAX_ATTACHMENT_BYTES = env_int("SYNC_MAX_ATTACHMENT_BYTES", 25 * 1024 * 1024)

INTERNAL_IPS = ["127.0.0.1", "localhost"]

# --- Synchronization tuning ---
