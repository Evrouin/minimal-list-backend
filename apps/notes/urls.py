from django.urls import path

from .views import NoteDetailView, NoteListCreateView, bulk_delete_notes, bulk_pin_notes, bulk_restore_notes, link_preview

urlpatterns = [
    path("", NoteListCreateView.as_view(), name="note_list_create"),
    path("bulk-delete/", bulk_delete_notes, name="note_bulk_delete"),
    path("bulk-pin/", bulk_pin_notes, name="note_bulk_pin"),
    path("bulk-restore/", bulk_restore_notes, name="note_bulk_restore"),
    path("link-preview/", link_preview, name="note_link_preview"),
    path("<int:pk>/", NoteDetailView.as_view(), name="note_detail"),
]
