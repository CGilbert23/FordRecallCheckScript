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
  cadence text not null check (cadence in ('daily', 'weekly', 'monthly', 'quarterly')),
  vins text not null,
  vin_units jsonb,
  recipients text[] not null default '{}',
  active boolean not null default true,
  account_id uuid,  -- FK constraint added after `accounts` is created below
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
  vins text,
  notes text,
  last_checked_in_at timestamptz,
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
  lead_source text check (lead_source is null or lead_source in ('Sales', 'Service', 'Visual', 'Other')),
  lead_source_other text,
  notes text,
  lead_type text not null default 'cold' check (lead_type in ('cold', 'warm')),
  last_contacted_at date,
  interest_level text not null default 'Y' check (interest_level in ('R', 'Y', 'G')),
  converted_at timestamptz,
  converted_account_id uuid references accounts(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index account_leads_account_rep_idx on account_leads(account_rep);
create index account_leads_lead_type_idx on account_leads(lead_type);
create trigger account_leads_updated_at
  before update on account_leads
  for each row execute function set_updated_at();

-- Wire the schedule -> account FK now that `accounts` exists.
alter table schedules
  add constraint schedules_account_id_fkey
  foreign key (account_id) references accounts(id) on delete set null;
create index schedules_account_id_idx on schedules(account_id);
