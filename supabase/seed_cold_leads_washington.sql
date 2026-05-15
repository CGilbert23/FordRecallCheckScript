-- One-time seed for the Washington tab on /cold-leads (cold_leads table).
-- 59 rows lifted from the team's Excel sheet.
--
-- Normalizations applied:
--   Source:  "Service"            -> "Xtime"
--            "Sales (Hoisington)" -> "Sales"  (salesperson name dropped)
--            "Sales"              -> "Sales"
--            "Recalls"            -> "Other"  (not a dropdown option; closest fit)
--            (empty)              -> NULL
--   Phone:   stripped to digits, reformatted as (NNN-NNN-NNNN).
--   Dates:   M/D/YYYY -> YYYY-MM-DD. A handful of rows have 2025 dates
--            (South Branch Emergceny / Blairstown lead_date, plus Esurance,
--             TM Morey, South Branch, Blairstown contact_date). Imported
--            verbatim — fix any that are actual typos in the UI.
--   Notes:   empty -> NULL. Apostrophes (FITZ'S FISH POND) doubled.
--            Source-typos preserved verbatim ("Onwers", "Grouo", "Emergceny",
--            "Schedueled", "MASONTRY", "CONCTRUCTION", "Pesonal", etc.).
--
-- Run AFTER 2026-05-15_cold_leads.sql + 2026-05-15_cold_leads_markets.sql.
-- Not idempotent — re-running creates duplicates. To re-seed:
--   delete from cold_leads where market = 'Washington';

insert into cold_leads (
  market, name, phone, source, lead_date, contact_date, notes, hot_lead
) values
  ('Washington', 'JOE THE PLUMBER LLC',                           '(908-283-6021)', 'Xtime', '2026-02-20', '2026-03-13', 'Spoke with Joe - only 2 vehicles - does not seem really interested', false),
  ('Washington', 'ADVANCED MECHANICAL SERVICES',                  '(973-418-1859)', 'Xtime', '2026-03-02', '2026-03-26', '5 trucks - somewhat interested, schedueled a PDEL', false),
  ('Washington', 'MID ATLANTIC MECHANICAL',                       '(908-752-8773)', 'Xtime', '2026-03-03', '2026-03-26', 'Todd - 7 vehicles - interested - turkeytoplandscaping@gmail.com', false),
  ('Washington', 'BARR NONE COATING APPLICATORS',                 '(732-685-2979)', 'Xtime', '2026-03-03', '2026-03-26', 'VM', false),
  ('Washington', 'ALTEC INDUSTRIES',                              '(908-200-1322)', 'Xtime', '2026-03-03', '2026-03-26', 'VM - Ray', false),
  ('Washington', 'ALTE ROOFING INC',                              '(908-227-3522)', 'Xtime', '2026-03-03', '2026-04-01', 'VM', false),
  ('Washington', 'FITZ''S FISH POND',                             '(848-230-5178)', 'Xtime', '2026-03-03', '2026-04-01', 'VM', false),
  ('Washington', 'CJR LANDSCAPE DESIGN LLC',                      '(201-400-8645)', 'Xtime', '2026-03-03', '2026-04-01', 'VM', false),
  ('Washington', 'Esurance Insurance',                            '(908-307-7743)', 'Xtime', '2026-03-03', '2025-12-14', 'Large fleet across areas, going to bring us up at next meeting', false),
  ('Washington', 'TM Morey',                                      '(570-780-4542)', 'Sales', '2026-03-03', '2025-12-19', 'Poconos, lead from sales, Tim Morey', false),
  ('Washington', 'South Branch Emergceny',                        '(908-581-3090)', 'Xtime', '2025-01-06', '2025-12-19', 'Has a car that needs service soon', false),
  ('Washington', 'Blairstown Twsp Police',                        '(908-310-5250)', 'Other', '2025-01-06', '2025-12-19', 'Tom Tuka, waiting to book', false),
  ('Washington', 'REACT LOGISTICS',                               '(484-885-4143)', 'Xtime', '2026-03-16', '2026-04-01', 'VM - Alex - AMZN LOGISTICS', false),
  ('Washington', 'LLC IVAN MEDINA LAWN MAINTENANCE',              '(908-229-3609)', 'Xtime', '2026-03-17', '2026-04-01', 'VM - IVAN', false),
  ('Washington', 'BUCKLEY CABLE CONSTRUCTION CO',                 '(610-637-9944)', 'Xtime', '2026-03-17', '2026-04-01', 'VM - Chris', false),
  ('Washington', 'VERTA MASONRY LLC',                             '(908-434-8680)', 'Xtime', '2026-03-18', '2026-04-01', '5 Trucks - somewhat interested but happy w service', false),
  ('Washington', 'STOVES & FIREPLACE EXPERTS LLC',                '(570-872-4386)', 'Xtime', '2026-03-18', '2026-04-01', 'VM', false),
  ('Washington', 'JG SERVICES LLC',                               '(267-316-8511)', 'Xtime', '2026-03-19', '2026-04-01', 'VM', false),
  ('Washington', 'INNOVATIVE CONCRETE TECHNOLOGY, LLC',           '(908-894-0383)', 'Xtime', '2026-03-23', '2026-04-01', '3 Trucks - jacob@bestadmix.com', false),
  ('Washington', 'KELLER NORTH AMERICA',                          '(201-274-5099)', 'Xtime', '2026-03-24', '2026-04-01', 'VM - Bill', false),
  ('Washington', 'COOL AIR HEATING AND AIR CONDITIONING LLC',     '(908-342-2088)', 'Xtime', '2026-03-24', '2026-04-01', 'VM', false),
  ('Washington', 'CHARLES T MATARAZZO EXCAVATING AND MASONTRY',   '(908-229-3394)', 'Xtime', '2026-03-25', '2026-04-01', 'Charlie', false),
  ('Washington', 'RODOTA TRUCKING AND EXCAVATING, LLC',           '(908-453-3230)', 'Xtime', '2026-03-25', '2026-04-01', 'VM', false),
  ('Washington', 'S&M Concrete Services',                         '(908-310-9828)', 'Xtime', '2026-04-01', '2026-04-01', 'VM - OOO 4/27', false),
  ('Washington', 'The Corporation',                               '(731-991-9335)', 'Xtime', '2026-04-01', '2026-04-01', 'Pingry School - Barabara - seems to manage it with her husband. Sent her an email', false),
  ('Washington', 'Smiths Tree Service',                           '(908-655-5438)', 'Xtime', '2026-04-01', '2026-04-01', 'VM - lot of trucks, call again', false),
  ('Washington', 'J&D Auto Body (Jeff and Dennis)',               '(908-689-4233)', 'Xtime', '2026-04-01', '2026-04-01', 'Spoke to rep and made him aware - said they will keep in mind', false),
  ('Washington', 'Merril Creek Onwers Grouo',                     '(609-865-9735)', 'Xtime', '2026-04-01', '2026-04-01', ' 6 vehicles - curtishill@terraengineers.com', false),
  ('Washington', 'Township of Harmony',                           '(908-878-3001)', 'Xtime', '2026-04-01', '2026-04-01', 'VM', false),
  ('Washington', 'The Safe Man',                                  '(908-963-1572)', 'Sales', '2026-04-01', '2026-04-01', 'Schedueled PDEL, completed mobile service', false),
  ('Washington', 'Copolla Services',                              '(201-846-6760)', 'Sales', '2026-04-01', '2026-04-01', 'DOCUMENTS WITH CFO', false),
  ('Washington', 'American Pile',                                 '(908-752-5775)', 'Xtime', '2026-04-01', '2026-04-01', 'Number is Frankies Cell - Sent email also (interested in recalls 200 trucks and own shop ): fmarotti@americanpilellc.com', false),
  ('Washington', 'JDC Power',                                     '(908-963-5558)', null,    '2026-04-01', '2026-04-01', 'Called tim the owner (tim@jdcpowersystems.com) Super interested - fleet manager is Anthony. 20 trucks. company builds data centers', false),
  ('Washington', 'EWC Plumbing',                                  '(908-235-6915)', 'Xtime', '2026-02-06', '2026-04-01', 'Eric - only has 2 vehicles but likes the idea', false),
  ('Washington', 'BAKER CONSTRUCTION',                            '(908-581-3546)', 'Xtime', '2026-03-04', '2026-04-01', 'jordan@bakerconstructionnj.com- 15 fords + others, very interested- BOOKED', false),
  ('Washington', 'JML LANDSCAPING INC',                           '(908-507-5954)', 'Xtime', '2026-03-04', '2026-04-01', 'Has open recalls, large fleet. Was to busy last time, call again', false),
  ('Washington', 'CIRCLE THREE DESIGNS, LLC',                     '(973-879-1959)', 'Xtime', '2026-03-05', '2026-04-01', 'Interested but only 3 cars. Chris Shaloub - Dash Cam (973-879-1959). christopher@circlethreedesigns.com', false),
  ('Washington', 'MUSKY TROUT HATCHERIES LLC',                    '(908-507-7639)', null,    '2026-03-09', '2026-04-01', 'musky279@yahoo.com - Jeff (5 vehicles) very interested', false),
  ('Washington', 'C&L OF WASHINGTON',                             '(201-704-2711)', 'Xtime', '2026-03-19', '2026-04-01', 'very interested - wants other brands, has several locations. miket@clautobody.com', false),
  ('Washington', 'PAUL KLEIN CONCTRUCTION',                       '(908-752-9688)', 'Xtime', '2026-03-25', '2026-04-01', '2 Trucks - Sent text', false),
  ('Washington', 'Ianella Masonry',                               '(908-359-0739)', 'Xtime', '2026-04-01', '2026-04-15', '5 Fords - very interested. Uses fleettech', false),
  ('Washington', 'APH Mechanical',                                '(973-224-7085)', 'Xtime', '2026-04-01', '2026-04-15', 'Andy - Four total - moving closer to Washington NJ', false),
  ('Washington', 'Blewjas Associates',                            '(908-797-9653)', 'Xtime', '2026-04-01', '2026-04-15', 'Steven - 30 trucks, interested - doing a recall on Monday', false),
  ('Washington', 'JERSEY CENTRAL POWER AND LIGHT',                '(862-881-1936)', 'Xtime', '2026-04-17', '2026-04-15', 'Brandon - mechanic at one of the locations? says he will pass it up the chain to supervisor backerman@firstenergycorp.com', false),
  ('Washington', 'LLC IRISH MEADOWS',                             '(908-879-0233)', 'Xtime', '2026-04-15', '2026-04-15', 'talked to a woman - sounded interested, decision maker is Billy', false),
  ('Washington', 'KPM EXCEPTIONAL LLC',                           '(717-514-4481)', 'Xtime', '2026-04-16', '2026-04-15', 'left message for Gino and also sent emial', false),
  ('Washington', 'HAJDU CO.',                                     '(908-319-1551)', 'Xtime', '2026-04-16', '2026-04-15', 'left message with the receptionist and followed up with an email', false),
  ('Washington', 'TOWN OF CLINTON',                               '(908-616-6864)', 'Xtime', '2026-04-17', '2026-04-15', 'Chris sent an email on 5/4 as per Shelbi', false),
  ('Washington', 'WFF INC T-A LAWN DOCTOR OF WARREN',             '(908-399-4486)', 'Xtime', '2026-04-17', '2026-04-15', 'No answer', false),
  ('Washington', 'LLC PATRIOT PAVING',                            '(908-500-0404)', 'Xtime', '2026-04-17', '2026-04-15', 'No answer', false),
  ('Washington', 'LAYOUT INC.',                                   '(908-493-3627)', 'Xtime', '2026-04-18', '2026-04-15', 'No answer', false),
  ('Washington', 'MANSFIELD TWP',                                 '(908-246-8906)', 'Xtime', '2026-04-20', '2026-04-15', 'VM', false),
  ('Washington', 'WARREN COUNTY MOSQUITO COMMISS',                '(908-453-3585)', 'Xtime', '2026-04-21', '2026-04-15', 'Interested, hanful of vehicles. John Necina - jnecina@warrencountymosquito.org', false),
  ('Washington', 'TWSP OF BEDMINSTER',                            '(908-963-7217)', 'Xtime', '2026-04-21', '2026-04-15', 'Pesonal vehicle - said he would let his boss know', false),
  ('Washington', 'HC CONSTRUCTORS INC',                           '(908-574-8093)', 'Xtime', '2026-04-23', '2026-04-15', 'MSTEVENSON@HCCONSTRUCTORS.COM - sent email, 15 Fords very interested - offered free LOF', false),
  ('Washington', 'MENDHAM GARDEN CENTER',                         '(908-892-7475)', 'Xtime', '2026-04-28', '2026-04-15', 'No answer - call again', false),
  ('Washington', 'ADS ENVIRONMENTAL INC',                         '(908-616-8928)', 'Xtime', '2026-04-29', '2026-04-15', 'Spoke to him - not really interested', false),
  ('Washington', 'GREEN TOWNSHIP',                                '(862-258-7249)', 'Xtime', '2026-04-30', '2026-04-15', 'Bad number - sent email', false),
  ('Washington', 'LOPATCONG TOWNSHIP',                            '(908-859-1212)', 'Xtime', '2026-04-27', '2026-04-15', 'Got kathy receptionist - she said send email to garciaj@lopatcongtwp.com', false);
