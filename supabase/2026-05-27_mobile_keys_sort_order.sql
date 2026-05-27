-- Add manual sort_order to mobile_keys so reps can drag rows up/down on the
-- Key Database page. Pure manual order: sort_order asc is the only sort the
-- list query uses. New rows go to the top via min(sort_order) - 1 in app code.
--
-- Backfill assigns sort_order in the *current* visual order so the first
-- render after migration looks identical to today: not-done first
-- (status_done asc), newest cut_date first, then created_at desc as a
-- tiebreaker.

alter table mobile_keys
  add column if not exists sort_order integer not null default 0;

with ordered as (
  select id,
         row_number() over (
           order by status_done asc, cut_date desc, created_at desc
         ) as rn
  from mobile_keys
)
update mobile_keys mk
set sort_order = ordered.rn
from ordered
where mk.id = ordered.id;

create index if not exists mobile_keys_sort_order_idx
  on mobile_keys(sort_order);
