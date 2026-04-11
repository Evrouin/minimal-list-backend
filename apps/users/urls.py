from django.utils.decorators import method_decorator
from django.urls import path
from django.utils import timezone
from django_ratelimit.decorators import ratelimit
from rest_framework import status
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView


@method_decorator(ratelimit(key="ip", rate="30/h", method="POST"), name="dispatch")
class RateLimitedTokenRefreshView(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        try:
            old_token = request.data.get("refresh")
            old_jti = None
            if old_token:
                try:
                    old_jti = RefreshToken(old_token)["jti"]
                except Exception:
                    pass

            response = super().post(request, *args, **kwargs)

            if old_jti and response.status_code == 200:
                try:
                    from apps.users.models import UserSession
                    new_jti = RefreshToken(response.data["refresh"])["jti"]
                    UserSession.objects.filter(jti=old_jti).update(jti=new_jti, last_active_at=timezone.now())
                except Exception:
                    pass

            return response
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
    deactivate_account,
    delete_account,
    google_login,
    list_sessions,
    logout,
    password_reset_confirm,
    password_reset_request,
    reactivate_account,
    recover_account,
    resend_verification,
    revoke_other_sessions,
    revoke_session,
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
    path("recover-account/<str:token>/", recover_account, name="recover_account"),
    path("deactivate/", deactivate_account, name="deactivate_account"),
    path("reactivate/<str:token>/", reactivate_account, name="reactivate_account"),
    # Sessions
    path("sessions/", list_sessions, name="list_sessions"),
    path("sessions/<int:session_id>/", revoke_session, name="revoke_session"),
    path("sessions/revoke-others/", revoke_other_sessions, name="revoke_other_sessions"),
]
