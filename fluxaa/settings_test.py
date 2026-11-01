"""Settings for the automated test-suite (PostgreSQL, so that the database triggers are exercised)."""
import os

os.environ.setdefault("DJANGO_DEBUG", "1")
os.environ.setdefault("FLUXAA_TESTING", "1")
os.environ.setdefault("DATABASE_URL", "postgres://postgres@/fluxaa?host=/tmp")
os.environ.setdefault("SECURE_DATABASE_URL", "postgres://postgres@/fluxaa_secure?host=/tmp")
os.environ.setdefault("FLUXAA_N4_KEYS", "pWZ3G3t1b9ZkI3s4H6x4m1lJ2bC5mY8fQ9wq7sDqk2E=")
os.environ.setdefault("FLUXAA_SIGNING_KEY", "test-signing-key")

from .settings import *  # noqa: E402,F401,F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
FLUXAA_SMS_BACKEND = "console"
os.makedirs(STATIC_ROOT, exist_ok=True)  # noqa: F405 — WhiteNoise expects it even before collectstatic
# Files written by the tests never land in the media folder of a development or production instance.
import atexit  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402

MEDIA_ROOT = os.environ.get("FLUXAA_TEST_MEDIA_ROOT") or tempfile.mkdtemp(prefix="fluxaa-test-media-")
if not os.environ.get("FLUXAA_TEST_MEDIA_ROOT"):
    atexit.register(shutil.rmtree, MEDIA_ROOT, True)
