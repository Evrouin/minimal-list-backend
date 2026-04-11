from django.urls import path

from .views import (
    FolderDetailView,
    FolderListCreateView,
    NoteDetailView,
    NoteListCreateView,
    archive_folder,
    archive_note,
    bulk_archive_notes,
    bulk_delete_notes,
    bulk_pin_notes,
    bulk_reorder_notes,
    bulk_restore_notes,
    clear_all_notes,
    empty_trash,
    link_preview,
    reorder_folders,
    snooze_note,
    unarchive_folder,
    unarchive_note,
)

urlpatterns = [
    # Notes
    path("", NoteListCreateView.as_view(), name="note_list_create"),
    path("bulk-delete/", bulk_delete_notes, name="note_bulk_delete"),
    path("bulk-pin/", bulk_pin_notes, name="note_bulk_pin"),
    path("bulk-restore/", bulk_restore_notes, name="note_bulk_restore"),
    path("bulk-reorder/", bulk_reorder_notes, name="note_bulk_reorder"),
    path("bulk-archive/", bulk_archive_notes, name="note_bulk_archive"),
    path("clear-all/", clear_all_notes, name="note_clear_all"),
    path("empty-trash/", empty_trash, name="note_empty_trash"),
    path("link-preview/", link_preview, name="note_link_preview"),
    path("<uuid:uuid>/", NoteDetailView.as_view(), name="note_detail"),
    path("<uuid:uuid>/archive/", archive_note, name="note_archive"),
    path("<uuid:uuid>/unarchive/", unarchive_note, name="note_unarchive"),
    # Folders
    path("folders/", FolderListCreateView.as_view(), name="folder_list_create"),
    path("folders/reorder/", reorder_folders, name="folder_reorder"),
    path("folders/<uuid:uuid>/", FolderDetailView.as_view(), name="folder_detail"),
    path("folders/<uuid:uuid>/archive/", archive_folder, name="folder_archive"),
    path("folders/<uuid:uuid>/unarchive/", unarchive_folder, name="folder_unarchive"),
]
