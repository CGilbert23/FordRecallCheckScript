-- One-time recall runs: persists the run log for ad-hoc /submit jobs so it
-- survives container restarts. The legacy in-memory `jobs` dict in app.py is
-- still used for live progress polling, but the run-log page reads from here.
-- `vins` is stored as a text[] so users can open a row and copy/re-run the
-- exact list later.

create table one_time_runs (
  id uuid primary key default gen_random_uuid(),
  job_id text not null,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  status text not null default 'queued' check (status in (
    'queued', 'starting', 'running', 'complete', 'error'
  )),
  vin_count integer not null default 0,
  vins text[] not null default '{}',
  recalls_found integer,
  customer_name text,
  output_file text,
  email text,
  email_sent boolean,
  error text
);

create index one_time_runs_started_at_idx on one_time_runs(started_at desc);
create index one_time_runs_job_id_idx on one_time_runs(job_id);
