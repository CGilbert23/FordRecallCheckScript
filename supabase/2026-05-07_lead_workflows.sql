-- Migration: split account_leads into cold-call and warm-prospect workflows.
--
-- A single table, with a lead_type discriminator. Cold leads are the existing
-- cold-call list. Warm prospects are leads we're actively engaged with and get
-- two extra fields: last_contacted_at and interest_level (R/Y/G, default Y).
-- All existing rows default to 'cold' so behavior is preserved on rollout.

alter table account_leads
  add column lead_type text not null default 'cold' check (lead_type in ('cold', 'warm')),
  add column last_contacted_at date,
  add column interest_level text not null default 'Y' check (interest_level in ('R', 'Y', 'G'));

create index account_leads_lead_type_idx on account_leads(lead_type);
