-- Migration: shared scratchpad table for the Notes page under Account Management.
-- Single-row pattern: the CHECK constraint pins the row at id=1 so the app
-- always reads/writes the same row. No history kept — this is a freeform
-- scribble pad (write, reference, delete as needed).

create table if not exists notepad (
  id integer primary key default 1,
  content text not null default '',
  updated_at timestamptz not null default now(),
  constraint notepad_single_row check (id = 1)
);

insert into notepad (id, content) values (1, '') on conflict (id) do nothing;

create trigger notepad_updated_at
  before update on notepad
  for each row execute function set_updated_at();
