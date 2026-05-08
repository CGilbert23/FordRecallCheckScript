-- Migration: store a free-text note alongside the latest contact attempt.
-- Reps now must enter a note when they log a "made contact" attempt; the
-- column stays null for voicemail outcomes.

alter table account_leads
  add column last_attempt_note text;
