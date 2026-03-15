from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
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


class TodoListCreateView(ApiResponseMixin, generics.ListCreateAPIView):
    """List and create todos for the authenticated user."""

    permission_classes = [IsAuthenticated]
    serializer_class = TodoSerializer
    pagination_class = TodoPagination

    def get_queryset(self):
        queryset = Todo.objects.filter(user=self.request.user)
        if self.request.query_params.get("include_deleted") != "true":
            queryset = queryset.filter(deleted=False)
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

    @extend_schema(summary="Create todo", description="Create a new todo for the authenticated user.")
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user)
        return self.api_response(serializer.data, status.HTTP_201_CREATED)


class TodoDetailView(ApiResponseMixin, generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, and delete a single todo."""

    permission_classes = [IsAuthenticated]
    serializer_class = TodoSerializer

    def get_queryset(self):
        return Todo.objects.filter(user=self.request.user)

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
