-- Xtime Tech Report: one row per uploaded month of the Xtime "Technician RO /
-- ASR Report Totals" export (Tech Performance > Xtime Tech Report).
-- `techs` holds every technician parsed from the file (store, name, total_ro,
-- mpi_completed, avg_miles, lines_requested, lines_sold) -- not just the
-- mobile techs -- so a roster change applies to months already uploaded.
-- One row per month: re-uploading a month replaces it (upsert on period_start).

create table xtime_tech_reports (
  id uuid primary key default gen_random_uuid(),
  period_start date not null unique,
  period_end date not null,
  filename text,
  techs jsonb not null default '[]'::jsonb,
  uploaded_at timestamptz not null default now()
);
