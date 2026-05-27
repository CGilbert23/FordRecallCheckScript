-- Allow mobile_keys.cut_date to be NULL so reps can log a key before the
-- appointment has been scheduled. The Key Database list shows an em-dash
-- when cut_date is NULL.

alter table mobile_keys
  alter column cut_date drop not null;
