-- Optional person attached to an Internal key — e.g. the car was already sold and
-- the key gets cut at the buyer's house. The store is still who gets billed, but
-- the tech needs to know whose car it is. Displayed as "FB Chevrolet - Mark Macy"
-- on the Key Database and Inventory lists; blank falls back to just the store.
alter table mobile_keys
  add column if not exists internal_contact text;
