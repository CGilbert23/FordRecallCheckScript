-- Free-text notes per key. Surfaced as a textarea on the add/edit form and
-- as a hover popover (notepad icon next to the customer name) on the Key
-- Database list page when non-empty.
alter table mobile_keys
  add column if not exists notes text;
