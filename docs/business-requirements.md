# Business Requirements & Acceptance Criteria

## Overview

This document defines the business requirements and functional/technical acceptance criteria for the next two major feature milestones of minimal list:

1. **Folders & Sidebar** — folder-based note organization with a hamburger sidebar
2. **Reminders & Task Completion** — reminder lifecycle, recurrence, snooze, and context-aware completion

---

## Milestone 1: Folders & Sidebar

---

### BR-01: Sidebar Navigation

**Business Requirement**
Users need a way to navigate between note collections without cluttering the main note view. The sidebar replaces the current filter tabs and provides a persistent, accessible navigation structure.

**Functional Acceptance Criteria**
- [x] Sidebar opens via hamburger icon in the top-left header
- [x] Sidebar opens via swipe-right gesture on mobile (left edge only)
- [x] Sidebar closes via backdrop tap, swipe-left, or Esc key
- [x] Sidebar is overlay mode only — does not push or shrink the notes grid
- [x] Active folder is visually highlighted in the sidebar
- [x] Sidebar is text-only (no icons by default)
- [x] On Android, pressing back while sidebar is open closes the sidebar before navigating back

**Technical Acceptance Criteria**
- [x] `AppSidebar.vue` component created
- [x] Sidebar state managed globally (open/closed)
- [x] Swipe gesture does not conflict with swipe-to-refresh or drag-to-reorder
- [x] Swipe-to-refresh and drag-to-reorder disabled while sidebar is open
- [x] `plugins/back-button.client.ts` updated to handle sidebar close

---

### BR-02: Default Folders

**Business Requirement**
Every user has three pre-seeded default folders (notes, tasks, reminders) that provide immediate structure without requiring setup. Default folders cannot be modified or deleted.

**Functional Acceptance Criteria**
- [x] Three default folders exist for every user: notes, tasks, reminders
- [x] Default folders appear at the top of the sidebar, above custom folders
- [x] Default folders cannot be renamed, deleted, or reordered
- [x] New notes are created in the currently active folder
- [x] Existing notes are migrated to the "notes" default folder silently on first load
- [x] Active folder name is shown as the page title

**Technical Acceptance Criteria**
- [x] `Folder` model added to backend with `is_default` flag
- [x] Default folders seeded on user registration
- [x] Default folders seeded for existing users on first login (migration-safe)
- [x] `folder_id` FK added to `Note` model (nullable, defaults to "notes" folder)
- [x] `GET /api/notes/?folder=:id` endpoint supports folder filtering
- [x] Active folder state stored in `stores/folders.ts`
- [x] Active folder reflected in URL (e.g. `/?folder=notes`) for deep-linking and refresh persistence

---

### BR-03: Custom Folders

**Business Requirement**
Users can create personal folders to organize notes beyond the three defaults. Folders can be renamed, deleted, and reordered to match the user's workflow.

**Functional Acceptance Criteria**
- [x] User can create a custom folder with a name
- [x] User can rename a custom folder
- [x] User can delete a custom folder — notes move to "notes" default (not deleted)
- [x] Deletion confirmation shows note count: "move X notes to default folder?"
- [x] User can drag-and-drop custom folders to reorder them in the sidebar
- [x] Default folders are not draggable
- [x] Duplicate folder names are prevented with an inline error
- [x] Very long folder names are truncated with ellipsis in the sidebar
- [x] Maximum of 20 custom folders per user
- [x] Folder limit error shown inline when limit is reached

**Technical Acceptance Criteria**
- [x] `GET/POST /api/notes/folders/` endpoints implemented
- [x] `PATCH/DELETE /api/notes/folders/:id/` endpoints implemented
- [x] `order` field on `Folder` model for drag-to-reorder persistence
- [x] `composables/useFolders.ts` handles folder CRUD and active folder state
- [x] `POST /api/notes/folders/reorder/` endpoint implemented
- [x] Switching folders resets pagination cursor and clears current note list

---

### BR-04: Trash Page

**Business Requirement**
Deleted notes are moved to a dedicated trash page instead of a filter tab, giving users a clear separation between active notes and pending deletions.

**Functional Acceptance Criteria**
- [x] Trash accessible from sidebar
- [x] Trash shows all deleted notes across all folders
- [x] Notes in trash grouped by folder or date
- [x] Each note can be restored or permanently deleted
- [x] "Empty trash" button permanently deletes all trashed notes with confirmation
- [x] Restoring a note whose folder was deleted restores it to "notes" default
- [x] Trash supports infinite scroll
- [x] "Deleted" filter tab removed from main notes page

**Technical Acceptance Criteria**
- [x] `pages/trash.vue` created
- [x] `/trash` added to auth middleware public/protected paths
- [x] Existing `empty-trash` endpoint used for "empty trash" action
- [x] Trash note list uses same pagination pattern as main notes list
- [x] `TodoHeader.vue` filter tabs updated (deleted tab removed)

---

### BR-05: Archive

**Business Requirement**
Users can archive notes and folders they want to keep but not see in their active workspace. Archive is distinct from trash — archived items are intentionally preserved, not pending deletion.

**Functional Acceptance Criteria**
- [x] Archive accessible from sidebar
- [x] Archiving a note hides it from all folder views
- [x] Archiving a folder archives the folder and all its notes together
- [x] Archived items can be unarchived (restored to original folder or "notes" default)
- [x] Archived notes do not appear in normal folder views or search by default
- [x] Reminders on archived notes are automatically dismissed on archive
- [x] Reminders restored on unarchive only if `reminder_at` is still in the future
- [x] Archiving a folder with notes shows confirmation with note count
- [x] Deleting an archived folder moves its notes to "notes" default (unarchived)

**Technical Acceptance Criteria**
- [x] `is_archived` boolean added to `Note` model
- [x] `is_archived` boolean added to `Folder` model
- [x] `POST /api/notes/:id/archive/` and `/unarchive/` endpoints
- [x] `POST /api/folders/:id/archive/` and `/unarchive/` endpoints
- [x] `pages/archive.vue` created
- [x] Archive excluded from default note queries (`is_archived=false` filter)
- [x] Note-level archive takes precedence over folder-level (note stays archived if folder is unarchived)

---

### BR-06: Settings Page

> **Cancelled** — settings consolidated into the existing profile page. No separate settings page needed.



---

## Milestone 2: Reminders & Task Completion

---

### BR-07: Context-Aware Completion

**Business Requirement**
The "complete" action is only meaningful for tasks and notes with reminders. Showing it on plain notes adds noise without value.

**Functional Acceptance Criteria**
- [x] Complete button hidden on plain notes (no reminder, not in tasks folder)
- [x] Complete button always visible on notes in the tasks folder
- [x] Complete button available on any note with `reminder_at` set
- [x] Completing a note with a reminder dismisses the reminder
- [x] Completing a recurring reminder stops the recurrence

**Technical Acceptance Criteria**
- [x] `TodoCard.vue` complete button conditionally rendered based on folder + reminder state
- [x] No backend changes required for this phase
- [x] Complete button not hidden behind hover on task cards (always visible)

---

### BR-08: Overdue Reminders

**Business Requirement**
Users need a clear visual signal when a reminder has passed without being acted on, so overdue items are not silently ignored.

**Functional Acceptance Criteria**
- [x] Notes with `reminder_at` in the past and `completed = false` are marked overdue
- [x] Overdue notes show a red bell indicator on the card
- [x] Overdue notes appear at the top of the reminders folder view
- [x] Overdue state is derived — no user action required to trigger it
- [x] Snoozed notes are not marked overdue while `snoozed_until` is in the future
- [x] Rescheduling a reminder to a future time clears the overdue state immediately
- [x] Rescheduling a reminder resets the notification so it re-fires at the new time

**Technical Acceptance Criteria**
- [x] `is_overdue` computed from `reminder_at < now && !completed && !(snoozed_until > now)` (frontend)
- [x] `TodoCard.vue` renders overdue indicator
- [x] Reminders folder sorts by `reminder_at` ascending, overdue group first
- [x] `firedIds` set in `reminders.client.ts` cleared for a note when its `fireAt` moves to the future
- [x] Web snooze toast dismissed when reminder is rescheduled to a future time
- [x] `reminderSections` in `TodoList.vue` excludes snoozed notes from overdue bucket
- [x] `updateTodo` in `stores/todos.ts` sends `snoozed_until: null` to backend when `reminder_at` changes

---

### BR-09: Reminders Folder View

**Business Requirement**
The reminders folder provides a timeline view of upcoming and overdue reminders, replacing the masonry grid with a layout suited to time-based content.

**Functional Acceptance Criteria**
- [x] Reminders folder shows notes with `reminder_at` set, sorted by time ascending
- [x] Notes grouped by: overdue / today / tomorrow / this week / later
- [x] Overdue group appears at the top
- [x] Timeline list layout used instead of masonry grid

**Technical Acceptance Criteria**
- [x] `TodoList.vue` renders timeline layout when active folder is "reminders"
- [x] `GET /api/notes/?has_reminder=true` returns notes sorted by `reminder_at` (cross-folder, not folder UUID)

---

### BR-10: Reminder Recurrence

**Business Requirement**
Users can set reminders that repeat on a schedule, so recurring tasks and habits don't require manual re-entry.

**Functional Acceptance Criteria**
- [x] Recurrence options: none, daily, weekly, monthly
- [x] Recurrence selector available in `ReminderPicker`
- [x] On recurrence, `reminder_at` advances to the next occurrence automatically
- [x] Completing a recurring reminder stops all future recurrences
- [x] Deleting a note with recurrence cancels all future occurrences
- [x] Ignoring a notification re-fires at the next scheduled time

**Technical Acceptance Criteria**
- [x] `recurrence_rule` field added to `Note` model: `none | daily | weekly | monthly`
- [x] Backend advances `reminder_at` on each recurrence trigger
- [x] `ReminderPicker.vue` updated with recurrence selector UI
- [x] `useReminders.ts` updated for recurrence-aware scheduling
- [x] Recurrence indicator shown on card when recurrence is set

---

### BR-11: Snooze

**Business Requirement**
Users can snooze a reminder when they see the notification but aren't ready to act, preventing reminders from being silently missed.

**Functional Acceptance Criteria**
- [x] Snooze options: 15 minutes, 1 hour, tomorrow (same time), pick a time
- [x] Snooze available from notification (Android) and in-app (web)
- [x] Snoozed reminder re-fires after the snooze period
- [x] Multiple snoozes allowed — each replaces the previous
- [x] Snooze state survives app restart (server-side)
- [x] If snooze extends past next recurrence, snooze wins
- [x] Web snooze prompt displayed as a toast matching the undo toast style: `[title · due now   snooze Xm   done]`
- [x] Clicking the note title in the web snooze toast navigates to the reminders folder and opens a view dialog for the note
- [x] View dialog for reminder notes includes complete and delete action buttons
- [x] Closing the view dialog without acting restores the snooze toast
- [x] Tapping an Android notification (body) navigates to the reminders folder and opens the note view dialog

**Technical Acceptance Criteria**
- [x] `snoozed_until` nullable datetime field added to `Note` model
- [x] `POST /api/notes/:id/snooze/` endpoint sets `snoozed_until`
- [x] `useReminders.ts` polling checks `snoozed_until` before firing
- [x] Android notification action buttons: "snooze 15m" and "done" via Capacitor
- [x] Web: in-app snooze prompt shown after notification fires
- [x] On app open, local notifications rescheduled based on current `snoozed_until`
- [x] UUID stored in notification `extra` field for reliable note lookup on Android tap
- [x] Android notification default tap handled in `localNotificationActionPerformed` — routes to `/?folder=reminders&open=<uuid>`
- [x] `pages/index.vue` watches `route.query.open` and opens note view dialog once todos are loaded
- [x] Web snooze toast hidden while note view dialog is open; restored on dialog close without action

---

### BR-12: Tasks Folder View

**Business Requirement**
The tasks folder provides a focused view for actionable items, with completion as the primary interaction.

**Functional Acceptance Criteria**
- [x] Complete button always visible on task cards (not hover-only)
- [x] Completed tasks visually dimmed or struck through
- [x] Optional "hide completed" toggle in tasks folder header
- [x] No reminder required for a task — completion is standalone

**Technical Acceptance Criteria**
- [x] `TodoCard.vue` renders complete button without hover requirement when in tasks folder
- [x] "Hide completed" toggle filters `completed = true` notes client-side or via API param
- [x] No new backend fields required for this phase

---

---

## Milestone 3: Account Lifecycle

---

### BR-13: User Deactivation

**Business Requirement**
Users can reversibly deactivate their own account without losing data. Deactivation is distinct from deletion — it suspends access while preserving all notes and settings. Admins can also deactivate/reactivate accounts, with different recovery flows depending on who initiated it.

**Functional Acceptance Criteria**
- [x] User can deactivate their own account from the profile page
- [x] Deactivated user cannot log in (web or native)
- [x] Self-deactivated user receives an email with a reactivation link (7-day expiry)
- [x] Self-deactivated user can reactivate via the email link
- [x] Admin-deactivated user sees "contact support" message on login (no self-reactivation)
- [x] Admin can reactivate any deactivated user from the admin panel
- [x] All active sessions are blacklisted immediately on deactivation
- [x] If user has a pending deletion scheduled, deactivation cancels it
- [x] Deactivated accounts still block email re-registration

**Technical Acceptance Criteria**
- [x] `deactivation_reason`, `reactivation_token`, `reactivation_token_expires` fields added to `User` model
- [x] `POST /api/auth/deactivate/` endpoint — self-service, blacklists sessions, sends email
- [x] `POST /api/auth/reactivate/:token/` endpoint — validates token + expiry, restores account
- [x] Login view returns context-aware error (self vs admin deactivation)
- [x] Admin `PATCH /api/admin/users/:id/` handles session blacklisting + emails on `is_active` toggle
- [x] `pages/auth/reactivate/[token].vue` created
- [x] Deactivate button added to `pages/auth/profile.vue`
- [x] `/auth/reactivate` added to public middleware paths
- [x] `deactivateAccount()` added to `useAuthApi.ts`

---

### BR-14: Soft Account Deletion with 30-Day Recovery

**Business Requirement**
Account deletion is non-immediate — users have a 30-day grace period to cancel. During this window the account is locked but all data is preserved. After 30 days a scheduled job permanently deletes the account and all associated data.

**Functional Acceptance Criteria**
- [x] Deleting an account schedules permanent deletion in 30 days (not immediate)
- [x] User receives a confirmation email with a cancel/recover link
- [x] User can cancel deletion within 30 days via the email link
- [x] Locked account cannot log in during the grace period
- [x] Login shows specific error: "Account scheduled for deletion. Check email to cancel."
- [x] Requesting deletion twice resets the 30-day timer and resends the email
- [x] After 30 days, account and all data (notes, files) are permanently deleted
- [x] Admin hard-delete bypasses the grace period entirely
- [x] Deactivated accounts still block email re-registration during grace period

**Technical Acceptance Criteria**
- [x] `scheduled_deletion_at`, `deletion_recovery_token` fields added to `User` model
- [x] `DELETE /api/auth/delete-account/` updated to soft delete — sets `scheduled_deletion_at`, blacklists sessions, sends email
- [x] `POST /api/auth/recover-account/:token/` endpoint — clears deletion fields, restores `is_active`
- [x] Login view handles `is_pending_deletion` with specific error message
- [x] `purge_deleted_accounts` management command deletes expired accounts + files
- [ ] Cron job scheduled to run `purge_deleted_accounts` daily on Render
- [x] `pages/auth/recover-account/[token].vue` created
- [x] Delete account confirmation dialog updated to show 30-day grace period info
- [x] `/auth/recover-account` added to public middleware paths
- [ ] Admin user list shows visual indicator for accounts pending deletion

---

## Non-Functional Requirements

| Requirement | Criteria |
|-------------|----------|
| Performance | Folder switch completes in < 300ms on a standard connection |
| Offline | Folder creation/rename queued and synced on reconnect |
| Accessibility | Sidebar navigable via keyboard; all interactive elements have accessible labels |
| Mobile | Sidebar gesture does not conflict with existing swipe gestures |
| Data integrity | No notes are ever silently deleted during folder operations |
| Migration | All existing users migrated to default folders without data loss or UX disruption |
| Backward compatibility | All existing note features (pin, color, audio, image, link preview) work unchanged within folders |
