# Folders & Sidebar — Feature Proposal

## Overview

Replace the current flat filter tabs (all/active/completed/deleted) with a **folder-based organization system** and a **hamburger sidebar**. Users can create custom folders alongside three default folders (notes, tasks, reminders). Trash and Archive move to dedicated sidebar items.

This keeps the minimalist branding intact — the note model stays simple, organization is user-driven rather than app-imposed.

---

## Core Concept

A note is still just a note. Folders are lightweight containers — a note belongs to one folder (or none, defaulting to "notes"). No special note types, no schema changes beyond a `folder_id` field.

---

## Sidebar Design

```
Sidebar (slides in from left, swipe gesture on mobile):

┌──────────────────┐
│  minimal list    │
├──────────────────┤
│  notes           │  ← default folder (current behavior)
│  tasks           │  ← default folder
│  reminders       │  ← default folder
│  archive         │  ← archived notes & folders
│  trash           │  ← replaces deleted filter tab
├──────────────────┤
│  my folders      │
│    work          │  ← user-created
│    personal      │
│    ideas         │
│  + new folder    │
├──────────────────┤
│  account         │  ← profile, avatar, password, sessions, danger zone
│  settings        │  ← app preferences (color, haptics, notifications, default folder)
│  admin           │  ← superusers only
└──────────────────┘
```

> **Icons:** text-only by default, matching the app's minimal aesthetic. Folder icons are an optional future enhancement — if added, they would be small and muted, not colorful.

**Sidebar behavior:**
- Opens via hamburger icon (top left of header) or swipe right on mobile
- **Overlay mode only** — sidebar floats over content, never pushes/shrinks the notes grid
- Closes on backdrop tap, swipe left, or Esc
- Active folder highlighted
- Folder note count shown (optional)
- Net space gain: filter tabs (~40px) removed, hamburger fits in existing header row

---

## Navigation Changes

### Current
```
/ → notes page with filter tabs: all | active | completed | deleted
```

### Proposed
```
/ → notes page, active folder = "notes" (default)
    sidebar controls active folder
    no filter tabs — folder is the primary navigation
    active/completed state is per-card, filterable in a future update
    /trash → dedicated trash page (all deleted notes across folders)
```

---

## Default Folders

| Folder | Icon | Description |
|--------|------|-------------|
| notes | 📝 | General notes — current default behavior |
| tasks | ✅ | Checklist-style notes (future: inline checklist UI) |
| reminders | 🔔 | Notes with a reminder_at set (future: auto-sort by time) |

Default folders cannot be renamed or deleted. They are pre-seeded per user on registration.

---

## Custom Folders

- User can create, rename, delete, and **reorder** custom folders via drag-and-drop in the sidebar
- Default folders (notes/tasks/reminders) are always pinned at the top — not draggable
- Max depth: **1 level** (no sub-folders in v1)
- Deleting a folder moves its notes to "notes" (default), does not delete them
- Max folders: reasonable limit (e.g. 20) to keep sidebar clean

---

## Archive Page (`/archive`)

A dedicated space for notes and folders you want to keep but not see day-to-day.

**Archive rules:**
- Archiving a **note** → hidden from all folder views, moved to archive
- Archiving a **folder** → folder and all its notes archived together, folder disappears from sidebar
- Archived items are recoverable (unarchive) indefinitely — no auto-purge
- Archived notes do **not** appear in normal folder views or search by default
- Reminders on archived notes are automatically dismissed
- Archive is not trash — intent is "keep but hide", not "pending deletion"

**Archive vs Trash:**

| | Archive | Trash |
|--|---------|-------|
| Intent | Keep but hide | Pending deletion |
| Recoverable | Yes, indefinitely | Yes, until emptied |
| Auto-purge | No | No (manual empty) |
| Reminders | Dismissed | Dismissed |
| Searchable | Optional toggle | No |

**Backend:** `is_archived` boolean on both `Note` and `Folder` models. Simple flag, no new model needed.

---

## Trash Page (`/trash`)

- Separate page, accessible from sidebar
- Lists all deleted notes across all folders, grouped by folder or date
- Restore / permanent delete per note
- "Empty trash" button (existing endpoint)
- Notes in trash retain their original folder reference for restore

---

## UI Changes

### Header
- Hamburger icon (left) — only header action for navigation
- Profile/admin icons removed from header (moved to sidebar bottom)
- Right side of header: add note button (desktop) only

### Account & Settings (sidebar bottom)
- **Account** (`/auth/profile`) — profile info, avatar, password, Google auth, active sessions, danger zone. No change to existing page structure.
- **Settings** (`/settings`) — new page for app preferences:
  - Default note color
  - Default folder for new notes
  - Haptic feedback toggle (Android)
  - Notification preferences
  - Theme (future)
- **Admin** — only visible to superusers, links to `/admin`

### Notes Page
- Folder name shown as page title (replaces "minimal list" title or shown below it)
- Notes filtered by active folder
- Add note → note created in active folder
- No filter tabs — active/completed state handled per-card or via a future filter/sort option

### TodoCard
- Optional folder badge (subtle, small) — only shown in "all notes" cross-folder view
- No other card changes

### Mobile
- Sidebar opens via hamburger or swipe-right gesture
- Backdrop overlay when open
- Swipe-left or tap backdrop to close

---

## Backend Impact

### Model Changes
- Add `Folder` model: `id, user, name, icon, is_default, order, is_archived, created_at`
- Add `folder` FK to `Note` model (nullable, defaults to user's "notes" folder)
- Add `is_archived` boolean to `Note` model
- Seed 3 default folders on user registration
- API endpoints:
  - `GET/POST /api/folders/`
  - `PATCH/DELETE /api/folders/:id/`
  - `POST /api/folders/:id/archive/`
  - `POST /api/folders/:id/unarchive/`
  - `GET /api/notes/?folder=:id` (add folder filter to existing endpoint)
  - `POST /api/notes/:id/archive/`
  - `POST /api/notes/:id/unarchive/`

### Migration
- Existing notes get assigned to the user's default "notes" folder
- Non-breaking with nullable FK + default

---

## Frontend Impact

### High Impact
- **`pages/index.vue`** — integrate sidebar, folder-aware note loading
- **`stores/todos.ts`** — add active folder state, folder-filtered fetching
- **`components/TodoHeader.vue`** — remove filter tabs, add hamburger, show active folder name
- **`pages/trash.vue`** — new page (move deleted filter here)
- **`pages/archive.vue`** — new page (archived notes and folders)
- **`types/todo.d.ts`** — add `folder_id` to `Todo`

### Medium Impact
- **`useTodoApi.ts`** — add folder param to fetch, new folder CRUD endpoints, archive/unarchive endpoints
- **`middleware/auth.global.ts`** — add `/trash` to public/protected paths
- **`plugins/back-button.client.ts`** — handle sidebar close on Android back

### Low Impact
- **`TodoCard.vue`** — optional folder badge in cross-folder view
- **`MasonryGrid.vue`**, **`AudioPlayer.vue`**, **`ReminderPicker.vue`** — no changes

### New Files Needed
- `components/AppSidebar.vue` — sidebar component
- `composables/useFolders.ts` — folder CRUD and active folder state
- `stores/folders.ts` — folder state
- `pages/trash.vue` — trash page
- `pages/archive.vue` — archive page
- `pages/settings.vue` — app preferences (split from profile)
- `types/folder.d.ts` — Folder type

---

## Migration Strategy

### Phase 1 — Foundation (low risk)
1. Add `Folder` model + migration on backend
2. Seed default folders on registration
3. Add `folder_id` and `is_archived` to `Note` (nullable, defaults)
4. Add `is_archived` to `Folder`
5. Add folder filter + archive/unarchive to notes API
6. Add `/trash` page, remove "deleted" tab from filter tabs
7. Add `/archive` page

### Phase 2 — Sidebar
6. Build `AppSidebar.vue` with default folders + trash + archive links
7. Hamburger in header, swipe gesture on mobile
8. Active folder state in store, notes filtered by folder
9. Add note → assigned to active folder
10. Move profile/admin icons from header to sidebar bottom
11. Create `/settings` page, move app preferences out of profile

### Phase 3 — Custom Folders
10. Folder CRUD UI in sidebar (create, rename, delete)
11. Move note to folder (drag or context menu)
12. Folder note counts
13. **Drag-to-reorder folders** in sidebar (custom folders only, default folders stay fixed at top)

### Phase 4 — Polish
13. Folder icons/colors (optional)
14. Sub-folders (optional, v2)
15. Update FAQ, README

---

## Risks & Considerations

- **Sidebar on mobile** — needs careful gesture handling to not conflict with swipe-to-refresh and drag-to-reorder. Use a distinct swipe zone (left edge only).
- **Default folder seeding** — must happen on registration and on first login for existing users.
- **Cross-folder search** — when search is added, it should span all folders.
- **Android back button** — back should close sidebar before navigating back.
- **Sub-folders** — intentionally excluded from v1. Research shows most users never go deeper than 1 level. Flat folders with descriptive names (e.g. `work-client-a`) cover the majority of use cases without the added UI and backend complexity. If sub-folders become a validated user need post-launch, the implementation path is a simple `parent_id` FK with a **max depth of 1** (folder → subfolder, no deeper). This avoids recursive queries and keeps the sidebar UI manageable. No tree structures, no breadcrumbs, no closure tables.

---

## Edge Cases

### Folders
- **Deleting a folder with notes** — notes move to "notes" (default), never deleted silently. Show count in confirmation: "move 12 notes to default folder?"
- **Renaming a default folder** — not allowed. Default folders (notes/tasks/reminders) are fixed.
- **Folder limit reached** — show inline error when user tries to create beyond the limit.
- **Empty folder** — show empty state, still allow delete.
- **Folder with only deleted notes** — folder appears empty (deleted notes are in trash, not the folder view). Note count should exclude deleted.
- **Duplicate folder name** — prevent at creation/rename, show inline error.
- **Folder drag-and-drop reorder** — only custom folders are draggable. Default folders stay fixed. Order persisted via `order` field on the backend (same pattern as note reordering).
- **Very long folder name** — truncate in sidebar with ellipsis, show full name on hover/tooltip.

### Notes & Folders
- **Note created while sidebar is open** — note goes into the currently active folder.
- **Moving a note to a different folder** — needs a "move to folder" action on the card (long-press menu or card action). Not in v1 — defer to Phase 3.
- **Note in a deleted folder** — if folder is deleted, note is reassigned to default. No orphaned notes.
- **Bulk actions across folders** — multi-select only operates within the current folder view. Cross-folder bulk actions deferred.
- **Pinned notes across folders** — pinned notes only pin within their folder, not globally across all folders.
- **Infinite scroll + folder switch** — switching folders resets pagination cursor and clears the current list.
- **URL state** — active folder should be reflected in the URL (e.g. `/?folder=work`) so it persists on refresh and can be deep-linked.

### Trash
- **Restoring a note whose folder was deleted** — restore to "notes" default, not the original folder.
- **Empty trash with notes from multiple folders** — all deleted notes removed regardless of folder.
- **Trash pagination** — trash can grow large; needs the same infinite scroll as the main view.
- **Note deleted from trash view** — permanent delete, no undo.

### Archive
- **Archiving a folder with notes** — all notes archived with it. Unarchiving the folder restores all notes.
- **Archiving a note inside an archived folder** — note stays archived even if folder is unarchived (note-level archive takes precedence).
- **Reminder on archived note** — auto-dismissed on archive. Restored on unarchive only if `reminder_at` is still in the future.
- **Archived folder deleted** — notes move to "notes" default (unarchived), same as regular folder deletion.
- **Search in archive** — archived content excluded by default; toggle to include.

### Sidebar
- **Sidebar open + Android back button** — back closes sidebar first, then navigates back normally.
- **Sidebar open + swipe-to-refresh** — swipe-to-refresh should be disabled while sidebar is open.
- **Sidebar open + drag-to-reorder** — drag should be disabled while sidebar is open.
- **Sidebar open + expanded note editor** — closing the expanded editor should not close the sidebar (they're independent).
- **First-time user** — default folders pre-seeded, sidebar shows them immediately. No empty state needed for folders.
- **Existing users on migration** — all notes assigned to "notes" folder silently. Sidebar shows correct counts on first load.

### Sync & Offline
- **Folder created offline** — queue and sync when back online (same pattern as note creation).
- **Folder deleted offline** — defer to online; show optimistic UI.
- **Note count mismatch** — counts are derived from the API, not cached locally. Refresh on folder switch.

---

**Phase 1 + 2** as a single milestone — trash page and sidebar with default folders only. This delivers the most visible UX improvement with manageable scope. Custom folders (Phase 3) as a follow-up milestone after user feedback.
