from django.http import JsonResponse
from django.conf import settings


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
