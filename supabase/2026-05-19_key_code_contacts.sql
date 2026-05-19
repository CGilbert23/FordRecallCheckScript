-- Key Code Contacts: backs the new "Key Code Contacts" page under Mobile Keys.
-- A small free-text reference table so the team knows who to reach out to at
-- each store for a key code. One row per contact; every column is free text
-- and nullable (rows are typed in inline, spreadsheet-style).

create table key_code_contacts (
  id uuid primary key default gen_random_uuid(),
  store text,
  name text,
  email text,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create trigger key_code_contacts_updated_at
  before update on key_code_contacts
  for each row execute function set_updated_at();
