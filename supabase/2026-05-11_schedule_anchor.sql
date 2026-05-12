-- Migration: anchor recurring schedules to a creation-relative anchor date
-- instead of always firing on the 1st of the month / 1st of Jan/Apr/Jul/Oct.
--
-- - Adds nullable `anchor_at`. When set, the scheduler fires at that
--   timestamp and then on a fixed interval (30 days for monthly, 90 for
--   quarterly). When null, the scheduler falls back to the legacy
--   cron-on-the-1st behavior — so existing rows are unchanged.
-- - Drops `weekly` from the allowed cadence set. Any existing weekly rows
--   are converted to monthly first so the new CHECK constraint passes.

alter table schedules add column if not exists anchor_at timestamptz;

update schedules set cadence = 'monthly' where cadence = 'weekly';

alter table schedules drop constraint if exists schedules_cadence_check;
alter table schedules add constraint schedules_cadence_check
  check (cadence in ('daily', 'monthly', 'quarterly'));

-- Spread the five existing schedules across consecutive days near their next
-- "natural" fire date so they don't all run on the same morning. Once these
-- anchors are set, IntervalTrigger keeps each row on its own 30/90-day track.
update schedules set anchor_at = timestamp '2026-06-01 06:00:00' at time zone 'America/New_York'
  where id = '61337f47-b513-4bdb-8993-ca5a4a0b802e';  -- Plumstead Township Police (monthly)
update schedules set anchor_at = timestamp '2026-06-02 06:00:00' at time zone 'America/New_York'
  where id = 'dfaab71a-0e39-445a-b5e6-8b814257ff56';  -- Buckingham Police (monthly)
update schedules set anchor_at = timestamp '2026-07-01 06:00:00' at time zone 'America/New_York'
  where id = '81f40b7d-1b79-47f2-96d8-efde5f91febc';  -- Clint & Rachel Transportation (quarterly)
update schedules set anchor_at = timestamp '2026-07-02 06:00:00' at time zone 'America/New_York'
  where id = 'c7b36f3e-76cd-4771-9670-644804987d6d';  -- American Pile (quarterly)
update schedules set anchor_at = timestamp '2026-07-03 06:00:00' at time zone 'America/New_York'
  where id = 'd85b0666-568b-4998-b222-719dc2375707';  -- Bristol Township (quarterly)
