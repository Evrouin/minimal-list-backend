import ipaddress
import logging
import socket
from urllib.parse import urlparse

NO_IDS_ERROR = "No IDs provided."

import requests as http_requests
from bs4 import BeautifulSoup
from django.conf import settings
from django.db import transaction
from django.db.models import Count, Max, Q
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

from .models import Folder, Note
from .serializers import FolderSerializer, NoteSerializer

logger = logging.getLogger(__name__)


class NotePagination(CursorPagination):
    """Cursor pagination for notes."""

    page_size = 20
    ordering = "-order_id"
    cursor_query_param = "cursor"

    def get_ordering(self, request, queryset, view):
        if request.query_params.get("has_reminder") == "true":
            return ("reminder_at",)
        return super().get_ordering(request, queryset, view)


class ApiResponseMixin:
    """Mixin to wrap responses in the Nuxt ApiResponse format."""

    def api_response(self, data, status_code=200):
        return Response(
            {"data": data, "statusCode": status_code, "timestamp": timezone.now().isoformat()},
            status=status_code,
        )


@method_decorator(ratelimit(key="user", rate="60/h", method="POST"), name="dispatch")
@method_decorator(ratelimit(key="user", rate="120/h", method="GET"), name="dispatch")
class NoteListCreateView(ApiResponseMixin, generics.ListCreateAPIView):
    """List and create notes for the authenticated user."""

    permission_classes = [IsAuthenticated]
    serializer_class = NoteSerializer
    pagination_class = NotePagination

    def get_queryset(self):
        queryset = Note.objects.filter(user=self.request.user)  # type: ignore[misc]
        if self.request.query_params.get("deleted_only") == "true":
            return queryset.filter(deleted=True)
        if self.request.query_params.get("archived_only") == "true":
            folder_uuid = self.request.query_params.get("folder")
            if folder_uuid:
                return queryset.filter(is_archived=True, deleted=False, folder__uuid=folder_uuid)
            return queryset.filter(is_archived=True, deleted=False, archived_by_folder=False)
        # Default: exclude deleted and archived
        queryset = queryset.filter(deleted=False, is_archived=False)
        # Reminders folder: cross-folder view of all notes with reminder_at set
        if self.request.query_params.get("has_reminder") == "true":
            return queryset.filter(reminder_at__isnull=False).order_by("reminder_at")
        folder = self.request.query_params.get("folder")
        if folder:
            queryset = queryset.filter(folder__uuid=folder)
        completed = self.request.query_params.get("completed")
        if completed == "true":
            queryset = queryset.filter(completed=True)
        elif completed == "false":
            queryset = queryset.filter(completed=False)
        return queryset

    @extend_schema(summary="List notes", description="Get all notes for the authenticated user. Pass ?include_deleted=true to include soft-deleted notes.")
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

    MAX_NOTES_PER_USER = 100

    @extend_schema(summary="Create note", description="Create a new note for the authenticated user.")
    def create(self, request, *args, **kwargs):
        if not settings.DEBUG and Note.objects.filter(user=request.user, deleted=False).count() >= self.MAX_NOTES_PER_USER:
            return self.api_response(
                {"error": f"Note limit reached ({self.MAX_NOTES_PER_USER}). Delete some notes first."},
                status.HTTP_400_BAD_REQUEST,
            )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user)
        return self.api_response(serializer.data, status.HTTP_201_CREATED)


class NoteDetailView(ApiResponseMixin, generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, and delete a single note."""

    permission_classes = [IsAuthenticated]
    serializer_class = NoteSerializer
    lookup_field = "uuid"

    def get_queryset(self):
        return Note.objects.filter(user=self.request.user)  # type: ignore[misc]

    @extend_schema(summary="Get note", description="Get a single note by ID.")
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return self.api_response(serializer.data)

    @extend_schema(summary="Update note", description="Full update of a note.")
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return self.api_response(serializer.data)

    @extend_schema(summary="Partial update note", description="Partial update of a note (e.g., toggle completed).")
    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data.get("deleted") is False and instance.deleted:
            if instance.folder is None or instance.folder.is_archived:
                instance.folder = Folder.objects.filter(user=request.user, name="notes", is_default=True).first()
        serializer.save()
        return self.api_response(serializer.data)

    @extend_schema(summary="Delete note", description="Soft delete on first call, permanent delete if already soft-deleted.")
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.deleted:
            instance.delete()
        else:
            instance.deleted = True
            instance.pinned = False
            instance.reminder_at = None
            instance.save(update_fields=["deleted", "pinned", "reminder_at"])
        return self.api_response({"success": True})


MAX_BULK_IDS = 50


@extend_schema(summary="Bulk delete notes", description="Soft delete multiple notes by IDs.")
@api_view(["POST"])
@perm_classes([IsAuthenticated])
def bulk_delete_notes(request):
    """Soft-delete active notes, permanently delete already soft-deleted ones."""
    ids = request.data.get("ids", [])
    if not ids:
        return Response({"error": NO_IDS_ERROR}, status=status.HTTP_400_BAD_REQUEST)
    if len(ids) > MAX_BULK_IDS:
        return Response({"error": f"Maximum {MAX_BULK_IDS} IDs per request."}, status=status.HTTP_400_BAD_REQUEST)
    notes = Note.objects.filter(uuid__in=ids, user=request.user)
    permanent_ids = list(notes.filter(deleted=True).values_list("uuid", flat=True))
    notes.filter(deleted=False).update(deleted=True)
    Note.objects.filter(uuid__in=permanent_ids).delete()
    return Response({"success": True})


@extend_schema(summary="Clear all notes", description="Permanently delete all notes for the authenticated user. Requires password confirmation.")
@api_view(["POST"])
@perm_classes([IsAuthenticated])
def clear_all_notes(request):
    """Permanently delete all notes for the user. Requires password confirmation."""
    password = request.data.get("password")
    if not password:
        return Response({"error": "Password is required."}, status=status.HTTP_400_BAD_REQUEST)
    if not request.user.check_password(password):
        return Response({"error": "Incorrect password."}, status=status.HTTP_400_BAD_REQUEST)
    count, _ = Note.objects.filter(user=request.user).delete()
    return Response({"success": True, "deleted": count})


@extend_schema(summary="Empty trash", description="Permanently delete all soft-deleted notes for the authenticated user.")
@api_view(["DELETE"])
@perm_classes([IsAuthenticated])
def empty_trash(request):
    count, _ = Note.objects.filter(user=request.user, deleted=True).delete()
    return Response({"success": True, "deleted": count})


@extend_schema(summary="Reorder a note within its section", description="Move a note to a new position within the pinned or unpinned section.")
@api_view(["POST"])
@perm_classes([IsAuthenticated])
def bulk_reorder_notes(request):
    """Move a note to a new position within its pinned/unpinned section."""
    uuid = request.data.get("uuid")
    new_position = request.data.get("new_position")
    pinned = request.data.get("pinned")

    if not uuid:
        return Response({"error": "uuid is required."}, status=status.HTTP_400_BAD_REQUEST)
    if new_position is None:
        return Response({"error": "new_position is required."}, status=status.HTTP_400_BAD_REQUEST)
    if not isinstance(new_position, int) or new_position < 1:
        return Response({"error": "new_position must be a positive integer."}, status=status.HTTP_400_BAD_REQUEST)
    if pinned is None or not isinstance(pinned, bool):
        return Response({"error": "pinned (boolean) is required."}, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        all_notes = list(
            Note.objects.select_for_update()
            .filter(user=request.user, deleted=False)
            .order_by("-order_id")
        )

        pinned_notes = [n for n in all_notes if n.pinned]
        unpinned_notes = [n for n in all_notes if not n.pinned]

        section = pinned_notes if pinned else unpinned_notes

        target = None
        for n in section:
            if str(n.uuid) == uuid:
                target = n
                break

        if target is None:
            return Response({"error": "Note not found in the specified section."}, status=status.HTTP_404_NOT_FOUND)

        section.remove(target)
        insert_idx = max(0, min(new_position - 1, len(section)))
        section.insert(insert_idx, target)

        # Rebuild: pinned get highest order_ids, unpinned get the rest
        combined = pinned_notes + unpinned_notes
        total = len(combined)
        to_update = []
        for i, n in enumerate(combined):
            new_oid = total - i
            if n.order_id != new_oid:
                n.order_id = new_oid
                to_update.append(n)

        if to_update:
            Note.objects.bulk_update(to_update, ["order_id"])

    return Response({"success": True})


@extend_schema(summary="Bulk pin/unpin notes", description="Pin or unpin multiple notes by IDs.")
@api_view(["POST"])
@perm_classes([IsAuthenticated])
def bulk_pin_notes(request):
    """Bulk pin or unpin notes."""
    ids = request.data.get("ids", [])
    pinned = request.data.get("pinned", True)
    if not ids:
        return Response({"error": NO_IDS_ERROR}, status=status.HTTP_400_BAD_REQUEST)
    if len(ids) > MAX_BULK_IDS:
        return Response({"error": f"Maximum {MAX_BULK_IDS} IDs per request."}, status=status.HTTP_400_BAD_REQUEST)
    Note.objects.filter(uuid__in=ids, user=request.user).update(pinned=pinned)
    return Response({"success": True})


@extend_schema(summary="Bulk restore notes", description="Restore multiple soft-deleted notes by IDs.")
@api_view(["POST"])
@perm_classes([IsAuthenticated])
def bulk_restore_notes(request):
    """Restore soft-deleted notes, assigning new order_ids to avoid duplicates."""
    ids = request.data.get("ids", [])
    if not ids:
        return Response({"error": NO_IDS_ERROR}, status=status.HTTP_400_BAD_REQUEST)
    if len(ids) > MAX_BULK_IDS:
        return Response({"error": f"Maximum {MAX_BULK_IDS} IDs per request."}, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        max_order = (
            Note.objects.filter(user=request.user, deleted=False).aggregate(m=Max("order_id"))["m"] or 0
        )
        notes = list(
            Note.objects.select_for_update()
            .filter(uuid__in=ids, user=request.user, deleted=True)
            .order_by("order_id", "created_at")
        )
        default_folder = Folder.objects.filter(user=request.user, name="notes", is_default=True).first()
        for i, note in enumerate(notes, start=1):
            note.deleted = False
            note.order_id = max_order + i
            # If original folder was deleted (NULL) or is archived, restore to default
            if note.folder is None or note.folder.is_archived:
                note.folder = default_folder
        Note.objects.bulk_update(notes, ["deleted", "order_id", "folder"])

    return Response({"success": True})


def _is_safe_url(url):
    """Block requests to private/internal IPs (SSRF protection)."""
    try:
        hostname = urlparse(url).hostname
        if not hostname:
            return False
        ip = ipaddress.ip_address(socket.gethostbyname(hostname))
        return ip.is_global
    except (socket.gaierror, ValueError):
        return False


def _fetch_og_data(url):
    """Fetch Open Graph metadata from a URL."""
    try:
        resp = http_requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
    except http_requests.RequestException:
        return None

    soup = BeautifulSoup(resp.text[:50_000], "html.parser")

    def og(prop):
        tag = soup.find("meta", attrs={"property": f"og:{prop}"}) or soup.find(
            "meta", attrs={"name": prop}
        )
        return tag["content"].strip() if tag and tag.get("content") else None

    title = og("title") or (soup.title.string.strip() if soup.title and soup.title.string else None)
    if not title:
        return None

    return {
        "url": url,
        "title": title,
        "description": og("description") or "",
        "image": og("image") or "",
        "domain": urlparse(url).netloc,
    }


@extend_schema(
    summary="Fetch link preview",
    description="Fetch Open Graph metadata for a URL to generate a link preview card.",
)
@api_view(["POST"])
@perm_classes([IsAuthenticated])
@ratelimit(key="user", rate="30/h", method="POST")
def link_preview(request):
    """Fetch OG metadata for a single URL."""
    url = request.data.get("url", "").strip()
    if not url:
        return Response({"error": "URL is required."}, status=status.HTTP_400_BAD_REQUEST)

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return Response({"error": "Invalid URL."}, status=status.HTTP_400_BAD_REQUEST)

    if not _is_safe_url(url):
        return Response({"error": "Invalid URL."}, status=status.HTTP_400_BAD_REQUEST)

    data = _fetch_og_data(url)
    if not data:
        return Response({"error": "Could not fetch preview."}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

    return Response(data)


# ---------------------------------------------------------------------------
# Note archive / unarchive
# ---------------------------------------------------------------------------

@extend_schema(summary="Archive a note")
@api_view(["POST"])
@perm_classes([IsAuthenticated])
def archive_note(request, uuid):
    note = Note.objects.filter(user=request.user, uuid=uuid, deleted=False).first()
    if not note:
        return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
    note.is_archived = True
    note.pinned = False
    if note.reminder_at:
        note.reminder_at = None
    note.save(update_fields=["is_archived", "pinned", "reminder_at"])
    return Response({"success": True})


@extend_schema(summary="Unarchive a note")
@api_view(["POST"])
@perm_classes([IsAuthenticated])
def unarchive_note(request, uuid):
    note = Note.objects.filter(user=request.user, uuid=uuid, deleted=False).first()
    if not note:
        return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
    note.is_archived = False
    note.save(update_fields=["is_archived"])
    return Response({"success": True})


@extend_schema(summary="Bulk archive/unarchive notes")
@api_view(["POST"])
@perm_classes([IsAuthenticated])
def bulk_archive_notes(request):
    ids = request.data.get("ids", [])
    archive = request.data.get("archived", True)
    if not ids:
        return Response({"error": NO_IDS_ERROR}, status=status.HTTP_400_BAD_REQUEST)
    if len(ids) > MAX_BULK_IDS:
        return Response({"error": f"Maximum {MAX_BULK_IDS} IDs per request."}, status=status.HTTP_400_BAD_REQUEST)
    update = {"is_archived": archive}
    if archive:
        update["pinned"] = False
    Note.objects.filter(user=request.user, uuid__in=ids, deleted=False).update(**update)
    return Response({"success": True})


# ---------------------------------------------------------------------------
# Folder CRUD + archive/unarchive
# ---------------------------------------------------------------------------

MAX_CUSTOM_FOLDERS = 20


class FolderListCreateView(ApiResponseMixin, generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = FolderSerializer

    def get_queryset(self):
        archived = self.request.query_params.get("archived") == "true"
        note_filter = Q(notes__deleted=False, notes__is_archived=True) if archived else Q(notes__deleted=False, notes__is_archived=False)
        return (
            Folder.objects.filter(user=self.request.user, is_archived=archived)
            .annotate(active_note_count=Count("notes", filter=note_filter))
        )

    @extend_schema(summary="List folders")
    def list(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return self.api_response(serializer.data)

    @extend_schema(summary="Create folder")
    def create(self, request, *args, **kwargs):
        custom_count = Folder.objects.filter(user=request.user, is_default=False).count()
        if custom_count >= MAX_CUSTOM_FOLDERS:
            return self.api_response({"error": f"Maximum {MAX_CUSTOM_FOLDERS} custom folders allowed."}, status.HTTP_400_BAD_REQUEST)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user)
        return self.api_response(serializer.data, status.HTTP_201_CREATED)


class FolderDetailView(ApiResponseMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = FolderSerializer
    lookup_field = "uuid"

    def get_queryset(self):
        return (
            Folder.objects.filter(user=self.request.user)
            .annotate(active_note_count=Count("notes", filter=Q(notes__deleted=False, notes__is_archived=False)))
        )

    @extend_schema(summary="Get folder")
    def retrieve(self, request, *args, **kwargs):
        return self.api_response(self.get_serializer(self.get_object()).data)

    @extend_schema(summary="Update folder")
    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.is_default:
            return self.api_response({"error": "Default folders cannot be modified."}, status.HTTP_400_BAD_REQUEST)
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return self.api_response(serializer.data)

    @extend_schema(summary="Delete folder", description="Deletes folder and moves its notes to the user's default 'notes' folder.")
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.is_default:
            return self.api_response({"error": "Default folders cannot be deleted."}, status.HTTP_400_BAD_REQUEST)
        default_folder = Folder.objects.filter(user=request.user, name="notes", is_default=True).first()
        # Move all notes (including archived ones) to default folder and unarchive them
        instance.notes.filter(deleted=False).update(folder=default_folder, is_archived=False, archived_by_folder=False)
        instance.delete()
        return self.api_response({"success": True})


@extend_schema(summary="Archive a folder")
@api_view(["POST"])
@perm_classes([IsAuthenticated])
def archive_folder(request, uuid):
    folder = Folder.objects.filter(user=request.user, uuid=uuid, is_default=False).first()
    if not folder:
        return Response({"error": "Not found or cannot archive default folders."}, status=status.HTTP_404_NOT_FOUND)
    folder.is_archived = True
    folder.save(update_fields=["is_archived"])
    # Mark notes as archived_by_folder only if not already individually archived
    folder.notes.filter(deleted=False, is_archived=False).update(
        is_archived=True, pinned=False, reminder_at=None, archived_by_folder=True
    )
    return Response({"success": True})


@extend_schema(summary="Unarchive a folder")
@api_view(["POST"])
@perm_classes([IsAuthenticated])
def unarchive_folder(request, uuid):
    folder = Folder.objects.filter(user=request.user, uuid=uuid).first()
    if not folder:
        return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
    folder.is_archived = False
    folder.save(update_fields=["is_archived"])
    folder.notes.filter(deleted=False, archived_by_folder=True).update(is_archived=False, archived_by_folder=False)
    folder = Folder.objects.annotate(active_note_count=Count("notes", filter=Q(notes__deleted=False, notes__is_archived=False))).get(pk=folder.pk)
    return Response(FolderSerializer(folder).data)


@extend_schema(summary="Snooze a reminder")
@api_view(["POST"])
@perm_classes([IsAuthenticated])
def snooze_note(request, uuid):
    note = Note.objects.filter(user=request.user, uuid=uuid, deleted=False).first()
    if not note:
        return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
    snoozed_until = request.data.get("snoozed_until")
    if not snoozed_until:
        return Response({"error": "snoozed_until is required."}, status=status.HTTP_400_BAD_REQUEST)
    note.snoozed_until = snoozed_until
    note.save(update_fields=["snoozed_until"])
    return Response({"success": True})
@api_view(["POST"])
@perm_classes([IsAuthenticated])
def reorder_folders(request):
    """Accepts [{uuid, order}] list and updates order for custom folders only."""
    items = request.data.get("folders", [])
    if not items:
        return Response({"error": "No folders provided."}, status=status.HTTP_400_BAD_REQUEST)
    uuids = [item["uuid"] for item in items if "uuid" in item and "order" in item]
    folders = {str(f.uuid): f for f in Folder.objects.filter(user=request.user, uuid__in=uuids, is_default=False)}
    for item in items:
        folder = folders.get(str(item.get("uuid")))
        if folder:
            folder.order = item["order"]
    Folder.objects.bulk_update(list(folders.values()), ["order"])
    return Response({"success": True})
