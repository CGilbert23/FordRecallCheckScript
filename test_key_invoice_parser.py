"""Regression tests for key_invoice_parser against the sample invoices in KeyDash/.

No test framework in this repo, so this runs standalone like the parser itself:

    python test_key_invoice_parser.py

The strongest assertion here is the per-invoice total: the parsed line amounts
only add up to the invoice's own printed TOTAL if every line was read exactly
once and attributed to the right vehicle. CPQQ4656475 is the invoice that caught
the page-straddle bug — it read $1,432.48 against a printed $1,182.39, dropping
one part, double-counting two and inventing a group that was never billed.
"""

import io
import re
import sys

import key_invoice_parser as parser

STRADDLE = 'KeyDash/CPQQ4656475_FBPW_I_6ac5181a71069.pdf'
MULTI_RO = 'KeyDash/316114,316119,316118,315115,316117.pdf'
SINGLE = 'KeyDash/316120.pdf'

# (ro, vin, fob part, fob cost, blank part, blank cost) — hand-checked against
# the paperwork and the corrected Key Database rows.
STRADDLE_GROUPS = [
    ('316959', '3C3JY55E16T324881', '5179514AC', 152.90, '5102247AB', 70.65),
    ('316954', '2T3A1RFV0PW381492', '8990H-0R220', 149.59, '69515-16110', 24.19),
    ('316955', '1GKS2CRD5SR148531', '13560220', 137.91, '13536164', 69.87),
    ('316956', '2GC4YNE70R1240518', '13560205', 112.18, '13536164', 69.87),
    ('316957', '1GNSKRKL3PR289080', '13560207', 129.35, '13536164', 69.87),
    ('316958', '1FMDE7BH5RLA69420', '5940321', 159.72, '5929522', 36.29),
]

failures = []


def check(label, got, want):
    if got == want:
        print(f'  ok   {label}')
    else:
        print(f'  FAIL {label}\n        got:  {got!r}\n        want: {want!r}')
        failures.append(label)


def parse(path):
    return parser.parse_invoice_pdf(io.open(path, 'rb').read())


def swap_vin_ro(pdf_path):
    """Re-emit the pages with each VIN/RO pair swapped.

    CDK prints the pair RO-first on some invoices; the parser must not care.
    """
    pages = parser.extract_text_pages(io.open(pdf_path, 'rb').read())
    out = []
    for text in pages:
        lines = text.split('\n')
        i = 0
        while i < len(lines) - 1:
            if parser.RE_VIN.match(lines[i]) and parser.RE_RO.match(lines[i + 1]):
                lines[i], lines[i + 1] = lines[i + 1], lines[i]
                i += 2
            else:
                i += 1
        out.append('\n'.join(lines))
    return out


def groups_of(result):
    return [
        (g['ro_number'], g['vin'], g['key_fob_part_number'], g['key_fob_cost'],
         g['key_blank_part_number'], g['key_blank_cost'])
        for g in result['groups']
    ]


print('CPQQ4656475 — the page-straddle invoice')
r = parse(STRADDLE)
check('line item count', len(r['line_items']), 12)
check('parsed total matches printed total',
      (r['parsed_total'], r['invoice_total']), (1182.39, 1182.39))
check('groups', groups_of(r), STRADDLE_GROUPS)
check('no warnings', r['warnings'], [])

print('CPQQ4656475 — same invoice with the RO printed before the VIN')
items, warnings = parser.parse_line_items(swap_vin_ro(STRADDLE))
groups, _ = parser.group_line_items(items)
check('line item count', len(items), 12)
check('total', round(sum(i['amount'] for i in items), 2), 1182.39)
check('groups unchanged', [
    (g['ro_number'], g['vin'], g['key_fob_part_number'], g['key_fob_cost'],
     g['key_blank_part_number'], g['key_blank_cost']) for g in groups
], STRADDLE_GROUPS)

print('316114/316119/316118/315115/316117 — multi-RO, two pages')
r = parse(MULTI_RO)
check('line item count', len(r['line_items']), 8)
check('parsed total matches printed total',
      (r['parsed_total'], r['invoice_total']), (1099.04, 1099.04))
# One RO legitimately covering two VINs is why groups key on the pair.
check('group count', len(r['groups']), 6)
check('316117 covers two VINs',
      sorted(g['vin'] for g in r['groups'] if g['ro_number'] == '316117'),
      ['4T3E6RFV1MU020786', '5TFCZ5AN9LX230996'])
check('no warnings', r['warnings'], [])

print('316120 — single part, single page')
r = parse(SINGLE)
check('line item count', len(r['line_items']), 1)
check('parsed total matches printed total',
      (r['parsed_total'], r['invoice_total']), (134.20, 134.20))
check('group', groups_of(r), [('316120', '1FTER4FH1PLE31889', '5923694', 134.20, None, None)])
check('no warnings', r['warnings'], [])

print('copy splitting')
pages = parser.extract_text_pages(io.open(STRADDLE, 'rb').read())
check('two printed copies per page', [len(parser.split_page_copies(t)) for t in pages], [2, 2, 2])
check('one stream per copy', len(parser.copy_streams(pages)), 2)
check('the copies read identically',
      parser._identity(parser.parse_stream(parser.copy_streams(pages)[0])),
      parser._identity(parser.parse_stream(parser.copy_streams(pages)[1])))
# No sentinel anywhere must still yield something rather than nothing.
check('falls back to one stream without a sentinel',
      len(parser.copy_streams(['no account marker here', 'nor here'])), 1)

print()
if failures:
    print(f'{len(failures)} FAILED: ' + ', '.join(failures))
    sys.exit(1)
print('all passed')
