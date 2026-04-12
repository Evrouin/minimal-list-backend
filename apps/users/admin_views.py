from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import filters, generics
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from apps.notes.models import Note
from apps.users.admin_serializers import AdminCreateUserSerializer, AdminNoteSerializer, AdminUserUpdateSerializer
from apps.users.permissions import IsSuperUser
from apps.users.serializers import UserSerializer

User = get_user_model()


class AdminPagination(PageNumberPagination):
    """Page number pagination for admin views."""

    page_size = 15
    page_size_query_param = "page_size"
    max_page_size = 100


class AdminUserListView(generics.ListCreateAPIView):
    """List and create users (superuser only)."""

    permission_classes = [IsSuperUser]
    queryset = User.objects.all().order_by("-created_at")
    pagination_class = AdminPagination
    filter_backends = [filters.SearchFilter]
    search_fields = ["email", "username"]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return AdminCreateUserSerializer
        return UserSerializer

    @extend_schema(summary="List all users", description="Admin endpoint to list all users.")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(summary="Create user", description="Admin endpoint to create a new user.")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)


class AdminUserDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Get, update, and delete any user (superuser only)."""

    permission_classes = [IsSuperUser]
    queryset = User.objects.all()
    lookup_field = "uuid"

    def get_serializer_class(self):
        if self.request.method == "PATCH":
            return AdminUserUpdateSerializer
        return UserSerializer

    @extend_schema(summary="Get user detail", description="Admin endpoint to get user detail.")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(summary="Update user", description="Admin endpoint to update a user.")
    def partial_update(self, request, *args, **kwargs):
        from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
        from rest_framework_simplejwt.tokens import RefreshToken as RT
        from apps.users.email import send_account_deactivated_email, send_account_reactivated_email

        user = self.get_object()
        is_active = request.data.get("is_active")

        if is_active is False and user.is_active:
            user.deactivation_reason = "admin"
            user.reactivation_token = ""
            user.reactivation_token_expires = None
            user.save(update_fields=["deactivation_reason", "reactivation_token", "reactivation_token_expires"])
            for session in user.sessions.all():
                try:
                    ot = OutstandingToken.objects.get(jti=session.jti)
                    RT(ot.token).blacklist()
                except Exception:
                    pass
            user.sessions.all().delete()
            send_account_deactivated_email(user, token=None, reason="admin")

        elif is_active is True and not user.is_active:
            user.deactivation_reason = ""
            user.reactivation_token = ""
            user.reactivation_token_expires = None
            user.scheduled_deletion_at = None
            user.deletion_recovery_token = ""
            user.save(update_fields=["deactivation_reason", "reactivation_token", "reactivation_token_expires", "scheduled_deletion_at", "deletion_recovery_token"])
            send_account_reactivated_email(user)

        return super().partial_update(request, *args, **kwargs)

    @extend_schema(summary="Delete user", description="Admin endpoint to permanently delete a user. Requires superuser password confirmation.")
    def destroy(self, request, *args, **kwargs):
        user = self.get_object()
        if user == request.user:
            return Response({"error": "Cannot delete yourself."}, status=400)
        password = request.data.get("password")
        if not password:
            return Response({"error": "Password is required."}, status=400)
        if not request.user.check_password(password):
            return Response({"error": "Incorrect password."}, status=400)
        return super().destroy(request, *args, **kwargs)


class AdminNoteListView(generics.ListAPIView):
    """List all notes across users (superuser only)."""

    permission_classes = [IsSuperUser]
    serializer_class = AdminNoteSerializer
    pagination_class = AdminPagination
    queryset = Note.objects.select_related("user").all().order_by("-created_at")
    filter_backends = [filters.SearchFilter]
    search_fields = ["title", "body", "user__email"]

    @extend_schema(summary="List all notes", description="Admin endpoint to list all notes.")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)


class AdminNoteDetailView(generics.RetrieveDestroyAPIView):
    """View and delete any note (superuser only)."""

    permission_classes = [IsSuperUser]
    serializer_class = AdminNoteSerializer
    queryset = Note.objects.select_related("user").all()
    lookup_field = "uuid"

    @extend_schema(summary="Get note detail", description="Admin endpoint to view a note with user info.")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(summary="Delete note", description="Admin endpoint to permanently delete a note.")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)


@extend_schema(summary="Dashboard stats", description="Admin endpoint for dashboard statistics.")
@api_view(["GET"])
@permission_classes([IsSuperUser])
def admin_stats(request):
    """Dashboard statistics."""
    now = timezone.now()
    user_stats = User.objects.aggregate(
        total=Count("id"),
        verified=Count("id", filter=Q(is_verified=True)),
        joined_today=Count("id", filter=Q(created_at__date=now.date())),
    )
    note_agg = Note.objects.aggregate(
        total=Count("id"),
        completed_count=Count("id", filter=Q(completed=True)),
        deleted_count=Count("id", filter=Q(deleted=True)),
        active_count=Count("id", filter=Q(completed=False, deleted=False)),
    )
    note_stats = {
        "total": note_agg["total"],
        "completed": note_agg["completed_count"],
        "deleted": note_agg["deleted_count"],
        "active": note_agg["active_count"],
    }
    return Response({"users": user_stats, "notes": note_stats})
