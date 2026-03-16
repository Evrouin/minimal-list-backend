from decouple import config  # type: ignore[import-untyped]
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
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
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import PasswordResetToken
from .serializers import (
    ChangePasswordSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
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
        response = super().create(request, *args, **kwargs)
        user = User.objects.get(email=response.data["email"])

        # Send verification email
        verification_url = f"{settings.FRONTEND_URL}/verify-email/{user.verification_token}"
        send_mail(
            "Verify your email",
            f"Click the link to verify your email: {verification_url}",
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=True,
        )

        return Response(
            {
                "message": "Registration successful. Please check your email to verify your account.",
                "user": response.data,
            },
            status=status.HTTP_201_CREATED,
        )


@method_decorator(ratelimit(key="ip", rate="10/h", method="POST"), name="dispatch")
class CustomTokenObtainPairView(TokenObtainPairView):
    """Login endpoint with rate limiting."""

    @extend_schema(
        summary="Login and obtain JWT tokens",
        description="Authenticate with email and password to receive access and refresh tokens.",
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


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

        return Response({"message": "Password updated successfully."}, status=status.HTTP_200_OK)


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
    try:
        user = User.objects.get(verification_token=token)
        if user.is_verified:
            return Response({"message": "Email already verified."}, status=status.HTTP_200_OK)

        user.is_verified = True
        user.verification_token = None  # type: ignore[assignment]
        user.save()

        return Response({"message": "Email verified successfully."}, status=status.HTTP_200_OK)
    except User.DoesNotExist:
        return Response(
            {"error": "Invalid verification token."}, status=status.HTTP_400_BAD_REQUEST
        )


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
        reset_url = f"{settings.FRONTEND_URL}/reset-password/{reset_token.token}"
        send_mail(
            "Password Reset Request",
            f"Click the link to reset your password: {reset_url}\nThis link expires in 24 hours.",
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=True,
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
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "first_name": idinfo.get("given_name", ""),
                "last_name": idinfo.get("family_name", ""),
                "is_verified": True,  # Google emails are verified
            },
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
