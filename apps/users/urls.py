from django.utils.decorators import method_decorator
from django.urls import path
from django_ratelimit.decorators import ratelimit
from rest_framework import status
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.views import TokenRefreshView


@method_decorator(ratelimit(key="ip", rate="30/h", method="POST"), name="dispatch")
class RateLimitedTokenRefreshView(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        try:
            return super().post(request, *args, **kwargs)
        except TokenError:
            return Response(
                {"error": "Token is invalid or expired. Please log in again."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

from .views import (
    ChangePasswordView,
    CustomTokenObtainPairView,
    RegisterView,
    UserProfileView,
    delete_account,
    google_login,
    logout,
    password_reset_confirm,
    password_reset_request,
    resend_verification,
    set_password,
    unlock_account,
    verify_email,
)

urlpatterns = [
    # Authentication
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", CustomTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("login/google/", google_login, name="google_login"),
    path("logout/", logout, name="logout"),
    path("token/refresh/", RateLimitedTokenRefreshView.as_view(), name="token_refresh"),
    # Email verification
    path("verify-email/<str:token>/", verify_email, name="verify_email"),
    path("resend-verification/", resend_verification, name="resend_verification"),
    path("unlock-account/<str:token>/", unlock_account, name="unlock_account"),
    # Password reset
    path("password-reset/", password_reset_request, name="password_reset_request"),
    path("password-reset/confirm/", password_reset_confirm, name="password_reset_confirm"),
    # User management
    path("profile/", UserProfileView.as_view(), name="user_profile"),
    path("change-password/", ChangePasswordView.as_view(), name="change_password"),
    path("set-password/", set_password, name="set_password"),
    path("delete-account/", delete_account, name="delete_account"),
]
