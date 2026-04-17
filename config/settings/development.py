"""
Development settings.
"""

from .base import *

DEBUG = config("DEBUG", default=True, cast=bool)

# Only add debug toolbar if installed
try:
    import debug_toolbar  # type: ignore[import-untyped]  # noqa: F401

    INSTALLED_APPS += ["debug_toolbar"]
    MIDDLEWARE += ["debug_toolbar.middleware.DebugToolbarMiddleware"]
    INTERNAL_IPS = ["127.0.0.1", "localhost"]
except ImportError:
    pass

CORS_ALLOW_ALL_ORIGINS = True

EMAIL_BACKEND = config(
    "EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = config("EMAIL_HOST", default="")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")

ENCRYPTION_KEY = config("ENCRYPTION_KEY", default="")
HMAC_SIGNING_KEY = config("HMAC_SIGNING_KEY", default="")
