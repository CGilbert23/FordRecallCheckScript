-- Add per-row "Key Code" tracking to mobile_keys.
-- Two columns, both surfaced via the "Key Code" checkbox column (between
-- Ordered and Complete) on the list page:
--   key_code        - boolean checkbox state ("we have the key code")
--   key_code_value  - the actual key code text, entered via a modal that
--                     opens when the checkbox is clicked
-- Default false / null. Unlike the ordered migration, existing rows are NOT
-- backfilled -- this is a new workflow step, so every row starts unchecked.

alter table mobile_keys
  add column if not exists key_code boolean not null default false,
  add column if not exists key_code_value text;
