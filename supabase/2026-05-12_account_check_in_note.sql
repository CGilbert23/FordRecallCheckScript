-- Migration: add check_in_note to accounts.
--
-- Optional free-text note paired with last_checked_in_at. Editable
-- independently of the check-in date (reps can update the note without
-- bumping the date, and vice versa). Nullable, no default.

alter table accounts add column check_in_note text;
