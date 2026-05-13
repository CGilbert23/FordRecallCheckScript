-- Migration: add a per-row "done" status flag to mobile_keys.
--
-- The Key Database list now has a leftmost Status column with a checkbox.
-- Unchecked rows render with a light-grey background so it's easy to spot
-- which keys still need follow-up. Default for new rows is false (pending).
--
-- Existing rows are historical / already-completed work, so we backfill
-- them all to done = true. New inserts after this migration default to
-- false.

alter table mobile_keys
  add column status_done boolean not null default false;

update mobile_keys set status_done = true;
