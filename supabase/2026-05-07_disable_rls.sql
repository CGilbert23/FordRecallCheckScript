-- Fix: writes to schedules were failing with
--   "new row violates row-level security policy for table \"schedules\""
--   (Postgres error 42501)
--
-- The schedules + schedule_runs tables had RLS enabled (likely auto-toggled
-- by Supabase when the table was first created via the dashboard) but no
-- policy that lets the anon key insert. This app has no per-user auth, so
-- RLS just blocks legitimate writes. The accounts/account_leads tables were
-- created without RLS, hence why they always worked — this brings the
-- recall tables into line with the rest of the schema.
--
-- Run once on the existing project. New projects created from supabase/
-- schema.sql don't auto-enable RLS, so this isn't part of the base schema.

alter table schedules disable row level security;
alter table schedule_runs disable row level security;
