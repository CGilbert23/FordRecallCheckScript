-- Migration: split the two combined Xtime follow-up tabs back into
-- individual stores. Newtown/Langhorne folds to Newtown, and
-- West Chester/Exton folds to Exton (West Chester is dropped). Final
-- tab set: Doylestown, Exton, Newtown, Mechanicsburg, Washington.

alter table cold_leads drop constraint cold_leads_market_check;

update cold_leads
   set market = 'Newtown'
 where market = 'Newtown/Langhorne';

update cold_leads
   set market = 'Exton'
 where market in ('West Chester/Exton', 'West Chester');

alter table cold_leads
  add constraint cold_leads_market_check
  check (market in (
    'Doylestown', 'Exton', 'Newtown', 'Mechanicsburg', 'Washington'
  ));
