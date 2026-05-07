-- Migration: CRM expansion (accounts + leads, schedule->account FK,
-- GroupWide -> Company-Wide rename).
--
-- Run this ONCE in the Supabase SQL Editor on the existing project. It is
-- safe to paste the whole file in one go — every statement is sequential and
-- depends on the previous one. New projects don't need this file; they get
-- the same end state from `supabase/schema.sql`.

-- 1. Rename existing rows BEFORE swapping the check constraint, otherwise
--    the UPDATE itself would fail validation.
update schedules set location = 'Company-Wide' where location = 'GroupWide';

-- 2. Replace the location check constraint with the new value-set.
alter table schedules drop constraint schedules_location_check;
alter table schedules add constraint schedules_location_check
  check (location in (
    'Boyertown', 'Doylestown', 'Exton', 'Langhorne', 'Newtown',
    'Washington', 'West Chester', 'Mechanicsburg', 'Company-Wide'
  ));

-- 3. Accounts: master record for an existing customer.
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
  service_type text not null check (service_type in ('Full Service', 'Recall Only')),
  vins text,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index accounts_account_rep_idx on accounts(account_rep);
create index accounts_market_idx on accounts(market);
create trigger accounts_updated_at
  before update on accounts
  for each row execute function set_updated_at();

-- 4. Account leads: pre-customer prospects.
create table account_leads (
  id uuid primary key default gen_random_uuid(),
  company_name text not null,
  market text not null,
  account_rep text not null,
  notes text,
  converted_at timestamptz,
  converted_account_id uuid references accounts(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index account_leads_account_rep_idx on account_leads(account_rep);
create trigger account_leads_updated_at
  before update on account_leads
  for each row execute function set_updated_at();

-- 5. Optional link from a recall schedule to its parent account.
alter table schedules add column account_id uuid references accounts(id) on delete set null;
create index schedules_account_id_idx on schedules(account_id);
