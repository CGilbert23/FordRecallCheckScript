-- 'FB Ford' is split into two stores: the existing rows are the Doylestown
-- store, renamed to 'FB Ford Doylestown'. 'FB Ford Washington' and 'FB GMC'
-- are new dropdown entries (db.KEY_INTERNAL_CUSTOMERS) and need no data change.
-- Only Internal rows are touched; free-text Customer rows are left alone.
-- Safe to re-run.

update mobile_keys set customer_name = 'FB Ford Doylestown'
  where end_user = 'Internal' and customer_name = 'FB Ford';
