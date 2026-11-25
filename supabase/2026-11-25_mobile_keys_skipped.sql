-- Mobile keys: "Skipped" -- a key we never ordered because we already knew we
-- couldn't do it. Shown in its own Skipped table under the Key Database (white,
-- boxes left unticked) and left out of Analytics. The app keeps skipped,
-- unable and sublet mutually exclusive.
alter table mobile_keys
  add column if not exists skipped boolean not null default false;
