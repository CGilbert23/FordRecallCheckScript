-- Add per-row "Ordered" flag to mobile_keys.
-- Mirrors status_done: a boolean toggled by a checkbox in the list view.
-- Default false (not yet ordered). Existing rows are historical/complete
-- so backfill them to true to match how they were tracked previously.

alter table mobile_keys
  add column if not exists ordered boolean not null default false;

update mobile_keys set ordered = true where ordered = false;
