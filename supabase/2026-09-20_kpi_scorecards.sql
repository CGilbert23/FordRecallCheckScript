-- EOS Scorecard (Tech Performance > KPI Tracker > EOS Scorecard).
--
-- 1. kpi_report_weeks: one row per *weekly* Ford KPI upload, so the scorecard
--    can show a column per Monday. `kpi_reports` keeps only the newest
--    snapshot per month (each upload replaces it); this table keeps them all.
--    `as_of` is the date in the file name (the Monday it was sent), which is
--    the scorecard's column header. Re-uploading a week replaces that column.
-- 2. kpi_scorecards: the hand-entered half of the scorecard for one month --
--    `goals` {row key: number}, `notes` {row key: text}, and `manual`
--    {as_of date: {vans, techs}} for the two forward-looking Tracking cells
--    (vans on order, techs being hired) that no report can know.
--    A month with no row yet inherits the previous month's goals on screen.

create table kpi_report_weeks (
  id uuid primary key default gen_random_uuid(),
  period_start date not null,
  as_of date not null,
  days_elapsed int not null,
  work_days int not null,
  filename text,
  stores jsonb not null default '[]'::jsonb,
  uploaded_at timestamptz not null default now(),
  unique (period_start, as_of)
);
create index kpi_report_weeks_period_idx on kpi_report_weeks (period_start);

create table kpi_scorecards (
  id uuid primary key default gen_random_uuid(),
  period_start date not null unique,
  goals jsonb not null default '{}'::jsonb,
  notes jsonb not null default '{}'::jsonb,
  manual jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);
