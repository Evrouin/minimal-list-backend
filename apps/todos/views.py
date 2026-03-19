from django.conf import settings
from django.utils import timezone
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes as perm_classes
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Todo
from .serializers import TodoSerializer


class TodoPagination(CursorPagination):
    """Cursor pagination for todos."""

    page_size = 20
    ordering = "-created_at"
    cursor_query_param = "cursor"


class ApiResponseMixin:
    """Mixin to wrap responses in the Nuxt ApiResponse format."""

    def api_response(self, data, status_code=200):
        return Response(
            {"data": data, "statusCode": status_code, "timestamp": timezone.now().isoformat()},
            status=status_code,
        )


@method_decorator(ratelimit(key="user", rate="60/h", method="POST"), name="dispatch")
class TodoListCreateView(ApiResponseMixin, generics.ListCreateAPIView):
    """List and create todos for the authenticated user."""

    permission_classes = [IsAuthenticated]
    serializer_class = TodoSerializer
    pagination_class = TodoPagination

    def get_queryset(self):
        queryset = Todo.objects.filter(user=self.request.user)  # type: ignore[misc]
        if self.request.query_params.get("deleted_only") == "true":
            queryset = queryset.filter(deleted=True)
        elif self.request.query_params.get("include_deleted") != "true":
            queryset = queryset.filter(deleted=False)
        completed = self.request.query_params.get("completed")
        if completed == "true":
            queryset = queryset.filter(completed=True)
        elif completed == "false":
            queryset = queryset.filter(completed=False)
        return queryset

    @extend_schema(summary="List todos", description="Get all todos for the authenticated user. Pass ?include_deleted=true to include soft-deleted todos.")
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        paginated = self.get_paginated_response(serializer.data)
        return Response(
            {
                "data": serializer.data,
                "next": paginated.data.get("next"),
                "previous": paginated.data.get("previous"),
                "statusCode": 200,
                "timestamp": timezone.now().isoformat(),
            },
        )

    MAX_TODOS_PER_USER = 100

    @extend_schema(summary="Create todo", description="Create a new todo for the authenticated user.")
    def create(self, request, *args, **kwargs):
        if not settings.DEBUG and Todo.objects.filter(user=request.user, deleted=False).count() >= self.MAX_TODOS_PER_USER:
            return self.api_response(
                {"error": f"Todo limit reached ({self.MAX_TODOS_PER_USER}). Delete some todos first."},
                status.HTTP_400_BAD_REQUEST,
            )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user)
        return self.api_response(serializer.data, status.HTTP_201_CREATED)


class TodoDetailView(ApiResponseMixin, generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, and delete a single todo."""

    permission_classes = [IsAuthenticated]
    serializer_class = TodoSerializer

    def get_queryset(self):
        return Todo.objects.filter(user=self.request.user)  # type: ignore[misc]

    @extend_schema(summary="Get todo", description="Get a single todo by ID.")
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return self.api_response(serializer.data)

    @extend_schema(summary="Update todo", description="Full update of a todo.")
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return self.api_response(serializer.data)

    @extend_schema(summary="Partial update todo", description="Partial update of a todo (e.g., toggle completed).")
    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return self.api_response(serializer.data)

    @extend_schema(summary="Delete todo", description="Soft delete on first call, permanent delete if already soft-deleted.")
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.deleted:
            instance.delete()
        else:
            instance.deleted = True
            instance.save()
        return self.api_response({"success": True})


@extend_schema(summary="Bulk delete todos", description="Soft delete multiple todos by IDs.")
@api_view(["POST"])
@perm_classes([IsAuthenticated])
def bulk_delete_todos(request):
    """Bulk delete todos. Soft-deletes active todos, permanently deletes already soft-deleted ones."""
    ids = request.data.get("ids", [])
    if not ids:
        return Response({"error": "No IDs provided."}, status=status.HTTP_400_BAD_REQUEST)
    todos = Todo.objects.filter(id__in=ids, user=request.user)
    permanent_ids = list(todos.filter(deleted=True).values_list("id", flat=True))
    todos.filter(deleted=False).update(deleted=True)
    Todo.objects.filter(id__in=permanent_ids).delete()
    return Response({"success": True})


@extend_schema(summary="Bulk pin/unpin todos", description="Pin or unpin multiple todos by IDs.")
@api_view(["POST"])
@perm_classes([IsAuthenticated])
def bulk_pin_todos(request):
    """Bulk pin or unpin todos."""
    ids = request.data.get("ids", [])
    pinned = request.data.get("pinned", True)
    if not ids:
        return Response({"error": "No IDs provided."}, status=status.HTTP_400_BAD_REQUEST)
    Todo.objects.filter(id__in=ids, user=request.user).update(pinned=pinned)
    return Response({"success": True})


@extend_schema(summary="Bulk restore todos", description="Restore multiple soft-deleted todos by IDs.")
@api_view(["POST"])
@perm_classes([IsAuthenticated])
def bulk_restore_todos(request):
    """Bulk restore soft-deleted todos."""
    ids = request.data.get("ids", [])
    if not ids:
        return Response({"error": "No IDs provided."}, status=status.HTTP_400_BAD_REQUEST)
    Todo.objects.filter(id__in=ids, user=request.user, deleted=True).update(deleted=False)
    return Response({"success": True})
