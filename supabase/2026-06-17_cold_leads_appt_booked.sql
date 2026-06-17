-- Migration: add an "Appt Booked?" flag to cold_leads. Surfaced as a second
-- checkbox column (next to Hot?) in the Hot Prospects table on /cold-leads.
-- A hot row with no appointment tints yellow; checking appt_booked turns it green.

alter table cold_leads
  add column if not exists appt_booked boolean not null default false;
