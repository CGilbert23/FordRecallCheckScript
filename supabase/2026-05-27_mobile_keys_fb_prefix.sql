-- Rename the internal-dealership customer names in mobile_keys to use the
-- "FB " (Fred Beans) prefix so they read as Fred Beans dealerships rather
-- than the bare brand name. Only touches rows where end_user = 'Internal'
-- — external Customer rows that happen to type "Ford" or "Toyota" are
-- left alone. 'Bid Lot' is not a dealership and stays as-is.

update mobile_keys set customer_name = 'FB Chevrolet'
  where end_user = 'Internal' and customer_name = 'Chevrolet';
update mobile_keys set customer_name = 'FB CDJR'
  where end_user = 'Internal' and customer_name = 'CDJR';
update mobile_keys set customer_name = 'FB Hyundai'
  where end_user = 'Internal' and customer_name = 'Hyundai';
update mobile_keys set customer_name = 'FB Lincoln'
  where end_user = 'Internal' and customer_name = 'Lincoln';
update mobile_keys set customer_name = 'FB Ford'
  where end_user = 'Internal' and customer_name = 'Ford';
update mobile_keys set customer_name = 'FB Subaru'
  where end_user = 'Internal' and customer_name = 'Subaru';
update mobile_keys set customer_name = 'FB Toyota'
  where end_user = 'Internal' and customer_name = 'Toyota';
