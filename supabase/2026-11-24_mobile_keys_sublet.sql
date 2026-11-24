-- Mobile keys: "Sublet" -- another dealership did the key programming, but
-- the job still got done. Unlike Unable, a sublet key still counts in the
-- Analytics totals. The app keeps sublet and unable mutually exclusive.
alter table mobile_keys
  add column if not exists sublet boolean not null default false;
