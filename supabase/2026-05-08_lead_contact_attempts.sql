-- Migration: track cold-lead contact attempts and a soft-close for
-- "not interested" outcomes.
--
-- - last_attempt_at / last_attempt_outcome — most recent phone touch on a
--   cold lead (made_contact or left_voicemail). We only keep the latest
--   touch; a separate history table would be overkill for this workflow.
-- - closed_at / closed_reason — soft-close so leads we stop pursuing
--   disappear from the cold list (mirrors how converted_at hides
--   converted leads) without losing the row.

alter table account_leads
  add column last_attempt_at date,
  add column last_attempt_outcome text
    check (last_attempt_outcome is null or last_attempt_outcome in ('made_contact', 'left_voicemail')),
  add column closed_at timestamptz,
  add column closed_reason text;

create index account_leads_closed_at_idx on account_leads(closed_at);
