-- Mobile keys: add a "Closed" tracking checkbox (the RO has been closed out).
-- Sits after Complete on the Key Database: Ordered, Key Code, Complete, Closed.
-- No backfill -- existing rows start unchecked.
alter table mobile_keys
  add column if not exists ro_closed boolean not null default false;
