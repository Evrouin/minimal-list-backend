from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    ChangePasswordView,
    CustomTokenObtainPairView,
    RegisterView,
    UserProfileView,
    delete_account,
    google_login,
    password_reset_confirm,
    password_reset_request,
    verify_email,
)

urlpatterns = [
    # Authentication
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", CustomTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    # Email verification
    path("verify-email/<str:token>/", verify_email, name="verify_email"),
    # Password reset
    path("password-reset/", password_reset_request, name="password_reset_request"),
    path("password-reset/confirm/", password_reset_confirm, name="password_reset_confirm"),
    # User management
    path("profile/", UserProfileView.as_view(), name="user_profile"),
    path("change-password/", ChangePasswordView.as_view(), name="change_password"),
    path("delete-account/", delete_account, name="delete_account"),
]
