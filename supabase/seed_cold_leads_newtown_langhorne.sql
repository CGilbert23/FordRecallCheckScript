-- One-time seed for the Newtown/Langhorne tab on /cold-leads (cold_leads table).
-- 39 rows lifted from the team's Excel sheet.
--
-- Normalizations applied:
--   Source:  "Service" -> "Xtime"
--            (empty)   -> NULL  (only Northampton Twsp Public Works)
--   Phone:   stripped to digits, reformatted as (NNN-NNN-NNNN).
--   Dates:   M/D/YYYY -> YYYY-MM-DD. Several rows have an empty contact_date
--            (DREAM LAWN, NEWTOWN AMBULANCE, UNIVERSAL HEATING, Northampton
--             Twsp, HI-TECH COMPRESSOR) — saved as NULL.
--   Notes:   empty -> NULL. The literal "--" on TERRIFIC TURF LLC is also
--            treated as empty -> NULL (matches the seed_mobile_keys convention).
--            Apostrophes (BREEN'S LANDSCAPING, D'Andrea) doubled.
--            Source-typos preserved verbatim ("intrested", "Vehciles",
--            "chnages", "worlk", "Floring", "Cemetary", "intersted",
--            "Didnt", "newtwonpa.gov", etc.).
--   Whitespace inside names is preserved (e.g. BREEN'S LANDSCAPING  LLC has
--   a double space, matching the source).
--
-- Known internal duplicates kept as-is:
--   - HAMMER PROPERTY MANAGEMENT appears twice (rows w/ phone 215-397-5172).
--   - YC Contracting appears twice (rows w/ phone 267-709-6445).
--   - TERRIFIC TURF LLC's phone (215-900-4134) also exists in
--     seed_cold_leads_doylestown.sql; the dup-check toast will surface this.
--
-- Run AFTER 2026-05-15_cold_leads.sql + 2026-05-15_cold_leads_markets.sql.
-- Not idempotent — re-running creates duplicates. To re-seed:
--   delete from cold_leads where market = 'Newtown/Langhorne';

insert into cold_leads (
  market, name, phone, source, lead_date, contact_date, notes, hot_lead
) values
  ('Newtown/Langhorne', 'HARRIS FUELS INC',                              '(215-499-4621)', 'Xtime', '2026-03-02', '2026-03-26', 'left VM with i think his name was doug harris', false),
  ('Newtown/Langhorne', 'GLAXOSMITHKLINE LLC',                           '(215-260-3445)', 'Xtime', '2026-03-02', '2026-03-26', 'LVM', false),
  ('Newtown/Langhorne', 'INC ROBERT',                                    '(215-768-7544)', 'Xtime', '2026-03-02', '2026-03-26', 'LVM', false),
  ('Newtown/Langhorne', 'HAMMER PROPERTY MANAGEMENT, LLC.',              '(215-397-5172)', 'Xtime', '2026-03-02', '2026-03-26', 'LVM', false),
  ('Newtown/Langhorne', 'REALTY LANDSCAPE',                              '(267-935-4909)', 'Xtime', '2026-03-02', '2026-03-26', 'LVM', false),
  ('Newtown/Langhorne', 'BLUE KNIGHT HARDWOOD FLOORS LLC',               '(732-456-4141)', 'Xtime', '2026-03-03', '2026-03-26', 'Talked to him and sent info email ', false),
  ('Newtown/Langhorne', 'Signal Security',                               '(570-617-4171)', 'Xtime', '2026-03-04', '2026-03-26', 'LVM', false),
  ('Newtown/Langhorne', 'SHERWIN WILLIAMS CO',                           '(610-349-2407)', 'Xtime', '2026-03-05', '2026-04-03', 'Number just rang ', false),
  ('Newtown/Langhorne', 'MICHAEL J HUTCHINSON BUILDER',                  '(215-778-7159)', 'Xtime', '2026-03-05', '2026-04-03', 'LVM', false),
  ('Newtown/Langhorne', 'BUCKS COUNTY COMMUNITY COLLEGE',                '(215-968-8390)', 'Xtime', '2026-03-06', '2026-04-03', 'Talked to Jill and sent info email', false),
  ('Newtown/Langhorne', 'AMF SALES & ASSOCIATES INC.',                   '(973-647-9264)', 'Xtime', '2026-03-06', '2026-04-03', 'LVM', false),
  ('Newtown/Langhorne', 'ANDREOLI CONSTRUCTION LLC',                     '(215-397-5747)', 'Xtime', '2026-03-11', '2026-04-03', 'LVM', false),
  ('Newtown/Langhorne', 'TOM ADAMS WINDOWS & CARPETS',                   '(215-375-5985)', 'Xtime', '2026-03-12', '2026-04-03', 'She said she was not Intrested ', false),
  ('Newtown/Langhorne', 'VERDER SCIENTIFIC INC',                         '(267-349-6184)', 'Xtime', '2026-03-12', '2026-04-03', 'LVM', false),
  ('Newtown/Langhorne', 'RP TECHNOLOGIES INC',                           '(215-208-1485)', 'Xtime', '2026-03-13', '2026-04-03', 'LVM', false),
  ('Newtown/Langhorne', 'K N REPAIR INC',                                '(610-715-1475)', 'Xtime', '2026-03-13', '2026-04-03', 'Didnt call, this is a auto shop ', false),
  ('Newtown/Langhorne', 'NATIONWIDE MAINTENANCE',                        '(215-578-6951)', 'Xtime', '2026-03-16', '2026-04-07', 'not intrested ', false),
  ('Newtown/Langhorne', 'BREEN''S LANDSCAPING  LLC',                     '(215-435-7010)', 'Xtime', '2026-03-16', '2026-04-07', 'sent info email', false),
  ('Newtown/Langhorne', 'The Guardians of the National Cemetary',        '(267-432-1739)', 'Xtime', '2026-03-20', '2026-04-07', 'LVM', false),
  ('Newtown/Langhorne', 'JUDAH INC DBA HOLLAND FLOOR COVERING',          '(814-746-2620)', 'Xtime', '2026-03-23', '2026-04-07', 'LVM', false),
  ('Newtown/Langhorne', 'HAMMER PROPERTY MANAGEMENT LLC',                '(215-397-5172)', 'Xtime', '2026-03-23', '2026-04-21', 'not intrested ', false),
  ('Newtown/Langhorne', 'C S GROUP INC',                                 '(610-513-7675)', 'Xtime', '2026-03-25', '2026-04-21', 'LVM', false),
  ('Newtown/Langhorne', 'Simple Charm Floring',                          '(856-287-5621)', 'Xtime', '2026-04-01', '2026-04-21', 'Justin - 1 truck - lives in NJ', false),
  ('Newtown/Langhorne', 'Bill Gillespie Electric',                       '(267-566-2462)', 'Xtime', '2026-04-01', '2026-04-21', 'Jason Charnick - handful of trucks - intersted', false),
  ('Newtown/Langhorne', 'Shelland Mechanical',                           '(267-549-8490)', 'Xtime', '2026-04-01', '2026-04-21', 'VM - Call AGAIN', false),
  ('Newtown/Langhorne', 'D''Andrea Brothers',                            '(856-230-8855)', 'Xtime', '2026-04-01', '2026-04-21', 'Spoke to him - not to interested', false),
  ('Newtown/Langhorne', 'YC Contracting',                                '(267-709-6445)', 'Xtime', '2026-04-01', '2026-04-29', 'Jerry -yccontracting@outlook.com -11 Vehciles - offered 1-2 free oil chnages', false),
  ('Newtown/Langhorne', 'Newtown Township',                              '(609-558-4301)', 'Xtime', '2026-04-01', '2026-04-29', 'will be hard to round up but interested, etecker@newtwonpa.gov', false),
  ('Newtown/Langhorne', 'REVERE SUBURBAN REALTY CORP',                   '(215-399-6949)', 'Xtime', '2026-04-01', '2026-05-08', 'LVM', false),
  ('Newtown/Langhorne', 'YC CONTRACTING',                                '(267-709-6445)', 'Xtime', '2026-04-01', '2026-05-08', 'LVM', false),
  ('Newtown/Langhorne', 'TERRIFIC TURF LLC',                             '(215-900-4134)', 'Xtime', '2026-04-01', '2026-05-08', null, false),
  ('Newtown/Langhorne', 'STACI COUNCEL ROCK SCHOOL DISTRICT',            '(215-944-1010)', 'Xtime', '2026-04-01', '2026-04-07', 'VERY INTERESTED - JILL', false),
  ('Newtown/Langhorne', 'PROACT ENVIRONMENTAL INC',                      '(267-221-9416)', 'Xtime', '2026-04-01', '2026-04-07', 'VERY INTERESTED - Brian', false),
  ('Newtown/Langhorne', 'Sam Wexler Plumbing',                           '(267-688-1364)', 'Xtime', '2026-04-01', '2026-04-29', '30 trucks - pretty interested for warranty worlk', false),
  ('Newtown/Langhorne', 'DREAM LAWN SOLUTIONS LLC',                      '(215-609-7529)', 'Xtime', '2026-04-01', null,         'Gabriel - 5 cars not really interested', false),
  ('Newtown/Langhorne', 'NEWTOWN AMBULANCE SQUAD',                       '(267-688-3940)', 'Xtime', '2026-04-01', null,         'Kevin Gordon - somewhat interested - sent email - kgordon@newtownambulance.org', false),
  ('Newtown/Langhorne', 'UNIVERSAL HEATING AND AIR CONDITIONING INC',    '(267-228-2656)', 'Xtime', '2026-04-01', null,         null, false),
  ('Newtown/Langhorne', 'Northampton Twsp Public Works',                 '(215-357-8455)', null,    '2026-04-01', null,         null, false),
  ('Newtown/Langhorne', 'HI-TECH COMPRESSOR',                            '(215-880-0089)', 'Xtime', '2026-04-01', null,         null, false);
