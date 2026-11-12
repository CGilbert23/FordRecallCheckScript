-- Mobile keys: add Source (where the key job came from).
-- RS = route sheet, UCM = used car manager, Sales. Existing rows get UCM.
alter table mobile_keys
  add column if not exists source text not null default 'UCM'
  check (source in ('RS', 'UCM', 'Sales'));
