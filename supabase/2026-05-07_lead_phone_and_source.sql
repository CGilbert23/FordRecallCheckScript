-- Migration: add phone + lead_source to account_leads.
--
-- Run this AFTER 2026-05-07_crm_expansion.sql. Safe on existing data —
-- both new columns are nullable, so historical rows stay valid.
--
-- `lead_source_other` holds the free-text description when `lead_source`
-- is 'Other'. The check constraint allows NULL so legacy rows pass.

alter table account_leads add column phone text;

alter table account_leads add column lead_source text
  check (lead_source is null or lead_source in ('Sales', 'Service', 'Visual', 'Other'));

alter table account_leads add column lead_source_other text;
