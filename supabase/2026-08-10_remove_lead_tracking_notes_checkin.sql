-- Retire the Lead Tracking (Xtime follow-up) page, the shared Notes
-- scratchpad, and the account check-in / lead-source fields. The app no
-- longer reads or writes any of these.
--
-- DESTRUCTIVE: this deletes data permanently and cannot be undone. Export
-- cold_leads and notepad from Supabase first if you want to keep them.
--
-- Run this AFTER deploying the matching code. The old code writes
-- accounts.lead_source on every save, so running it against a running old
-- container breaks account saves until the deploy lands.

-- Each drop also removes the table's indexes and updated_at trigger.
drop table if exists cold_leads;
drop table if exists notepad;

-- Dropping lead_source takes its CHECK constraint with it.
alter table accounts
  drop column if exists last_checked_in_at,
  drop column if exists check_in_note,
  drop column if exists lead_source,
  drop column if exists lead_source_other,
  drop column if exists source_contact;
