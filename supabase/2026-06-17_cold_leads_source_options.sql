-- Migration: broaden cold_leads.source options to Sales/Service/Parts/Xtime/Other
-- (was Xtime/Sales/Other). Powers the Source dropdown on the Lead Tracking page
-- (formerly "Xtime Follow Up Calls").

alter table cold_leads drop constraint if exists cold_leads_source_check;

alter table cold_leads
  add constraint cold_leads_source_check
  check (source is null or source in ('Sales', 'Service', 'Parts', 'Xtime', 'Other'));
