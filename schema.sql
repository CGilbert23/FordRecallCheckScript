-- Supabase schema for CommercialAccount_RecallChecker
-- Run this in the Supabase SQL Editor when setting up a new project.

-- Schedules: one row per recurring recall check
create table schedules (
  id uuid primary key default gen_random_uuid(),
  company_name text not null,
  location text not null check (location in (
    'Doylestown', 'Boyertown', 'Newtown', 'Washington',
    'Exton', 'Langhorne', 'West Chester', 'Mechanicsburg', 'GroupWide'
  )),
  cadence text not null check (cadence in ('daily', 'weekly', 'monthly', 'quarterly')),
  vins text not null,
  vin_units jsonb,
  recipients text[] not null default '{}',
  active boolean not null default true,
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
