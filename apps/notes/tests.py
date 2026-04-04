import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from django.test.utils import override_settings
from rest_framework import status
from rest_framework.test import APIClient
from PIL import Image as PilImage

from .models import Note

User = get_user_model()


def make_test_image(*, color: tuple[int, int, int], name: str) -> SimpleUploadedFile:
    """Create an in-memory image suitable for upload tests."""

    image = PilImage.new("RGB", (64, 64), color=color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return SimpleUploadedFile(name=name, content=buffer.read(), content_type="image/png")


@pytest.fixture
def api_client():
    """API client fixture."""
    return APIClient()


@pytest.fixture
def create_user(db):
    """Create a test user."""

    def make_user(**kwargs):
        return User.objects.create_user(
            email=kwargs.get("email", "user@example.com"),
            username=kwargs.get("username", "testuser"),
            password=kwargs.get("password", "SecurePass123!"),
        )

    return make_user


@pytest.fixture
def auth_client(api_client, create_user):
    """Authenticated API client."""
    user = create_user()
    api_client.force_authenticate(user=user)
    return api_client, user


@pytest.fixture
def create_note(db):
    """Create a test note."""
    from django.db.models import Max

    def make_note(user, **kwargs):
        order_id = kwargs.get("order_id")
        if order_id is None:
            max_order = Note.objects.filter(user=user, deleted=False).aggregate(max_order=Max("order_id"))["max_order"]
            order_id = (max_order or 0) + 1

        return Note.objects.create(
            user=user,
            title=kwargs.get("title", "Test note"),
            body=kwargs.get("body", "Test body"),
            completed=kwargs.get("completed", False),
            deleted=kwargs.get("deleted", False),
            order_id=order_id,
        )

    return make_note


@pytest.mark.django_db
class TestNoteList:
    """Test note list endpoint."""

    def test_list_notes(self, auth_client, create_note):
        """Test listing notes for authenticated user."""
        client, user = auth_client
        create_note(user, title="Note 1")
        create_note(user, title="Note 2")
        response = client.get("/api/notes/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["data"]) == 2

    def test_list_excludes_deleted(self, auth_client, create_note):
        """Test that soft-deleted notes are excluded by default."""
        client, user = auth_client
        create_note(user, title="Active")
        create_note(user, title="Deleted", deleted=True)
        response = client.get("/api/notes/")
        assert len(response.data["data"]) == 1
        assert response.data["data"][0]["title"] == "Active"

    def test_list_include_deleted(self, auth_client, create_note):
        """Test including soft-deleted notes with query param."""
        client, user = auth_client
        create_note(user, title="Active")
        create_note(user, title="Deleted", deleted=True)
        response = client.get("/api/notes/?include_deleted=true")
        assert len(response.data["data"]) == 2

    def test_list_only_own_notes(self, api_client, create_user, create_note):
        """Test that users only see their own notes."""
        user1 = create_user(email="user1@example.com", username="user1")
        user2 = create_user(email="user2@example.com", username="user2")
        create_note(user1, title="User1 note")
        create_note(user2, title="User2 note")
        api_client.force_authenticate(user=user1)
        response = api_client.get("/api/notes/")
        assert len(response.data["data"]) == 1
        assert response.data["data"][0]["title"] == "User1 note"

    def test_list_unauthenticated(self, api_client):
        """Test that unauthenticated users cannot list notes."""
        response = api_client.get("/api/notes/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_bulk_reorder_notes_move_down(self, auth_client, create_note):
        """Test reorder moves an unpinned note to a lower position (higher position number)."""
        client, user = auth_client
        # Create notes: display order is -order_id, so order_id=4 shows first
        n1 = create_note(user, title="A", order_id=4)  # display pos 1
        n2 = create_note(user, title="B", order_id=3)  # display pos 2
        n3 = create_note(user, title="C", order_id=2)  # display pos 3
        n4 = create_note(user, title="D", order_id=1)  # display pos 4

        # Move A (pos 1) to pos 3 → expected: B, C, A, D
        response = client.post(
            "/api/notes/bulk-reorder/",
            {"uuid": str(n1.uuid), "new_position": 3, "pinned": False},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK

        n1.refresh_from_db()
        n2.refresh_from_db()
        n3.refresh_from_db()
        n4.refresh_from_db()
        assert n2.order_id > n3.order_id > n1.order_id > n4.order_id

    def test_bulk_reorder_notes_move_up(self, auth_client, create_note):
        """Test reorder moves an unpinned note to a higher position (lower position number)."""
        client, user = auth_client
        n1 = create_note(user, title="A", order_id=4)  # display pos 1
        n2 = create_note(user, title="B", order_id=3)  # display pos 2
        n3 = create_note(user, title="C", order_id=2)  # display pos 3
        n4 = create_note(user, title="D", order_id=1)  # display pos 4

        # Move C (pos 3) to pos 1 → expected: C, A, B, D
        response = client.post(
            "/api/notes/bulk-reorder/",
            {"uuid": str(n3.uuid), "new_position": 1, "pinned": False},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK

        n1.refresh_from_db()
        n2.refresh_from_db()
        n3.refresh_from_db()
        n4.refresh_from_db()
        assert n3.order_id > n1.order_id > n2.order_id > n4.order_id

    def test_bulk_reorder_notes_move_to_last(self, auth_client, create_note):
        """Test reorder moves a note to the last position."""
        client, user = auth_client
        n1 = create_note(user, title="A", order_id=4)
        n2 = create_note(user, title="B", order_id=3)
        n3 = create_note(user, title="C", order_id=2)
        n4 = create_note(user, title="D", order_id=1)

        # Move A (pos 1) to pos 4 → expected: B, C, D, A
        response = client.post(
            "/api/notes/bulk-reorder/",
            {"uuid": str(n1.uuid), "new_position": 4, "pinned": False},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK

        n1.refresh_from_db()
        n2.refresh_from_db()
        n3.refresh_from_db()
        n4.refresh_from_db()
        assert n2.order_id > n3.order_id > n4.order_id > n1.order_id

    def test_bulk_reorder_notes_same_position(self, auth_client, create_note):
        """Test reorder to same position is a no-op."""
        client, user = auth_client
        n1 = create_note(user, title="A", order_id=3)
        n2 = create_note(user, title="B", order_id=2)
        n3 = create_note(user, title="C", order_id=1)

        old_ids = {n.uuid: n.order_id for n in [n1, n2, n3]}

        response = client.post(
            "/api/notes/bulk-reorder/",
            {"uuid": str(n2.uuid), "new_position": 2, "pinned": False},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK

        for n in [n1, n2, n3]:
            n.refresh_from_db()
            assert n.order_id == old_ids[n.uuid]

    def test_bulk_reorder_pinned_section(self, auth_client, create_note):
        """Test reorder within pinned section doesn't affect unpinned notes."""
        client, user = auth_client
        # Pinned notes get highest order_ids
        p1 = create_note(user, title="P1", order_id=6)
        p1.pinned = True
        p1.save()
        p2 = create_note(user, title="P2", order_id=5)
        p2.pinned = True
        p2.save()
        p3 = create_note(user, title="P3", order_id=4)
        p3.pinned = True
        p3.save()
        # Unpinned
        u1 = create_note(user, title="U1", order_id=3)
        u2 = create_note(user, title="U2", order_id=2)
        u3 = create_note(user, title="U3", order_id=1)

        # Move P1 (pinned pos 1) to pinned pos 3 → P2, P3, P1
        response = client.post(
            "/api/notes/bulk-reorder/",
            {"uuid": str(p1.uuid), "new_position": 3, "pinned": True},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK

        for n in [p1, p2, p3, u1, u2, u3]:
            n.refresh_from_db()

        # Pinned order: P2 > P3 > P1
        assert p2.order_id > p3.order_id > p1.order_id
        # All pinned still above all unpinned
        assert min(p1.order_id, p2.order_id, p3.order_id) > max(u1.order_id, u2.order_id, u3.order_id)
        # Unpinned relative order unchanged
        assert u1.order_id > u2.order_id > u3.order_id

    def test_bulk_reorder_unpinned_section(self, auth_client, create_note):
        """Test reorder within unpinned section doesn't affect pinned notes."""
        client, user = auth_client
        p1 = create_note(user, title="P1", order_id=5)
        p1.pinned = True
        p1.save()
        p2 = create_note(user, title="P2", order_id=4)
        p2.pinned = True
        p2.save()
        u1 = create_note(user, title="U1", order_id=3)
        u2 = create_note(user, title="U2", order_id=2)
        u3 = create_note(user, title="U3", order_id=1)

        # Move U1 (unpinned pos 1) to unpinned pos 3 → U2, U3, U1
        response = client.post(
            "/api/notes/bulk-reorder/",
            {"uuid": str(u1.uuid), "new_position": 3, "pinned": False},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK

        for n in [p1, p2, u1, u2, u3]:
            n.refresh_from_db()

        # Pinned unchanged and still above unpinned
        assert p1.order_id > p2.order_id
        assert min(p1.order_id, p2.order_id) > max(u1.order_id, u2.order_id, u3.order_id)
        # Unpinned order: U2 > U3 > U1
        assert u2.order_id > u3.order_id > u1.order_id

    def test_bulk_reorder_no_duplicate_order_ids(self, auth_client, create_note):
        """Test reorder never produces duplicate order_ids."""
        client, user = auth_client
        notes = [create_note(user, title=f"N{i}") for i in range(10)]

        # Move first to last
        response = client.post(
            "/api/notes/bulk-reorder/",
            {"uuid": str(notes[0].uuid), "new_position": 10, "pinned": False},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK

        from django.db.models import Count
        dupes = Note.objects.filter(user=user, deleted=False).values("order_id").annotate(c=Count("id")).filter(c__gt=1)
        assert not dupes.exists()

    def test_bulk_reorder_requires_pinned_field(self, auth_client, create_note):
        """Test reorder returns 400 if pinned field is missing."""
        client, user = auth_client
        note = create_note(user, title="Test")
        response = client.post(
            "/api/notes/bulk-reorder/",
            {"uuid": str(note.uuid), "new_position": 1},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_bulk_reorder_wrong_section(self, auth_client, create_note):
        """Test reorder returns 404 if note is not in the specified section."""
        client, user = auth_client
        note = create_note(user, title="Unpinned note")
        response = client.post(
            "/api/notes/bulk-reorder/",
            {"uuid": str(note.uuid), "new_position": 1, "pinned": True},
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestNoteCreate:
    """Test note creation endpoint."""

    def test_create_note(self, auth_client):
        """Test creating a note."""
        client, user = auth_client
        response = client.post("/api/notes/", {"title": "New note", "body": "Details"})
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["data"]["title"] == "New note"
        assert Note.objects.filter(user=user).count() == 1

    def test_create_note_minimal(self, auth_client):
        """Test creating a note with only title."""
        client, _ = auth_client
        response = client.post("/api/notes/", {"title": "Just a title"})
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["data"]["completed"] is False
        assert response.data["data"]["deleted"] is False

    def test_create_note_no_title(self, auth_client):
        """Test creating a note without title fails."""
        client, _ = auth_client
        response = client.post("/api/notes/", {"body": "No title"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_note_assigns_order_id(self, auth_client, create_note):
        """Test creating a note assigns a new order_id for the user."""
        client, user = auth_client
        create_note(user, title="First note")
        response = client.post("/api/notes/", {"title": "Second note"})
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["data"]["order_id"] == 2
        assert Note.objects.get(title="Second note").order_id == 2


@pytest.mark.django_db
class TestNoteDetail:
    """Test note detail endpoint."""

    def test_get_note(self, auth_client, create_note):
        """Test getting a single note."""
        client, user = auth_client
        note = create_note(user)
        response = client.get(f"/api/notes/{note.uuid}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["title"] == note.title

    def test_get_other_user_note(self, api_client, create_user, create_note):
        """Test that users cannot access other users' notes."""
        user1 = create_user(email="user1@example.com", username="user1")
        user2 = create_user(email="user2@example.com", username="user2")
        note = create_note(user1)
        api_client.force_authenticate(user=user2)
        response = api_client.get(f"/api/notes/{note.uuid}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_nonexistent_note(self, auth_client):
        """Test getting a note that doesn't exist."""
        client, _ = auth_client
        response = client.get("/api/notes/00000000-0000-0000-0000-000000000000/")
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestNoteUpdate:
    """Test note update endpoints."""

    def test_full_update(self, auth_client, create_note):
        """Test full update of a note."""
        client, user = auth_client
        note = create_note(user)
        response = client.put(
            f"/api/notes/{note.uuid}/",
            {"title": "Updated", "body": "Updated body", "completed": True},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["title"] == "Updated"
        assert response.data["data"]["completed"] is True

    def test_partial_update(self, auth_client, create_note):
        """Test partial update (toggle completed)."""
        client, user = auth_client
        note = create_note(user)
        response = client.patch(f"/api/notes/{note.uuid}/", {"completed": True})
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["completed"] is True
        assert response.data["data"]["title"] == note.title

    def test_update_other_user_note(self, api_client, create_user, create_note):
        """Test that users cannot update other users' notes."""
        user1 = create_user(email="user1@example.com", username="user1")
        user2 = create_user(email="user2@example.com", username="user2")
        note = create_note(user1)
        api_client.force_authenticate(user=user2)
        response = api_client.patch(f"/api/notes/{note.uuid}/", {"completed": True})
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestNoteDelete:
    """Test note delete endpoint."""

    def test_soft_delete(self, auth_client, create_note):
        """Test first delete soft-deletes the note."""
        client, user = auth_client
        note = create_note(user)
        response = client.delete(f"/api/notes/{note.uuid}/")
        assert response.status_code == status.HTTP_200_OK
        note.refresh_from_db()
        assert note.deleted is True

    def test_permanent_delete(self, auth_client, create_note):
        """Test second delete permanently removes the note."""
        client, user = auth_client
        note = create_note(user, deleted=True)
        response = client.delete(f"/api/notes/{note.uuid}/")
        assert response.status_code == status.HTTP_200_OK
        assert not Note.objects.filter(uuid=note.uuid).exists()

    def test_delete_other_user_note(self, api_client, create_user, create_note):
        """Test that users cannot delete other users' notes."""
        user1 = create_user(email="user1@example.com", username="user1")
        user2 = create_user(email="user2@example.com", username="user2")
        note = create_note(user1)
        api_client.force_authenticate(user=user2)
        response = api_client.delete(f"/api/notes/{note.uuid}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestNoteImageStorageCleanup:
    """Test file cleanup on image replacement and permanent deletion."""

    def test_replacing_image_deletes_old_files(self, auth_client, tmp_path):
        client, user = auth_client
        image1 = make_test_image(color=(255, 0, 0), name="image1.png")
        image2 = make_test_image(color=(0, 255, 0), name="image2.png")

        with override_settings(
            MEDIA_ROOT=tmp_path,
            STORAGES={
                "default": {
                    "BACKEND": "django.core.files.storage.FileSystemStorage",
                    "OPTIONS": {"location": str(tmp_path)},
                },
                "staticfiles": {
                    "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
                },
            },
        ):
            response = client.post(
                "/api/notes/",
                {"title": "Note with image", "body": "Details", "image": image1},
                format="multipart",
            )
            assert response.status_code == status.HTTP_201_CREATED

            note = Note.objects.get(uuid=response.data["data"]["uuid"])
            old_image_name = note.image.name
            old_thumbnail_name = note.thumbnail.name
            assert (tmp_path / old_image_name).exists()
            assert (tmp_path / old_thumbnail_name).exists()

            response = client.put(
                f"/api/notes/{note.uuid}/",
                {"title": "Replaced", "body": "New body", "image": image2},
                format="multipart",
            )
            assert response.status_code == status.HTTP_200_OK

            note.refresh_from_db()
            new_image_name = note.image.name
            new_thumbnail_name = note.thumbnail.name
            assert (tmp_path / new_image_name).exists()
            assert (tmp_path / new_thumbnail_name).exists()

            # Old objects should be removed from storage.
            assert not (tmp_path / old_image_name).exists()
            assert not (tmp_path / old_thumbnail_name).exists()

    def test_permanent_delete_removes_files(self, auth_client, tmp_path):
        client, user = auth_client
        image = make_test_image(color=(0, 0, 255), name="image.png")

        with override_settings(
            MEDIA_ROOT=tmp_path,
            STORAGES={
                "default": {
                    "BACKEND": "django.core.files.storage.FileSystemStorage",
                    "OPTIONS": {"location": str(tmp_path)},
                },
                "staticfiles": {
                    "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
                },
            },
        ):
            response = client.post(
                "/api/notes/",
                {"title": "Note to delete", "body": "Details", "image": image},
                format="multipart",
            )
            assert response.status_code == status.HTTP_201_CREATED

            note = Note.objects.get(uuid=response.data["data"]["uuid"])
            old_image_name = note.image.name
            old_thumbnail_name = note.thumbnail.name
            assert (tmp_path / old_image_name).exists()
            assert (tmp_path / old_thumbnail_name).exists()

            # First delete is a soft delete: files must remain.
            response = client.delete(f"/api/notes/{note.uuid}/")
            assert response.status_code == status.HTTP_200_OK
            note.refresh_from_db()
            assert note.deleted is True
            assert (tmp_path / old_image_name).exists()
            assert (tmp_path / old_thumbnail_name).exists()

            # Second delete is permanent: files must be removed.
            response = client.delete(f"/api/notes/{note.uuid}/")
            assert response.status_code == status.HTTP_200_OK
            assert not Note.objects.filter(uuid=note.uuid).exists()
            assert not (tmp_path / old_image_name).exists()
            assert not (tmp_path / old_thumbnail_name).exists()


@pytest.mark.django_db
class TestApiResponseFormat:
    """Test that responses follow the ApiResponse format."""

    def test_response_format(self, auth_client, create_note):
        """Test response contains data, statusCode, and timestamp."""
        client, user = auth_client
        create_note(user)
        response = client.get("/api/notes/")
        assert "data" in response.data
        assert "statusCode" in response.data
        assert "timestamp" in response.data
