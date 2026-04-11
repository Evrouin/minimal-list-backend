# Reminders & Task Completion — Feature Proposal

## Overview

Elevate reminders from a one-shot timestamp into a full lifecycle feature with recurrence, snooze, and completion-driven dismissal. Tie the `completed` state to notes that actually need it — tasks and reminders — and remove it from plain notes where it serves no purpose.

---

## Completed State Rules

| Context | Completed State | Behavior |
|---------|----------------|----------|
| Plain note (no reminder, not in tasks folder) | **Hidden** | Notes just exist until deleted |
| Task (in tasks folder) | **Required** | Checkmark is the primary action |
| Note with reminder set | **Available** | Completing dismisses/resolves the reminder |

The complete button on `TodoCard` only renders when:
- The note is in the **tasks** folder, OR
- The note has a `reminder_at` value set

---

## Reminder Lifecycle

```
create note → set reminder → reminder fires
                                  ↓
                         ┌────────────────┐
                         │  user action   │
                         └────────────────┘
                          ↓        ↓       ↓
                       snooze   complete  ignore
                          ↓        ↓       ↓
                    re-fires    dismissed  re-fires at
                    after delay  (recurrence  next recurrence
                                  stops)
```

---

## Recurrence

### Options
- **none** (current behavior — one-shot)
- **daily**
- **weekly** (same day of week)
- **monthly** (same day of month)
- **custom** (every N days/weeks — v2)

### Behavior
- On each recurrence, the note's `reminder_at` advances to the next occurrence
- Completing the note stops recurrence and marks it done
- Ignoring (not acting on notification) re-fires at the next scheduled time
- Deleting the note cancels all future recurrences

### Backend
- Add `recurrence_rule` field: `none | daily | weekly | monthly`
- Add `next_reminder_at` computed/stored field for the next fire time
- On completion: set `completed = true`, clear `reminder_at`, clear recurrence
- On recurrence advance: update `reminder_at` to next occurrence, keep `completed = false`

---

## Snooze

### Options (shown in notification and in-app)
- 15 minutes
- 1 hour
- Tomorrow (same time)
- Pick a time (opens ReminderPicker)

### Backend
- Add `snoozed_until` field (nullable datetime)
- Snooze sets `snoozed_until`, suppresses notification until that time
- On snooze expiry, notification re-fires

### Frontend
- `useReminders.ts` checks `snoozed_until` in polling loop
- Android: notification action buttons ("snooze 1hr", "done") via Capacitor local notifications
- Web: snooze via in-app toast action after notification fires

---

## Overdue State

Notes with `reminder_at` in the past and `completed = false` are **overdue**.

### Visual treatment
- Red bell icon on card
- Subtle red tint on card border or background
- Overdue notes float to top of reminders folder (optional sort)

### Backend
- No new field needed — derived from `reminder_at < now && !completed`
- API can return `is_overdue` computed field for convenience

---

## Upcoming View

The **reminders** default folder (from sidebar proposal) shows notes with `reminder_at` set, sorted by upcoming time ascending.

```
reminders folder:
  ┌─────────────────────────────┐
  │ 🔴 overdue (2)              │  ← overdue group at top
  │   · buy groceries  2d ago   │
  │   · call dentist   1w ago   │
  ├─────────────────────────────┤
  │ today                       │
  │   · team standup   3:00 PM  │
  ├─────────────────────────────┤
  │ tomorrow                    │
  │   · submit report  9:00 AM  │
  └─────────────────────────────┘
```

This replaces the current flat masonry grid for the reminders folder — a timeline list view is more appropriate here than a masonry grid.

---

## Task Completion

Tasks (notes in the tasks folder) use completion as their primary action:

- Complete button always visible on task cards (not hidden behind hover)
- Completed tasks visually struck through or dimmed
- Completed tasks can be filtered out (show active only) — toggle in tasks folder header
- No reminder required — completion is standalone

### Checklist items (future — Phase 4)
- Individual checklist items within a task note
- Note auto-completes when all items are checked
- Deferred to a later phase

---

## UI Changes

### ReminderPicker
- Add recurrence selector: none / daily / weekly / monthly
- Add snooze options after reminder fires (in-app prompt or toast)

### TodoCard
- Complete button: only shown for tasks and notes with reminders
- Overdue indicator: red bell icon when `reminder_at` is past
- Recurrence indicator: small repeat icon when recurrence is set

### Reminders Folder View
- Timeline list layout instead of masonry grid
- Grouped by: overdue / today / tomorrow / this week / later
- Sort by `reminder_at` ascending

### Tasks Folder View
- Complete button always visible (not hover-only)
- Optional "hide completed" toggle

---

## Backend Impact

### New Fields on Note
| Field | Type | Description |
|-------|------|-------------|
| `recurrence_rule` | enum | `none \| daily \| weekly \| monthly` |
| `snoozed_until` | datetime (nullable) | suppress notifications until |
| `reminder_status` | enum | `pending \| snoozed \| dismissed \| completed` |

### New Endpoints
- `POST /api/notes/:id/snooze/` — set `snoozed_until`
- `POST /api/notes/:id/dismiss-reminder/` — dismiss without completing
- Existing `PATCH /api/notes/:id/` handles recurrence_rule updates

### Migration
- All existing notes: `recurrence_rule = none`, `reminder_status = pending` (if has reminder) or null
- Non-breaking

---

## Frontend Impact

### High Impact
- **`ReminderPicker.vue`** — add recurrence UI, snooze options
- **`useReminders.ts`** — recurrence calculation, snooze polling, overdue detection
- **`TodoCard.vue`** — conditional complete button, overdue indicator, recurrence badge
- **`TodoList.vue`** — timeline layout for reminders folder

### Medium Impact
- **`useTodoApi.ts`** — snooze and dismiss endpoints
- **`stores/todos.ts`** — overdue computed state
- **`types/todo.d.ts`** — new fields

### Low Impact
- **`plugins/reminders.client.ts`** — handle snooze re-scheduling in web polling
- **Android notifications** — add action buttons (snooze/done) via Capacitor

---

## Edge Cases

- **Recurring reminder + note deleted** — cancel all future recurrences on delete
- **Snooze past next recurrence** — snooze wins; next recurrence calculated from snooze expiry
- **Complete a recurring reminder** — stops recurrence entirely, marks done
- **Reminder set on a plain note, then moved to tasks folder** — both reminder and task completion apply
- **Note moved out of tasks folder** — complete button hides if no reminder set
- **Overdue + recurring** — show as overdue, advance to next occurrence on dismiss
- **Multiple snoozes** — each snooze replaces the previous `snoozed_until`
- **Web tab closed during snooze** — snooze state is server-side; re-fires correctly when tab reopens
- **Android app killed during snooze** — local notification rescheduled on app open via `getLaunchUrl` check

---

## Migration Strategy

### Phase 1 — Completed state rules
1. Hide complete button on plain notes (no reminder, not in tasks folder)
2. Always show complete button on task cards
3. No backend changes needed

### Phase 2 — Overdue state
4. Add overdue visual treatment to cards with past `reminder_at`
5. Sort reminders folder by `reminder_at`

### Phase 3 — Recurrence
6. Add `recurrence_rule` to backend + frontend
7. Update `ReminderPicker` with recurrence selector
8. Update `useReminders.ts` for recurrence advancement

### Phase 4 — Snooze
9. Add snooze endpoint + `snoozed_until` field
10. Android notification action buttons
11. Web in-app snooze prompt

### Phase 5 — Checklist items (tasks)
12. Inline checklist editor in task notes
13. Auto-complete note when all items checked

---

## Recommendation

**Phase 1 + 2** are low effort and immediately improve UX — hide the useless complete button on plain notes and add overdue visual treatment. These can ship alongside the folders/sidebar milestone.

**Phase 3 (recurrence)** is the highest-value addition and should be the next dedicated milestone after folders.
