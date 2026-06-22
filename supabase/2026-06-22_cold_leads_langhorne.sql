-- Migration: add Langhorne as its own Xtime follow-up tab. Langhorne was
-- previously folded into Newtown (see 2026-06-17_cold_leads_split_markets.sql);
-- this reintroduces it as a standalone market. Final tab set:
-- Doylestown, Exton, Langhorne, Newtown, Mechanicsburg, Washington.
-- Existing rows are untouched — Langhorne simply becomes a valid value.

alter table cold_leads drop constraint cold_leads_market_check;

alter table cold_leads
  add constraint cold_leads_market_check
  check (market in (
    'Doylestown', 'Exton', 'Langhorne', 'Newtown', 'Mechanicsburg', 'Washington'
  ));
