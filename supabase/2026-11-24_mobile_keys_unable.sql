-- Mobile keys: "Mark Unable" -- we had the key, tried everything, it didn't
-- work. The row shows light red on the Key Database and is left out of the
-- Analytics totals (listed in its own Unable section, since we eat the cost).
alter table mobile_keys
  add column if not exists unable boolean not null default false;
