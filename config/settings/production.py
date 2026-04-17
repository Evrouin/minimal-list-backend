"""
Production settings.
"""

from .base import *  # noqa: F403, F405

DEBUG = False

SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=False, cast=bool)  # noqa: F405
SESSION_COOKIE_SECURE = config("SESSION_COOKIE_SECURE", default=True, cast=bool)  # noqa: F405
CSRF_COOKIE_SECURE = config("CSRF_COOKIE_SECURE", default=True, cast=bool)  # noqa: F405
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
X_FRAME_OPTIONS = "DENY"

CORS_ALLOWED_ORIGINS = config("CORS_ALLOWED_ORIGINS", cast=Csv(), default="")  # noqa: F405

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = config("EMAIL_HOST", default="")  # noqa: F405
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)  # noqa: F405
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)  # noqa: F405
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")  # noqa: F405
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")  # noqa: F405

LOGGING["root"]["level"] = "WARNING"  # type: ignore[index]
LOGGING["loggers"]["django"]["level"] = "WARNING"  # type: ignore[index]

# S3-compatible storage (Cloudflare R2)
AWS_ACCESS_KEY_ID = config("AWS_ACCESS_KEY_ID", default="")  # noqa: F405
AWS_SECRET_ACCESS_KEY = config("AWS_SECRET_ACCESS_KEY", default="")  # noqa: F405
AWS_STORAGE_BUCKET_NAME = config("AWS_STORAGE_BUCKET_NAME", default="")  # noqa: F405
AWS_S3_ENDPOINT_URL = config("AWS_S3_ENDPOINT_URL", default="")  # noqa: F405
AWS_S3_CUSTOM_DOMAIN = config("AWS_S3_CUSTOM_DOMAIN", default="")  # noqa: F405
AWS_QUERYSTRING_AUTH = False
AWS_S3_FILE_OVERWRITE = False
AWS_S3_OBJECT_PARAMETERS = {
    "CacheControl": "public, max-age=31536000",
}

if AWS_ACCESS_KEY_ID:
    STORAGES["default"] = {  # noqa: F405
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
    }

HMAC_SIGNING_KEY = config("HMAC_SIGNING_KEY", default="")  # noqa: F405
ENCRYPTION_KEY = config("ENCRYPTION_KEY", default="")  # noqa: F405
