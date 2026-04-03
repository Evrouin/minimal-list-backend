from datetime import timedelta

from decouple import config  # type: ignore[import-untyped]
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail

from .email import send_template_email
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from google.auth.transport import requests  # type: ignore[import-untyped]
from google.oauth2 import id_token  # type: ignore[import-untyped]
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import PasswordResetToken
from .serializers import (
    ChangePasswordSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    SetPasswordSerializer,
    UserSerializer,
)

User = get_user_model()


@method_decorator(ratelimit(key="ip", rate="5/h", method="POST"), name="dispatch")
class RegisterView(generics.CreateAPIView):
    """User registration endpoint with rate limiting."""

    queryset = User.objects.all()
    permission_classes = [AllowAny]
    serializer_class = RegisterSerializer

    @extend_schema(
        summary="Register a new user",
        description="Create a new user account. Sends verification email upon successful registration.",
        responses={201: UserSerializer},
    )
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # Send verification email
        verification_url = f"{settings.FRONTEND_URL}/auth/verify-email/{user.verification_token}"
        send_template_email(
            subject="minimal list - verify your email",
            template_name="verify-email",
            context={"verification_url": verification_url},
            to_email=user.email,
        )

        return Response(
            {
                "message": "Registration successful. Please check your email to verify your account.",
                "user": UserSerializer(user).data,
            },
            status=status.HTTP_201_CREATED,
        )


@method_decorator(ratelimit(key="ip", rate="10/h", method="POST"), name="dispatch")
class CustomTokenObtainPairView(TokenObtainPairView):
    """Login endpoint with rate limiting and account lockout."""

    MAX_FAILED_ATTEMPTS = 5

    @extend_schema(
        summary="Login and obtain JWT tokens",
        description="Authenticate with email and password to receive access and refresh tokens.",
    )
    def post(self, request, *args, **kwargs):
        email = request.data.get("email", "")
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                {"error": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED
            )

        if user.locked_until and user.locked_until > timezone.now():
            return Response(
                {"error": "Account locked due to too many failed attempts. Check your email to unlock."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not user.is_verified:
            return Response(
                {"error": "Please verify your email before logging in."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            response = super().post(request, *args, **kwargs)
        except Exception:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= self.MAX_FAILED_ATTEMPTS:
                user.locked_until = timezone.now() + timedelta(hours=1)
                user.failed_login_attempts = 0
                user.verification_token = get_random_string(64)
                user.save()
                send_template_email(
                    subject="minimal list - account locked",
                    template_name="account-locked",
                    context={"unlock_url": f"{settings.FRONTEND_URL}/auth/unlock-account/{user.verification_token}"},
                    to_email=user.email,
                )
                return Response(
                    {"error": "Account locked due to too many failed attempts. Check your email to unlock."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            user.save()
            return Response(
                {"error": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED
            )

        user.failed_login_attempts = 0
        user.locked_until = None
        user.save()
        return response


class UserProfileView(generics.RetrieveUpdateAPIView):
    """Get and update user profile."""

    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer

    @extend_schema(
        summary="Get user profile",
        description="Retrieve the authenticated user's profile information.",
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary="Update user profile",
        description="Update the authenticated user's profile information.",
    )
    def patch(self, request, *args, **kwargs):
        return super().patch(request, *args, **kwargs)

    def get_object(self):
        return self.request.user


@method_decorator(ratelimit(key="user", rate="5/h", method="POST"), name="dispatch")
class ChangePasswordView(generics.UpdateAPIView):
    """Change user password with rate limiting."""

    permission_classes = [IsAuthenticated]
    serializer_class = ChangePasswordSerializer

    @extend_schema(
        summary="Change password",
        description="Change the authenticated user's password.",
    )
    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        if not user.check_password(serializer.validated_data["old_password"]):
            return Response({"old_password": "Wrong password."}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(serializer.validated_data["new_password"])
        user.save()

        # Blacklist all outstanding refresh tokens
        OutstandingToken.objects.filter(user=user).delete()

        # Issue new tokens
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "message": "Password updated successfully.",
                "tokens": {
                    "refresh": str(refresh),
                    "access": str(refresh.access_token),  # type: ignore[attr-defined]
                },
            },
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="Verify email address",
    description="Verify user's email address using the token sent during registration.",
    parameters=[
        OpenApiParameter(name="token", type=OpenApiTypes.STR, location=OpenApiParameter.PATH)
    ],
)
@api_view(["POST"])
@permission_classes([AllowAny])
@ratelimit(key="ip", rate="3/h", method="POST")
def verify_email(request, token):
    """Verify user email with token."""
    from datetime import timedelta

    from django.utils import timezone

    try:
        user = User.objects.get(verification_token=token)
        if user.is_verified:
            return Response({"message": "Email already verified."}, status=status.HTTP_200_OK)

        if timezone.now() - user.created_at > timedelta(hours=24):
            return Response(
                {"error": "Verification token has expired. Please register again."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.is_verified = True
        user.verification_token = ""
        user.save(update_fields=["is_verified", "verification_token"])

        return Response({"message": "Email verified successfully."}, status=status.HTTP_200_OK)
    except User.DoesNotExist:
        return Response(
            {"error": "Invalid verification token."}, status=status.HTTP_400_BAD_REQUEST
        )


@extend_schema(summary="Unlock account", description="Unlock a locked account using the token sent via email.")
@api_view(["POST"])
@permission_classes([AllowAny])
@ratelimit(key="ip", rate="5/h", method="POST")
def unlock_account(request, token):
    """Unlock a locked account."""
    try:
        user = User.objects.get(verification_token=token)
        user.locked_until = None
        user.failed_login_attempts = 0
        user.verification_token = ""
        user.save(update_fields=["locked_until", "failed_login_attempts", "verification_token"])
        return Response({"message": "Account unlocked successfully."})
    except User.DoesNotExist:
        return Response({"error": "Invalid token."}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    summary="Request password reset",
    description="Request a password reset link. An email will be sent if the email exists.",
    request=PasswordResetRequestSerializer,
)
@api_view(["POST"])
@permission_classes([AllowAny])
@ratelimit(key="ip", rate="3/h", method="POST")
def password_reset_request(request):
    """Request password reset - send email with token."""
    serializer = PasswordResetRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    try:
        user = User.objects.get(email=serializer.validated_data["email"])
        reset_token = PasswordResetToken.create_token(user)

        # Send password reset email
        reset_url = f"{settings.FRONTEND_URL}/auth/reset-password/{reset_token.token}"
        send_template_email(
            subject="minimal list - password reset",
            template_name="password-reset",
            context={"reset_url": reset_url},
            to_email=user.email,
        )
    except User.DoesNotExist:
        pass  # Don't reveal if email exists

    return Response(
        {"message": "If the email exists, a password reset link has been sent."},
        status=status.HTTP_200_OK,
    )


@extend_schema(
    summary="Confirm password reset",
    description="Reset password using the token received via email.",
    request=PasswordResetConfirmSerializer,
)
@api_view(["POST"])
@permission_classes([AllowAny])
@ratelimit(key="ip", rate="5/h", method="POST")
def password_reset_confirm(request):
    """Confirm password reset with token."""
    serializer = PasswordResetConfirmSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    try:
        reset_token = PasswordResetToken.objects.get(token=serializer.validated_data["token"])

        if not reset_token.is_valid():
            return Response(
                {"error": "Token is invalid or expired."}, status=status.HTTP_400_BAD_REQUEST
            )

        user = reset_token.user
        user.set_password(serializer.validated_data["new_password"])
        user.save()

        reset_token.is_used = True
        reset_token.save()

        return Response({"message": "Password reset successfully."}, status=status.HTTP_200_OK)
    except PasswordResetToken.DoesNotExist:
        return Response({"error": "Invalid token."}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    summary="Set or change password",
    description="Set password for OAuth users (no current password) or change password for existing users.",
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@ratelimit(key="user", rate="5/h", method="POST")
def set_password(request):
    """Set or change password."""
    serializer = SetPasswordSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    user = request.user
    had_password = user.has_usable_password()
    if had_password:
        current = serializer.validated_data.get("current_password")
        if not current or not user.check_password(current):
            return Response({"current_password": "Wrong password."}, status=status.HTTP_400_BAD_REQUEST)

    user.set_password(serializer.validated_data["new_password"])
    user.save()

    OutstandingToken.objects.filter(user=user).delete()
    refresh = RefreshToken.for_user(user)

    msg = "Password changed successfully." if had_password else "Password set successfully."
    return Response(
        {
            "message": msg,
            "tokens": {
                "refresh": str(refresh),
                "access": str(refresh.access_token),  # type: ignore[attr-defined]
            },
        },
        status=status.HTTP_200_OK,
    )


@extend_schema(
    summary="Logout",
    description="Blacklist the refresh token to log out.",
)
@api_view(["POST"])
@permission_classes([AllowAny])
def logout(request):
    """Blacklist refresh token."""
    refresh_token = request.data.get("refresh")
    if not refresh_token:
        return Response({"error": "Refresh token is required."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        RefreshToken(refresh_token).blacklist()
        return Response({"message": "Logged out successfully."}, status=status.HTTP_200_OK)
    except Exception:
        return Response({"error": "Invalid token."}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    summary="Delete user account",
    description="Permanently delete the authenticated user's account.",
)
@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_account(request):
    """Delete user account."""
    user = request.user
    user.delete()
    return Response({"message": "Account deleted successfully."}, status=status.HTTP_204_NO_CONTENT)


@extend_schema(
    summary="Google OAuth login",
    description="Authenticate user with Google ID token. Returns JWT tokens.",
    request={
        "application/json": {
            "type": "object",
            "properties": {"token": {"type": "string", "description": "Google ID token"}},
            "required": ["token"],
        }
    },
)
@api_view(["POST"])
@permission_classes([AllowAny])
@ratelimit(key="ip", rate="10/h", method="POST")
def google_login(request):
    """Authenticate with Google OAuth."""
    token = request.data.get("token")
    if not token:
        return Response({"error": "Token is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        try:
            client_id = config("GOOGLE_CLIENT_ID")
            idinfo = id_token.verify_oauth2_token(token, requests.Request(), client_id)
        except ValueError:
            import requests as http_requests

            resp = http_requests.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {token}"},
            )
            idinfo = resp.json()

        # Get user info from Google
        email = idinfo.get("email")
        if not email:
            return Response(
                {"error": "Email not provided by Google"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Get or create user
        User = get_user_model()
        base_username = email.split("@")[0]
        username = base_username
        if User.objects.filter(username=username).exists():
            username = f"user{get_random_string(10, '0123456789')}"
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "username": username,
                "first_name": idinfo.get("given_name", ""),
                "last_name": idinfo.get("family_name", ""),
                "avatar_url": idinfo.get("picture", ""),
                "is_verified": True,  # Google emails are verified
            },
        )

        if created:
            user.set_unusable_password()
            user.save(update_fields=["password"])

        if not created:
            updated_fields = []
            avatar_url = idinfo.get("picture", "")
            if avatar_url and user.avatar_url != avatar_url:
                user.avatar_url = avatar_url
                updated_fields.append("avatar_url")
            if not user.is_verified:
                user.is_verified = True
                user.verification_token = ""
                updated_fields.extend(["is_verified", "verification_token"])
            if updated_fields:
                user.save(update_fields=updated_fields)

        if not user.is_active:
            return Response(
                {"error": "This account has been deactivated."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "message": "Login successful" if not created else "Account created",
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "is_superuser": user.is_superuser,
                    "avatar_url": user.avatar_url,
                },
                "tokens": {
                    "refresh": str(refresh),
                    "access": str(refresh.access_token),  # type: ignore[attr-defined]
                },
            },
            status=status.HTTP_200_OK,
        )

    except ValueError as e:
        return Response({"error": f"Invalid token: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
