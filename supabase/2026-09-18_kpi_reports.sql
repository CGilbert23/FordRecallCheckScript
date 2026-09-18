-- KPI Tracker: one row per month of Ford's weekly mobile-service KPI export
-- (Tech Performance > KPI Tracker). Each weekly file is month-to-date, so a
-- re-upload of the same month replaces it (upsert on period_start).
-- `stores` keeps every Ford column raw ({code, name, region, raw: {...}}) so
-- a metric Ford adds later is already captured; `columns` maps the normalised
-- keys back to Ford's header text. `days_elapsed` is backed out of Ford's
-- ROs/Van/Day; `work_days` is the month's full working-day count.
-- `settings` = {store code: {active_techs, offset_value}} -- edited on the page,
-- seeded from the previous month, and left alone by re-uploads.

create table kpi_reports (
  id uuid primary key default gen_random_uuid(),
  period_start date not null unique,
  days_elapsed int not null,
  work_days int not null,
  filename text,
  columns jsonb not null default '{}'::jsonb,
  stores jsonb not null default '[]'::jsonb,
  settings jsonb not null default '{}'::jsonb,
  uploaded_at timestamptz not null default now()
);
