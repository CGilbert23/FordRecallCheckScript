-- Migration: create mobile_keys table for the Key Database under the new
-- Mobile Keys section. One row per key cut by the mobile service team —
-- captures who it was for, the vehicle, parts + costs, and a flag for
-- whether the parts cost is offset-eligible. Derived totals (parts total,
-- final charge, etc.) are computed in the app, not stored.

create table mobile_keys (
  id uuid primary key default gen_random_uuid(),
  cut_date date not null,
  end_user text not null check (end_user in ('Internal', 'Customer')),
  customer_name text not null,
  ro_number text,
  vin text not null,
  year integer not null check (year between 2000 and 2100),
  make text not null,
  model text not null,
  key_type text not null check (key_type in ('Fob', 'Turnkey', 'Flip Key')),
  key_fob_part_number text,
  key_fob_cost numeric(10, 2),
  key_blank_part_number text,
  key_blank_cost numeric(10, 2),
  programming_cost numeric(10, 2) not null default 60.00,
  offset_eligible boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index mobile_keys_cut_date_idx on mobile_keys(cut_date desc);
create index mobile_keys_vin_idx on mobile_keys(vin);

create trigger mobile_keys_updated_at
  before update on mobile_keys
  for each row execute function set_updated_at();
