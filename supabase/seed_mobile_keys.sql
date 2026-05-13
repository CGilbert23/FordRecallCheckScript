-- One-time seed for the mobile_keys table — imports the 15 historical rows
-- from Mocks/Key_DB.xlsx so the team doesn't have to retype them.
--
-- Cleanups applied to match the official dropdowns in db.py:
--   Customer Name:  "Chevy"      -> "Chevrolet"
--                   "Ford Dtown" -> "Ford"   (still Internal)
--                   "MTB" / "Aqualink"       -> Customer (external) rows
--   Make:           "Chevry"     -> "Chevrolet"
--                   "Ford " (trailing space) -> "Ford"
--                   "Chevy"      -> "Chevrolet"
--                   "RAM"        -> "Ram"
--   Costs marked "--" / "-" in the Excel become NULL.
--
-- Run AFTER 2026-05-12_mobile_keys.sql. Not idempotent — re-running on a
-- table that already has these rows will create duplicates. To re-seed:
--   delete from mobile_keys;
-- (or truncate) before pasting this file again.

insert into mobile_keys (
  cut_date, end_user, customer_name, ro_number, vin, year, make, model, key_type,
  key_fob_part_number, key_fob_cost, key_blank_part_number, key_blank_cost,
  programming_cost, offset_eligible
) values
  ('2026-04-27', 'Internal', 'Chevrolet', '314380', '1GCPYCEFXLZ317225', 2020, 'Chevrolet', 'Silverado',  'Fob',      '84209236',   114.02, '13523912',    37.09, 60.00, true),
  ('2026-05-27', 'Internal', 'Chevrolet', '314326', '1GYFZDR41MF000700', 2021, 'Cadillac',  'XT4',        'Fob',      '13544052',   102.95, '22984994',    52.18, 60.00, true),
  ('2026-05-27', 'Internal', 'Ford',      '314379', '1FTEW1EP0PKE59446', 2023, 'Ford',      'F150',       'Fob',      '5929503',    148.50, '5939649',     36.29, 60.00, true),
  ('2026-05-27', 'Customer', 'MTB',       '314397', '1FT8W3BNXTED32174', 2026, 'Ford',      'F350',       'Flip Key', '5945864',    128.70, null,           null, 60.00, true),
  ('2026-01-05', 'Internal', 'Toyota',    '314398', '1FTEW1EP8HFA95531', 2017, 'Ford',      'F150',       'Fob',      '5926054',    165.00, '4223891',     30.31, 60.00, true),
  ('2026-07-05', 'Internal', 'Ford',      '314504', '1FMSK8DH8NGC33636', 2022, 'Ford',      'Explorer',   'Fob',      '5933985',    157.25, '5929522',     36.29, 60.00, false),
  ('2026-07-05', 'Internal', 'Chevrolet', '314503', '1FMSK8JH1MGC19418', 2021, 'Ford',      'Explorer',   'Fob',      '5933985',    157.25, '5929522',     36.29, 60.00, false),
  ('2026-07-05', 'Internal', 'Chevrolet', '314502', '2GC4YNE75R1134470', 2024, 'Chevrolet', 'Silverado',  'Fob',      '13560205',   106.46, '1356164',     66.31, 60.00, true),
  ('2026-07-05', 'Internal', 'Bid Lot',   '314534', '4T1BF28B31U138923', 2001, 'Toyota',    'Avalon',     'Turnkey',  null,          null,   '90999-00185',  6.04, 60.00, true),
  ('2026-07-05', 'Internal', 'Bid Lot',   '314531', '1C3CDFAAXGD606909', 2016, 'Dodge',     'Dart',       'Fob',      '56046771AA', 139.70, '68029829AB',  43.12, 60.00, true),
  ('2026-11-05', 'Internal', 'Chevrolet', '314571', '3C6UR5DJ1RG303215', 2024, 'Ram',       '2500',       'Fob',      '68575426AA',  64.02, '68399889AA',  29.81, 60.00, true),
  ('2026-11-05', 'Internal', 'Ford',      '314572', '1FMSK8DH8NGC33636', 2022, 'Ford',      'Explorer',   'Fob',      '5933985',    157.25, '5929522',     36.29, 60.00, false),
  ('2026-11-05', 'Internal', 'Ford',      '314573', '1FMJK2AT3NEA53302', 2022, 'Ford',      'Expedition', 'Fob',      '5943669',    160.88, '5929522',     36.29, 60.00, false),
  ('2026-11-05', 'Customer', 'Aqualink',  null,     '1FTER4FH1PLE13537', 2023, 'Ford',      'Ranger',     'Flip Key', '5923694',    134.20, null,           null, 60.00, true);
