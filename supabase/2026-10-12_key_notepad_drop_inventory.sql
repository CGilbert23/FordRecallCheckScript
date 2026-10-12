-- Migration: replace the Mobile Keys Inventory page with a Key Notepad.
--
-- New process: a key we can't do is deleted from the Key Database and jotted
-- down on the notepad so nobody reorders it. The Inventory page, its rows and
-- the moved_to_inventory_at flag all go.
--
-- DESTRUCTIVE and order-sensitive: run it *after* the matching code is
-- deployed. The old code filters the Key Database on moved_to_inventory_at,
-- so dropping the column under a still-running old container breaks the page.
--
-- The deleted inventory keys are written onto the notepad first, one line
-- each, so the "don't reorder these" history isn't lost with the rows.

-- Single-row table: the whole notepad is one text body.
create table key_notepad (
  id smallint primary key default 1 check (id = 1),
  body text not null default '',
  updated_at timestamptz not null default now()
);
create trigger key_notepad_updated_at
  before update on key_notepad
  for each row execute function set_updated_at();

insert into key_notepad (id, body)
select 1, coalesce(string_agg(
  concat_ws(' - ',
    to_char(cut_date, 'FMMM/FMDD/YYYY'),
    concat_ws(' ', year, make, model),
    nullif(vin, ''),
    nullif(customer_name, ''),
    nullif(concat_ws(', ',
      nullif(concat_ws(' ', key_fob_part_number, '$' || key_fob_cost), ''),
      nullif(concat_ws(' ', key_blank_part_number, '$' || key_blank_cost), '')
    ), ''),
    nullif(notes, '')
  ),
  E'\n' order by moved_to_inventory_at
), '')
from mobile_keys
where moved_to_inventory_at is not null;

-- Prefix a heading when there was anything to carry over.
update key_notepad
set body = E'Moved from Inventory on 10/12/2026 (do not reorder):\n' || body
where id = 1 and body <> '';

delete from mobile_keys where moved_to_inventory_at is not null;

drop index if exists mobile_keys_inventory_idx;
alter table mobile_keys drop column moved_to_inventory_at;
