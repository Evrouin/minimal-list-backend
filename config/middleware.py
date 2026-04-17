import hashlib
import hmac
import time

from django.http import JsonResponse
from django.conf import settings


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
