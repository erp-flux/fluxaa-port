"""
FLUXAA Port — Django settings.

All deployment-specific values come from environment variables (see deploy/.env.example).
Two databases are used:
  * default — the operational registry of port calls;
  * secure  — the N4 security domain (armed guards, escorts, incidents), physically separate,
              with its own credentials and its own encryption keys (CDC EF-12.4, orientation 3).
"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from django.utils.translation import gettext_lazy as _

BASE_DIR = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------------------
# Environment helpers
# --------------------------------------------------------------------------------------
def env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name, default)


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


def database_from_url(url: str) -> dict:
    """Parse postgres://user:pass@host:port/dbname or sqlite:///path into a Django DATABASES entry."""
    parsed = urlparse(url)
    if parsed.scheme in {"sqlite", "sqlite3"}:
        path = unquote(parsed.path)
        if path.startswith("//"):
            path = path[1:]
        name = path.lstrip("/") if path not in {"", "/"} else ":memory:"
        if not name.startswith(":") and not Path(name).is_absolute():
            name = str(BASE_DIR / name)
        return {"ENGINE": "django.db.backends.sqlite3", "NAME": name}
    if parsed.scheme not in {"postgres", "postgresql", "pgsql"}:
        raise ValueError(f"Unsupported database URL scheme: {parsed.scheme}")
    options = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    config = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": unquote(parsed.path.lstrip("/")),
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": unquote(parsed.hostname or ""),
        "PORT": str(parsed.port or ""),
        "CONN_MAX_AGE": int(env("DB_CONN_MAX_AGE", "60")),
        "OPTIONS": {},
    }
    if "host" in options:  # unix socket: postgres://user@/db?host=/tmp
        config["HOST"] = options.pop("host")
    if "sslmode" in options:
        config["OPTIONS"]["sslmode"] = options.pop("sslmode")
    return config


# --------------------------------------------------------------------------------------
# Core
# --------------------------------------------------------------------------------------
DEBUG = env_bool("DJANGO_DEBUG", False)
SECRET_KEY = env("DJANGO_SECRET_KEY") or ("insecure-dev-key-change-me" if DEBUG else None)
if not SECRET_KEY:
    raise RuntimeError("DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is off.")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS", "")
SITE_URL = env("FLUXAA_SITE_URL", "http://localhost:8000").rstrip("/")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "drf_spectacular",
    "drf_spectacular_sidecar",
    "apps.core",
    "apps.registry",
    "apps.secure",
    "apps.api",
    "apps.ai",
    "apps.ais",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.core.middleware.ContentSecurityPolicyMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.core.middleware.PortContextMiddleware",
    "apps.core.middleware.MfaEnforcementMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "fluxaa.urls"
WSGI_APPLICATION = "fluxaa.wsgi.application"
ASGI_APPLICATION = "fluxaa.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.i18n",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.fluxaa",
            ],
        },
    },
]

# --------------------------------------------------------------------------------------
# Databases
# --------------------------------------------------------------------------------------
# FLUXAA_MIGRATE=1 switches both aliases to the *owner* credentials, used only to run
# migrations and apply grants. At runtime the application connects with the *app* role,
# which has no DELETE/TRUNCATE privilege on registry tables (CDC ENF-3.6).
_migrating = env_bool("FLUXAA_MIGRATE", False)
_default_url = env("DATABASE_OWNER_URL") if _migrating and env("DATABASE_OWNER_URL") else env(
    "DATABASE_URL", "sqlite:///db.sqlite3"
)
_secure_url = env("SECURE_DATABASE_OWNER_URL") if _migrating and env("SECURE_DATABASE_OWNER_URL") else env(
    "SECURE_DATABASE_URL", "sqlite:///db_secure.sqlite3"
)
DATABASES = {
    "default": database_from_url(_default_url),
    "secure": database_from_url(_secure_url),
}
DATABASE_ROUTERS = ["fluxaa.db_router.DomainRouter"]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "core.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LOGIN_URL = "core:login"
LOGIN_REDIRECT_URL = "registry:dashboard"
LOGOUT_REDIRECT_URL = "core:login"

# --------------------------------------------------------------------------------------
# Internationalisation (CDC ENF-7): French and English, UTC in database, port time zone on screen
# --------------------------------------------------------------------------------------
LANGUAGE_CODE = "fr"
LANGUAGES = [("fr", _("Français")), ("en", _("English"))]
LOCALE_PATHS = [BASE_DIR / "locale"]
USE_I18N = True
TIME_ZONE = "UTC"
USE_TZ = True

# --------------------------------------------------------------------------------------
# Static and media
# --------------------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = Path(env("DJANGO_STATIC_ROOT", str(BASE_DIR / "staticfiles")))
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
        if not DEBUG and not env_bool("FLUXAA_TESTING", False)
        else "django.contrib.staticfiles.storage.StaticFilesStorage"
    },
}
MEDIA_URL = "/media/"  # never served directly: documents are streamed through access-checked views
MEDIA_ROOT = Path(env("DJANGO_MEDIA_ROOT", str(BASE_DIR / "media")))
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 30 * 1024 * 1024
FLUXAA_MAX_UPLOAD_MB = int(env("FLUXAA_MAX_UPLOAD_MB", "25"))

# --------------------------------------------------------------------------------------
# Security
# --------------------------------------------------------------------------------------
SESSION_COOKIE_AGE = int(env("SESSION_COOKIE_AGE", str(12 * 3600)))
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False  # read by HTMX for the X-CSRFToken header
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
# Sent on every HTML page (apps.core.middleware.ContentSecurityPolicyMiddleware). Scripts come only from the
# platform's own static files; inline style attributes are allowed (positions on the berth plan and timelines);
# images may be data:/blob: (QR codes, photos and signatures taken in the field app before they are sent).
FLUXAA_CONTENT_SECURITY_POLICY = (env("FLUXAA_CONTENT_SECURITY_POLICY") or "").strip() or (  # empty = default
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
    "font-src 'self'; connect-src 'self'; worker-src 'self' blob:; manifest-src 'self'; media-src 'self' blob:; "
    "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)
if not DEBUG:
    SESSION_COOKIE_SECURE = env_bool("DJANGO_SECURE_COOKIES", True)
    CSRF_COOKIE_SECURE = env_bool("DJANGO_SECURE_COOKIES", True)
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SSL_REDIRECT", True)
    SECURE_HSTS_SECONDS = int(env("DJANGO_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_REDIRECT_EXEMPT = [r"^healthz$"]
    # HSTS preload commits the whole domain of the port for years: a decision for its owner, not a default.
    SECURE_HSTS_PRELOAD = env_bool("DJANGO_HSTS_PRELOAD", False)
    if not SECURE_HSTS_PRELOAD:
        SILENCED_SYSTEM_CHECKS = ["security.W021"]

# --------------------------------------------------------------------------------------
# REST API (CDC orientation 5: public API from V1)
# --------------------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.api.authentication.BearerTokenAuthentication",
        "apps.api.authentication.MasterAuthentication",
        "apps.api.authentication.MfaSessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 50,
    "EXCEPTION_HANDLER": "apps.api.exceptions.fluxaa_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.UserRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"user": env("API_THROTTLE_USER", "2000/hour"), "verify": "60/minute"},
}
SPECTACULAR_SETTINGS = {
    "SWAGGER_UI_DIST": "SIDECAR",
    "SWAGGER_UI_FAVICON_HREF": "SIDECAR",
    "REDOC_DIST": "SIDECAR",
    "TITLE": "FLUXAA Port API",
    "DESCRIPTION": "Registre opérationnel des escales pétrolières — API publique V1 / Operational registry of tanker port calls — public API v1.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

# --------------------------------------------------------------------------------------
# E-mail and SMS (CDC EF-18): SMS is used for escalations only
# --------------------------------------------------------------------------------------
EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", "localhost")
EMAIL_PORT = int(env("EMAIL_PORT", "587"))
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "FLUXAA Port <no-reply@fluxaa.io>")
FLUXAA_SMS_BACKEND = env("FLUXAA_SMS_BACKEND", "console")  # console | webhook | disabled
FLUXAA_SMS_WEBHOOK_URL = env("FLUXAA_SMS_WEBHOOK_URL", "")
FLUXAA_SMS_WEBHOOK_TOKEN = env("FLUXAA_SMS_WEBHOOK_TOKEN", "")

# --------------------------------------------------------------------------------------
# FLUXAA specifics
# --------------------------------------------------------------------------------------
# Key used to seal journal entries, signatures and authorizations (HMAC-SHA256).
FLUXAA_SIGNING_KEY = env("FLUXAA_SIGNING_KEY") or SECRET_KEY
# N4 domain: Fernet keys (comma-separated, newest first, for rotation). Distinct from every other key.
FLUXAA_N4_KEYS = env_list("FLUXAA_N4_KEYS", "")
# Timestamp provider (CDC ENF-4.2, open point O04). "local" now; a qualified RFC 3161 TSA can be plugged later.
FLUXAA_TIMESTAMP_PROVIDER = env("FLUXAA_TIMESTAMP_PROVIDER", "local")
FLUXAA_TSA_URL = env("FLUXAA_TSA_URL", "")
# Strong authentication (CDC ENF-3.1)
FLUXAA_MFA_REQUIRED_ROLES = {"CAP", "APO", "SUR"}
FLUXAA_MFA_STEPUP_SECONDS = int(env("FLUXAA_MFA_STEPUP_SECONDS", str(8 * 3600)))
FLUXAA_MFA_ENFORCED = env_bool("FLUXAA_MFA_ENFORCED", True)
# Offline entries synchronised later than this are flagged "saisie différée" (CDC EF-14.3)
FLUXAA_DEFERRED_THRESHOLD_SECONDS = int(env("FLUXAA_DEFERRED_THRESHOLD_SECONDS", "120"))
# An online entry declared for a time this much earlier than its recording is also marked "deferred entry"
# (shown on every document): the time of a fact is declared by its emitter, its lateness is visible.
FLUXAA_LATE_ENTRY_SECONDS = int(env("FLUXAA_LATE_ENTRY_SECONDS", "1800"))
# Optional AI assistance (CDC EF-17). Off unless the operator provides a key AND the reference of the
# contractual clause with the provider; each port must also opt in (Port.ai_assistance_enabled).
# The assistant never decides, never signs, and never reads the N4 security domain.
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY", "")
FLUXAA_AI_PROVIDER_AGREEMENT = env("FLUXAA_AI_PROVIDER_AGREEMENT", "")
FLUXAA_AI_ENABLED = (env_bool("FLUXAA_AI_ENABLED", False) and bool(ANTHROPIC_API_KEY)
                     and bool(FLUXAA_AI_PROVIDER_AGREEMENT))
FLUXAA_AI_MODEL = env("FLUXAA_AI_MODEL", "claude-sonnet-5-5")
FLUXAA_AI_TIMEOUT_SECONDS = int(env("FLUXAA_AI_TIMEOUT_SECONDS", "90"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
    "loggers": {"django.db.backends": {"level": "WARNING"}},
}
