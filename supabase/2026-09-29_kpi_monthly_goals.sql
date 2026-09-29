-- Monthly Goals (Performance Tracking > Monthly Goals): one place that defines
-- a month's targets. Both the KPI Tracker and the EOS Scorecard read from it.
--   stores = {P&A code: {active_techs, forecast}}
--     active_techs -- Ford doesn't supply it, so it's typed here; it drives the
--     KPI Tracker's per-tech-per-day maths (it used to live in
--     kpi_reports.settings, edited on the tracker itself).
--     forecast -- that store's RO Count goal for the month.
--   goals = {avg_ro_value, commercial_mix} -- the two company-wide goals that
--     aren't per store (they used to be typed on the Scorecard).
-- One row per month, carried forward: a month with no row inherits the newest
-- earlier one, so past months keep the figures they were judged on. Van Count
-- is NOT here -- that stays Ford's Launched Vans. Offset Value is no longer
-- editable at all; it's the per-store constant in kpi_tracker.STORES.

create table kpi_monthly_goals (
  id uuid primary key default gen_random_uuid(),
  period_start date not null unique,
  stores jsonb not null default '{}'::jsonb,
  goals jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);
