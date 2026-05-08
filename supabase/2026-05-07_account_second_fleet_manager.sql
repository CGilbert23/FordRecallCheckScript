-- Migration: add second fleet manager fields to accounts.
--
-- Some customers have two fleet manager contacts. Add an optional second set
-- of name/email/phone columns. All nullable, so existing rows are unaffected.

alter table accounts
  add column fleet_manager_2 text,
  add column fleet_manager_2_email text,
  add column fleet_manager_2_phone text;
