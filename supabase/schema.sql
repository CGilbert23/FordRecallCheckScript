-- Supabase base schema for Fred Beans Mobile Service.
-- Run this in the Supabase SQL Editor when setting up a NEW project.
-- For an existing project, the tables below already exist — run any files in
-- this directory named `<date>_*.sql` instead, in chronological order.

-- Schedules: one row per recurring recall check
create table schedules (
  id uuid primary key default gen_random_uuid(),
  company_name text not null,
  location text not null check (location in (
    'Boyertown', 'Doylestown', 'Exton', 'Langhorne', 'Newtown',
    'Washington', 'West Chester', 'Mechanicsburg', 'Company-Wide'
  )),
  cadence text not null check (cadence in ('daily', 'monthly', 'quarterly')),
  vins text not null,
  vin_units jsonb,
  recipients text[] not null default '{}',
  active boolean not null default true,
  account_id uuid,  -- FK constraint added after `accounts` is created below
  -- First fire for monthly/quarterly schedules. The scheduler uses this as the
  -- start_date of an IntervalTrigger (every 30 or 90 days). NULL = legacy
  -- behavior (fire on the 1st of the month via a cron trigger).
  anchor_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Run log: one row per execution (scheduled or manual)
create table schedule_runs (
  id uuid primary key default gen_random_uuid(),
  schedule_id uuid not null references schedules(id) on delete cascade,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  vin_count integer not null default 0,
  recalls_found integer,
  email_sent boolean not null default false,
  error text,
  triggered_by text not null default 'scheduled' check (triggered_by in ('scheduled', 'manual'))
);

create index schedule_runs_schedule_id_idx on schedule_runs(schedule_id);
create index schedule_runs_started_at_idx on schedule_runs(started_at desc);

-- Keep updated_at fresh on edits
create or replace function set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create trigger schedules_updated_at
  before update on schedules
  for each row execute function set_updated_at();

-- Accounts: master record for an existing customer.
create table accounts (
  id uuid primary key default gen_random_uuid(),
  company_name text not null,
  market text not null check (market in (
    'Boyertown', 'Doylestown', 'Exton', 'Langhorne', 'Newtown',
    'Washington', 'West Chester', 'Mechanicsburg', 'Company-Wide'
  )),
  account_rep text not null,
  fleet_manager text,
  fleet_manager_email text,
  fleet_manager_phone text,
  fleet_manager_2 text,
  fleet_manager_2_email text,
  fleet_manager_2_phone text,
  service_type text not null check (service_type in ('Full Service', 'Recall Only')),
  lead_source text check (lead_source is null or lead_source in ('Sales', 'Service', 'Parts', 'Visual', 'Other')),
  lead_source_other text,
  source_contact text,
  vins text,
  notes text,
  last_checked_in_at timestamptz,
  check_in_note text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index accounts_account_rep_idx on accounts(account_rep);
create index accounts_market_idx on accounts(market);
create trigger accounts_updated_at
  before update on accounts
  for each row execute function set_updated_at();

-- Account leads: pre-customer prospects. Two workflows on one table:
--   lead_type = 'cold' — cold-call list (default for new rows)
--   lead_type = 'warm' — actively engaged prospects; uses last_contacted_at
--                        and interest_level (R/Y/G) for follow-up tracking.
create table account_leads (
  id uuid primary key default gen_random_uuid(),
  company_name text not null,
  market text not null,
  account_rep text not null,
  phone text,
  lead_source text check (lead_source is null or lead_source in ('Sales', 'Service', 'Parts', 'Visual', 'Other')),
  lead_source_other text,
  source_contact text,
  notes text,
  lead_type text not null default 'cold' check (lead_type in ('cold', 'warm')),
  last_contacted_at date,
  interest_level text not null default 'Y' check (interest_level in ('R', 'Y', 'G')),
  fleet_manager text,
  fleet_manager_email text,
  last_attempt_at date,
  last_attempt_outcome text check (last_attempt_outcome is null or last_attempt_outcome in ('made_contact', 'left_voicemail')),
  last_attempt_note text,
  closed_at timestamptz,
  closed_reason text,
  converted_at timestamptz,
  converted_account_id uuid references accounts(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index account_leads_account_rep_idx on account_leads(account_rep);
create index account_leads_lead_type_idx on account_leads(lead_type);
create index account_leads_closed_at_idx on account_leads(closed_at);
create trigger account_leads_updated_at
  before update on account_leads
  for each row execute function set_updated_at();

-- Wire the schedule -> account FK now that `accounts` exists.
alter table schedules
  add constraint schedules_account_id_fkey
  foreign key (account_id) references accounts(id) on delete set null;
create index schedules_account_id_idx on schedules(account_id);

-- Notepad: shared scratchpad behind the Notes page. Single-row table — the
-- CHECK constraint pins id=1 so the app always reads/writes the same row.
create table notepad (
  id integer primary key default 1,
  content text not null default '',
  updated_at timestamptz not null default now(),
  constraint notepad_single_row check (id = 1)
);
insert into notepad (id, content) values (1, '') on conflict (id) do nothing;
create trigger notepad_updated_at
  before update on notepad
  for each row execute function set_updated_at();

-- Mobile keys: one row per key cut by the mobile service team. Tracks the
-- vehicle, parts + costs, and offset eligibility. Derived totals (parts
-- total, discount, final charge) are computed in the app, not stored.
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
  -- NULL = active key. Non-NULL = timestamp it was moved into inventory
  -- (customer no longer needed it, but we keep the part on hand).
  moved_to_inventory_at timestamptz,
  -- Per-row "done" flag. Default false (pending); rep marks done via the
  -- leftmost "Complete" checkbox on the list page. Pending rows render grey.
  status_done boolean not null default false,
  -- Per-row "Ordered" flag. Toggled by the checkbox column next to Complete
  -- on the list page. Default false.
  ordered boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index mobile_keys_cut_date_idx on mobile_keys(cut_date desc);
create index mobile_keys_vin_idx on mobile_keys(vin);
create index mobile_keys_inventory_idx
  on mobile_keys(moved_to_inventory_at desc)
  where moved_to_inventory_at is not null;
create trigger mobile_keys_updated_at
  before update on mobile_keys
  for each row execute function set_updated_at();

-- Cold leads: backs the Xtime Follow Up Calls page. One row per prospect to
-- call. The 5 markets here are the subset that actually run the Xtime
-- follow-up workflow.
create table cold_leads (
  id uuid primary key default gen_random_uuid(),
  market text not null check (market in (
    'Doylestown', 'Newtown/Langhorne', 'Mechanicsburg', 'Washington', 'West Chester/Exton'
  )),
  name text,
  phone text,
  source text check (source is null or source in ('Xtime', 'Sales', 'Other')),
  lead_date date,
  contact_date date,
  notes text,
  hot_lead boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index cold_leads_market_idx on cold_leads(market, created_at);
create trigger cold_leads_updated_at
  before update on cold_leads
  for each row execute function set_updated_at();
