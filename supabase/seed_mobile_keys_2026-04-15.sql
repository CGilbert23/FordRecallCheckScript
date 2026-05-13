-- One-time seed for the mobile_keys table — adds 5 keys cut on 2026-04-15
-- that weren't in the original Excel mock.
--
-- Cleanups applied to match the dropdowns in db.py:
--   Make:   "Chevy"    -> "Chevrolet"
--   Model:  "Slverado" -> "Silverado"   (typo in the source data)
--   "--" RO numbers    -> NULL
-- Programming cost falls back to the table default ($60.00); offset_eligible
-- defaults to true. Run AFTER 2026-05-12_mobile_keys.sql.
-- Not idempotent — re-running will create duplicates.

insert into mobile_keys (
  cut_date, end_user, customer_name, ro_number, vin, year, make, model, key_type,
  key_fob_part_number, key_fob_cost, key_blank_part_number, key_blank_cost
) values
  ('2026-04-15', 'Internal', 'Chevrolet', null,     '5TDKDRBHXPS010062', 2023, 'Toyota',    'Highlander',  'Fob', '8990H-0E370',   135.62, '69515-16110',  24.19),
  ('2026-04-15', 'Internal', 'Chevrolet', '314276', '1HGCV1F33NA117418', 2022, 'Honda',     'Accord',      'Fob', '72147-TVA-A12',  84.88, '35118-T2A-A50', 28.63),
  ('2026-04-15', 'Internal', 'Chevrolet', '314277', '1GB3YSE70PF240782', 2023, 'Chevrolet', 'Silverado',   'Fob', '13577765',       64.17, '13523912',      37.09),
  ('2026-04-15', 'Internal', 'Chevrolet', '314275', 'KL79MUSL1PB142623', 2023, 'Chevrolet', 'Trailblazer', 'Fob', '13547830',       94.30, '13523213',      52.18),
  ('2026-04-15', 'Internal', 'Hyundai',   '314121', '5NPEC4AC9DH629746', 2013, 'Hyundai',   'Sonata',      'Fob', '95440-3Q000',   352.32, '81996-3S020',   19.82);
