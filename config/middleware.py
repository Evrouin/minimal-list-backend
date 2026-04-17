import base64
import hashlib
import hmac
import json
import os
import time

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.http import JsonResponse
from django.conf import settings

def _get_aes_key():
    key = getattr(settings, "ENCRYPTION_KEY", "")
    if not key:
        return None
    return key.encode()[:32]


def _decrypt_value(value, key_bytes):
    try:
        combined = base64.b64decode(value)
        iv, ciphertext = combined[:12], combined[12:]
        return AESGCM(key_bytes).decrypt(iv, ciphertext, None).decode()
    except Exception:
        return value


def _encrypt_value(value, key_bytes):
    iv = os.urandom(12)
    ciphertext = AESGCM(key_bytes).encrypt(iv, value.encode(), None)
    return base64.b64encode(iv + ciphertext).decode()


def _process_fields(data, key_bytes, fn):
    if isinstance(data, dict):
        result = {}
        for k, v in data.items():
            if k in SENSITIVE_FIELDS and isinstance(v, str):
                result[k] = fn(v, key_bytes)
            elif isinstance(v, dict):
                result[k] = _process_fields(v, key_bytes, fn)
            else:
                result[k] = v
        return result
    return data


class FieldEncryptionMiddleware:
    """Decrypt sensitive request fields and encrypt sensitive response fields (production only)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        key_bytes = _get_aes_key()
        if not key_bytes or not request.path.startswith("/api/auth/"):
            return self.get_response(request)

        # Decrypt request body
        if request.body and request.content_type == "application/json":
            try:
                data = json.loads(request.body)
                decrypted = _process_fields(data, key_bytes, _decrypt_value)
                request._body = json.dumps(decrypted).encode()
            except (json.JSONDecodeError, Exception):
                pass

        response = self.get_response(request)

        # Encrypt response body
        if hasattr(response, "content") and response.get("Content-Type", "").startswith("application/json"):
            try:
                data = json.loads(response.content)
                encrypted = _process_fields(data, key_bytes, _encrypt_value)
                response.content = json.dumps(encrypted).encode()
                response["Content-Length"] = len(response.content)
            except (json.JSONDecodeError, Exception):
                pass

        return response


class HmacVerificationMiddleware:
    """Verify HMAC signature on incoming requests (production only)."""

    TOLERANCE = 300  # 5 minutes

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        key = getattr(settings, "HMAC_SIGNING_KEY", "")
        if not key or request.path in ("/", "/health/"):
            return self.get_response(request)

        signature = request.headers.get("X-Signature")
        timestamp = request.headers.get("X-Timestamp")
        if not signature or not timestamp:
            return JsonResponse({"error": "Missing request signature."}, status=403)

        try:
            ts = int(timestamp)
        except ValueError:
            return JsonResponse({"error": "Invalid timestamp."}, status=403)

        if abs(time.time() - ts) > self.TOLERANCE:
            return JsonResponse({"error": "Request expired."}, status=403)

        body = request.body.decode() if not (request.content_type or "").startswith("multipart/") else ""
        path = request.path
        method = request.method
        message = f"{timestamp}.{method}.{path}.{body}"
        expected = hmac.new(key.encode(), message.encode(), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(signature, expected):
            return JsonResponse({"error": "Invalid request signature."}, status=403)

        return self.get_response(request)


class MaintenanceModeMiddleware:
    """Return 503 for all requests when MAINTENANCE_MODE is enabled."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if getattr(settings, "MAINTENANCE_MODE", False):
            return JsonResponse(
                {"error": "Service is under maintenance. Please try again later."},
                status=503,
            )
        return self.get_response(request)


class RatelimitMiddleware:
    """Convert django-ratelimit 403 to 429 with a proper JSON response."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if response.status_code == 403 and getattr(request, "limited", False):
            return JsonResponse(
                {"error": "Too many requests. Please try again later."},
                status=429,
            )
        return response
