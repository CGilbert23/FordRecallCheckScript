-- One-time seed for the Doylestown tab on /cold-leads (cold_leads table).
-- 53 rows lifted from the team's Excel sheet.
--
-- Normalizations applied:
--   Source:  "Service"            -> "Xtime"
--            "Sales (Hoisington)" -> "Sales"  (salesperson name dropped — no field for it)
--   Phone:   stripped to digits, reformatted as (NNN-NNN-NNNN) to match the
--            client-side formatter in templates/cold_leads.html.
--   Dates:   M/D/YYYY -> YYYY-MM-DD. The "Revam" row's contact_date is
--            kept as 2025-01-02 verbatim — looks like a 2026 typo in the
--            source data; fix it in the UI after import if needed.
--   Notes:   empty cells -> NULL. Apostrophes doubled to '' for SQL.
--            Source-typos in notes ("Volunterr", "inmterested", trailing
--            spaces, etc.) preserved verbatim.
--
-- Run AFTER 2026-05-15_cold_leads.sql + 2026-05-15_cold_leads_markets.sql.
-- Not idempotent — re-running on a table that already has these rows will
-- create duplicates. To re-seed:
--   delete from cold_leads where market = 'Doylestown';
-- (or truncate cold_leads) before pasting this file again.

insert into cold_leads (
  market, name, phone, source, lead_date, contact_date, notes, hot_lead
) values
  ('Doylestown', 'New Leaf Growers',                '(908-797-5700)', 'Xtime', '2026-12-25', '2026-01-22', 'spoke w/ Robin - only a few vehicles- sent follow up email robin@newleafgrowers.com', false),
  ('Doylestown', 'Radio Systems Corportations',     '(908-798-9806)', 'Xtime', '2026-12-25', '2026-01-22', 'left vm msg', false),
  ('Doylestown', 'Economy Roofing',                 '(215-801-9504)', 'Xtime', '2026-12-25', '2026-01-29', 'spoke w/ Kim, sent follow up email- some interest- has 12 vehicles', false),
  ('Doylestown', 'Di''encenso Landscaping',         '(267-414-4943)', 'Xtime', '2026-12-25', '2026-01-30', 'left vm msg for Anthony', false),
  ('Doylestown', 'Northeast Medical',               '(215-380-2918)', 'Xtime', '2026-12-25', '2026-01-30', 'spoke w/ Evelyn, only 1 Transit- sent follow up email w/info', false),
  ('Doylestown', 'MontCo Water And Sewer (MTMSA)',  '(267-718-3784)', 'Xtime', '2026-12-25', '2026-01-30', 'spoke  w/office, called Keith cell, left msg and sent follow up email', false),
  ('Doylestown', 'Ambler Industries',               '(814-743-0104)', 'Xtime', '2026-12-25', '2026-02-02', 'left vm msg (no name on vm)', false),
  ('Doylestown', 'Point Pleasant Fire',             '(215-397-5818)', 'Xtime', '2026-12-25', '2026-02-02', 'spoke to Scott - not interested - municiple vehicles handled internally', false),
  ('Doylestown', 'Anderson Mechanical',             '(215-766-9890)', 'Xtime', '2026-12-25', '2026-02-02', 'spoke w/ Heather (prefers pick-up and del service currently using w/Ford Doy) ', false),
  ('Doylestown', 'DOD Enterprises',                 '(215-275-3675)', 'Xtime', '2026-12-25', '2026-02-05', 'spoke w/ Dennis- only 2 vehicles- flipped april appt to mobile', false),
  ('Doylestown', 'Walton Contracting',              '(215-630-1764)', 'Xtime', '2026-12-25', '2026-02-05', 'left vm msg', false),
  ('Doylestown', 'Revam',                           '(610-739-2132)', 'Sales', '2026-01-01', '2025-01-02', 'Lead from sales, spoke w/ Mike and sent follow up email', false),
  ('Doylestown', 'Infinite Mechanical LLC',         '(484-363-9840)', 'Xtime', '2026-01-01', '2026-01-16', 'INTERESTED - SENT FOLLOW UP EMAIL to Neil, Booked', false),
  ('Doylestown', 'FISHERS ACE HARDWARE',            '(215-766-8220)', 'Xtime', '2026-01-01', '2026-01-16', 'interested- follow up email sent (Nick@ Handyman Service) 215-766-1677 centralbucks@acehandymanservices.com', false),
  ('Doylestown', 'Blue Heron Water',                '(267-406-6050)', 'Xtime', '2026-01-01', '2026-02-05', 'called and was told to email Christian- but seemed interested in service even though he does not handle the fleet- sent follow up email', false),
  ('Doylestown', 'Gilbane Building',                '(267-990-2346)', 'Xtime', '2026-01-01', '2026-02-06', 'very large company- each person responsible for own vehicle- spoke w/ Ray- sent follow up email', false),
  ('Doylestown', 'VALTS ROOFING',                   '(215-852-5895)', 'Xtime', '2026-01-01', '2026-02-06', 'spoke w/ Dan. Interested, sent follow up email - ''valtsroofing@valtsroofing', false),
  ('Doylestown', 'REUTER & HANNEY INC',             '(215-595-3489)', 'Xtime', '2026-01-01', '2026-02-06', 'Sent follow up Email (Under Qualus) Huge account    Cody.Mastalski@qualuscorp.com, sent 2nd follow up email 1/30, followed up w/ phone call Cody said that everyone has our contact info and will reach out if needed', false),
  ('Doylestown', 'University of Pennstarr',         '(215-651-2619)', 'Xtime', '2026-01-01', '2026-02-06', 'spoke w/ Kevin Thomas Crew/Ops Mgr - sent follow up email, 1st appt scheduled 1/22', false),
  ('Doylestown', 'Gerharts Landscaping',            '(267-374-3280)', 'Xtime', '2026-01-01', '2026-02-06', 'spoke w/ Isaiah, sent follow up email igerhart@gerhartslandscaping.com', false),
  ('Doylestown', 'Burns & Burns Industries',        '(215-906-3210)', 'Xtime', '2026-01-01', '2026-02-06', 'spoke w/ - sent follow up email and flyer - did not seem overly interested', false),
  ('Doylestown', 'Renda Roads',                     '(908-399-3995)', 'Xtime', '2026-01-01', '2026-02-06', 'not interested- wants to come into the dealership', false),
  ('Doylestown', 'John Ford Builders',              '(267-262-1697)', 'Xtime', '2026-01-01', '2026-02-06', 'spoke w/Kristine - only 2 vehicles for business- sent email and flyer', false),
  ('Doylestown', 'Mcgonagle Contracting',           '(267-221-6926)', 'Xtime', '2026-01-01', '2026-02-06', 'left vm msg for Mike', false),
  ('Doylestown', 'Pappageorge Construction',        '(215-820-2600)', 'Xtime', '2026-01-01', '2026-02-06', 'bad connection on phone- sent follow up email to Mark', false),
  ('Doylestown', 'Fascella Construction',           '(610-847-6862)', 'Xtime', '2026-01-01', '2026-02-06', 'Craig', false),
  ('Doylestown', 'Eagle Power Turf & Tractor',      '(215-348-9041)', 'Xtime', '2026-01-01', '2026-02-06', 'Desk assistant, no idea', false),
  ('Doylestown', 'L-L Heating & Equipment',         '(267-246-5954)', 'Xtime', '2026-01-01', '2026-02-06', 'spoke w/ Robert - interested - sent follow up email rlevin@llheating.com- 1st MS appt thurs 2/12', false),
  ('Doylestown', 'Grecko Landscaping',              '(267-304-4865)', 'Xtime', '2026-01-01', '2026-02-06', 'Right around corner not interested', false),
  ('Doylestown', 'Terrific Turf',                   '(215-900-4134)', 'Xtime', '2026-01-01', '2026-02-06', '*interested*  spoke w/ Dan, shared his neg exp w/ Langhorne, comes to dtown or newtown for service, appreciated the call- sent follow up email', false),
  ('Doylestown', 'Sycamore Landscape',              '(267-994-0765)', 'Xtime', '2026-04-01', '2026-02-06', '4 vehicles, interested', false),
  ('Doylestown', 'Borough of Doylestown',           '(215-852-1757)', 'Xtime', '2026-04-01', '2026-02-06', 'Said interested, Kenn was just there. will call next time', false),
  ('Doylestown', 'Crossland Excavations',           '(267-767-8683)', 'Xtime', '2026-04-01', '2026-02-06', 'Somewhat interested', false),
  ('Doylestown', 'Drainmen Plumbing',               '(610-340-8232)', 'Xtime', '2026-04-01', '2026-02-06', 'spoke w/ Mike Ammouri , interested- email follow up sent', false),
  ('Doylestown', 'A-L Services',                    '(201-841-3910)', 'Xtime', '2026-04-01', '2026-04-01', 'Spoke to kurt Appleby- gave me Edgar Estrada (fleet manager) 973-202-0568 - left voicemail ', false),
  ('Doylestown', 'Triuane Mec Kanical',             '(215-852-0189)', 'Xtime', '2026-04-01', '2026-04-01', 'SERVICED BY MOBILE SERVICE ON 4/10 - ONLY 2-3 TRUCKS', false),
  ('Doylestown', 'Mallard Plumbing',                '(267-784-9489)', 'Xtime', '2026-04-01', '2026-04-01', 'Spoke w/ Bob Austin- interested - sent email follow up bobaustin@getmallard.com', false),
  ('Doylestown', 'Devault Refrigeration',           '(267-885-8238)', 'Xtime', '2026-04-01', '2026-04-01', 'Driver - called wrong guy', false),
  ('Doylestown', 'Bridges of Warwick',              '(215-600-3747)', 'Xtime', '2026-04-01', '2026-04-01', 'Not inmterested', false),
  ('Doylestown', 'Walter Brucker & Company',        '(215-858-8363)', 'Xtime', '2026-04-01', '2026-04-01', 'interested, 6-7 vehicles. Sent email to : office@walterbrucker.com', false),
  ('Doylestown', 'DMR Refrigeration',               '(215-435-0211)', 'Xtime', '2026-04-01', '2026-04-21', null, false),
  ('Doylestown', 'Marino Corp',                     '(610-584-1800)', 'Xtime', '2026-04-01', '2026-04-21', null, false),
  ('Doylestown', 'A R Nejad Enterprises',           '(267-221-4151)', 'Xtime', '2026-04-01', '2026-04-21', null, false),
  ('Doylestown', 'Blue Lion Landscaping',           '(215-837-2099)', 'Xtime', '2026-04-01', '2026-04-21', null, false),
  ('Doylestown', 'Millar & Sons',                   '(267-246-9773)', 'Xtime', '2026-04-01', '2026-04-21', null, false),
  ('Doylestown', 'Plumsteadville Volunteer Fire',   '(862-452-9526)', 'Xtime', '2026-04-01', '2026-04-21', null, false),
  ('Doylestown', 'Penyak Roofing',                  '(908-227-0101)', 'Xtime', '2026-04-01', '2026-04-21', null, false),
  ('Doylestown', 'Ground Water Consultants',        '(267-471-6742)', 'Xtime', '2026-04-01', '2026-04-21', null, false),
  ('Doylestown', 'Benito Isabela Nu Motion',        '(445-245-0146)', 'Xtime', '2026-04-01', '2026-04-21', null, false),
  ('Doylestown', 'New Huntington Construction',     '(267-249-0619)', 'Xtime', '2026-04-01', '2026-04-21', null, false),
  ('Doylestown', 'Rebcore',                         '(215-421-5792)', 'Xtime', '2026-04-01', '2026-04-21', null, false),
  ('Doylestown', 'Tacony Watershed',                '(484-553-4765)', 'Xtime', '2026-04-01', '2026-04-21', null, false),
  ('Doylestown', 'Volunterr Medical Service Corp',  '(301-703-0277)', 'Xtime', '2026-04-01', '2026-04-21', null, false);
