-- Migration: extend account_leads for the Parts source + a source contact
-- (salesperson or parts rep name) and an optional fleet manager name/email
-- on warm prospects.
--
-- 1. Expand the lead_source check to allow 'Parts'.
-- 2. Add source_contact (free text) — only meaningful when lead_source is
--    Sales or Parts; cleared by the app for other sources.
-- 3. Add fleet_manager + fleet_manager_email (free text) — used on warm
--    prospects; either may be null when we don't yet have that detail.

alter table account_leads
  drop constraint if exists account_leads_lead_source_check;

alter table account_leads
  add constraint account_leads_lead_source_check
  check (lead_source is null or lead_source in ('Sales', 'Service', 'Parts', 'Visual', 'Other'));

alter table account_leads
  add column source_contact text,
  add column fleet_manager text,
  add column fleet_manager_email text;
