-- Migration: combine Newtown + Langhorne into a single market tab and add
-- a new West Chester/Exton tab. Mirrors how the team actually divvies up
-- the Xtime follow-up workload — Newtown and Langhorne share a rep, and
-- West Chester/Exton was missing from the original 5.

alter table cold_leads drop constraint cold_leads_market_check;

update cold_leads
   set market = 'Newtown/Langhorne'
 where market in ('Newtown', 'Langhorne');

alter table cold_leads
  add constraint cold_leads_market_check
  check (market in (
    'Doylestown', 'Newtown/Langhorne', 'Mechanicsburg', 'Washington', 'West Chester/Exton'
  ));
