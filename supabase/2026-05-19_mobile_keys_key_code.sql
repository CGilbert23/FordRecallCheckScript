-- Add per-row "Key Code" flag to mobile_keys.
-- Mirrors status_done / ordered: a boolean toggled by a checkbox in the list
-- view. Column order in the UI is Ordered, Key Code, Complete.
-- Default false (key code not yet obtained). Unlike the ordered migration,
-- existing rows are NOT backfilled -- this is a new workflow step, so every
-- row starts unchecked.

alter table mobile_keys
  add column if not exists key_code boolean not null default false;
