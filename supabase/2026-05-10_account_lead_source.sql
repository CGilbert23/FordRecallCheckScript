-- Migration: bring lead_source onto accounts so converted leads keep that
-- context and existing accounts can record where the business originated.
--
-- Mirrors the same three columns that already exist on account_leads:
--   - lead_source       : enum (Sales/Service/Parts/Visual/Other), nullable
--   - lead_source_other : free text, only meaningful when lead_source = 'Other'
--   - source_contact    : free text, only meaningful for Sales/Service/Parts
--
-- App-level rules (clearing fields when they're not applicable) match the
-- lead form so the columns stay clean.

alter table accounts
  add column lead_source text
    check (lead_source is null or lead_source in ('Sales', 'Service', 'Parts', 'Visual', 'Other')),
  add column lead_source_other text,
  add column source_contact text;
