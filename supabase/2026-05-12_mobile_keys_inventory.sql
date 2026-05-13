-- Migration: add an inventory flag to mobile_keys.
--
-- When a customer no longer wants a key we've ordered for them, we mark the
-- key as "moved to inventory" rather than deleting the record — so we keep
-- the full history but also have a separate view of unsold parts on hand.
--
-- NULL = active key (sold/used); non-NULL = the timestamp it was moved into
-- inventory.

alter table mobile_keys
  add column moved_to_inventory_at timestamptz;

-- Partial index — only inventory rows. Tiny on the active dataset, so we
-- skip indexing the much larger NULL set.
create index mobile_keys_inventory_idx
  on mobile_keys(moved_to_inventory_at desc)
  where moved_to_inventory_at is not null;
