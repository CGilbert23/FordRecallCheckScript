-- Migration: cold_leads table backs the Xtime Follow Up Calls page
-- (formerly the SharePoint embed at /cold-leads). Each row is one prospect
-- the team plans to call. The market is one of the 5 stores that run the
-- Xtime follow-up workflow. lead_date is when the lead came in (e.g. Xtime
-- appointment date); contact_date is when we actually reached them.
-- hot_lead = true paints the row green in the UI so reps can flag
-- promising contacts for follow-up.

create table cold_leads (
  id uuid primary key default gen_random_uuid(),
  market text not null check (market in (
    'Doylestown', 'Newtown', 'Langhorne', 'Mechanicsburg', 'Washington'
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
