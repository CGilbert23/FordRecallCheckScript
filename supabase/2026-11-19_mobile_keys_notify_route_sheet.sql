-- Tell Route Sheet when a key's Complete box (status_done) is ticked or unticked, so the
-- car's key icon on the route sheet turns green (done) or back to orange.
--
-- Route Sheet's key-status-webhook edge function matches the row to a flagged car by
-- key_id (saved when Route Sheet created the row), falling back to VIN for older rows.
-- Keys with no flagged car on the route sheet are ignored there, so every row can call it.
--
-- Fire-and-forget through pg_net: a slow or failed call never blocks saving the checkbox.
--
-- BEFORE RUNNING: replace <KEY_STATUS_WEBHOOK_SECRET> with the value of Route Sheet's
-- KEY_STATUS_WEBHOOK_SECRET edge function secret. Do not commit the real value.
-- Safe to re-run.

create extension if not exists pg_net;

create or replace function notify_route_sheet_key_status()
returns trigger
language plpgsql
security definer
set search_path = public, extensions, net
as $$
begin
  perform net.http_post(
    url := 'https://qfiqqcrnskrpjzsowagf.supabase.co/functions/v1/key-status-webhook',
    body := jsonb_build_object(
      'key_id', new.id,
      'vin', new.vin,
      'status_done', new.status_done
    ),
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'x-webhook-secret', '<KEY_STATUS_WEBHOOK_SECRET>'
    ),
    timeout_milliseconds := 10000
  );
  return new;
end;
$$;

drop trigger if exists mobile_keys_notify_route_sheet on mobile_keys;

create trigger mobile_keys_notify_route_sheet
  after update of status_done on mobile_keys
  for each row
  when (old.status_done is distinct from new.status_done)
  execute function notify_route_sheet_key_status();
