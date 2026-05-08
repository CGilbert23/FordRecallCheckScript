-- Migration: add last_checked_in_at to accounts.
--
-- Run this AFTER the existing 2026-05-07 migrations. Safe on existing data —
-- the column is nullable, so historical rows are treated as "never checked in"
-- (red X) on first page load.

alter table accounts add column last_checked_in_at timestamptz;
