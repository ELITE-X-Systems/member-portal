"""
Generate the public ELITE X portal data from the PRIVATE Staff Records workbook.

Usage:
  python scripts/build_data.py "Elite-X Records.xlsx"

The generated data.json contains only member-facing fields.
Private workbook notes and internal award notes are never published.

Important: the workbook contains formulas, but XLSX files do not always carry
fresh cached formula results. When a calculated Bond Record value has no cache,
this script evaluates the equivalent formula from the workbook's raw inputs.
The browser still remains display-only and never becomes the source of truth.
"""
import sys
import json
from datetime import datetime, date
from openpyxl import load_workbook

if len(sys.argv) != 2:
    raise SystemExit("Usage: python scripts/build_data.py <private-workbook.xlsx>")

src = sys.argv[1]
# Formula results are read from the cached-value workbook where available.
wb_values = load_workbook(src, data_only=True)
# Formula-mode workbook is kept for diagnostics and future-proofing.
wb_formulas = load_workbook(src, data_only=False)

reg = wb_values["Member Registry"]
bond = wb_values["Bond Record"]
ded = wb_values["Deductions"]
arch = wb_values["Monthly Archive"]
awards_sheet = wb_values["Awards & Achievements"]

ALLOWED_STATUSES = {"ACTIVE", "ON LEAVE", "INACTIVE", "RESIGNED", "REMOVED"}
ALLOWED_AWARD_CATEGORIES = {"MEDALLION", "CREST", "ACHIEVEMENT"}
ALLOWED_AWARD_STATUSES = {"EARNED", "PENDING", "REVOKED"}
TRANSACTION_TYPES = {"DEDUCTION", "SHOP PURCHASE"}

# Public informational rules. These do not recalculate or alter historical records.
BOND_GUIDELINES = [
    {"label": "ATTENDANCE", "value": "2 Bonds", "detail": "Per attendance · Tuesday–Friday"},
    {"label": "ID INSPECTION", "value": "5 Bonds", "detail": "Per ID check · Monday"},
    {"label": "GAMES", "value": "50–70 Bonds", "detail": "Maximum per game"},
    {"label": "ACTIVITIES", "value": "20 Bonds", "detail": "Maximum per person"},
    {"label": "WEEKLY LIMIT", "value": "100 Bonds", "detail": "Maximum earned per member per week"},
]


def text(value):
    return str(value).strip() if value is not None else ""


def iso_date(value):
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    return text(value)


def number(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def clean_amount(value):
    n = number(value)
    if n is None:
        return None
    # Preserve integer-style Bond values in the JSON where possible.
    return int(n) if n.is_integer() else n


def month_transaction_totals(member_id):
    """Return current-month deduction and shop totals from Deductions.

    The current month is taken from Settings!B3. This mirrors the Bond Record
    SUMIFS formula without requiring Excel to have cached that formula result.
    """
    settings = wb_values["Settings"]
    month_start = settings.cell(3, 2).value
    if not isinstance(month_start, (datetime, date)):
        # Settings!B3 is a formula (first day of the current month). Some
        # openpyxl-written or externally exported XLSX files omit its cached
        # result, so mirror the formula at build time rather than treating it
        # as an unknown month.
        today = date.today()
        month_start = date(today.year, today.month, 1)

    y, m = month_start.year, month_start.month

    deduction_total = 0.0
    shop_total = 0.0
    for rr in range(7, 207):
        mid = text(ded.cell(rr, 3).value).upper()
        typ = text(ded.cell(rr, 5).value).upper()
        amount = number(ded.cell(rr, 7).value)
        tx_date = ded.cell(rr, 2).value
        if mid != member_id or typ not in TRANSACTION_TYPES or amount is None:
            continue
        # The spreadsheet formula only counts dated transactions inside the
        # current month. Preserve that behavior exactly.
        if not isinstance(tx_date, (datetime, date)):
            continue
        if tx_date.year != y or tx_date.month != m:
            continue
        if typ == "SHOP PURCHASE":
            shop_total += amount
        elif typ == "DEDUCTION":
            deduction_total += amount
    return deduction_total, shop_total


def calculated_bond_value(cached_value, evaluated_value, label, member_id):
    """Use the cached workbook result when it agrees with the equivalent
    formula evaluation. If the cache is missing or stale, use current workbook
    inputs instead of publishing an outdated value. This happens in the build
    pipeline, never in the browser.
    """
    cached = number(cached_value)
    evaluated = number(evaluated_value)
    if cached is None and evaluated is None:
        print(f"Warning: {label} missing for {member_id}; publishing null.", file=sys.stderr)
        return None
    if evaluated is None:
        return clean_amount(cached)
    if cached is None:
        print(f"Cached {label} missing for {member_id}; evaluated from workbook inputs.")
        return clean_amount(evaluated)
    if abs(cached - evaluated) > 1e-9:
        print(f"Cached {label} differs for {member_id} ({cached} vs {evaluated}); using current workbook inputs.")
        return clean_amount(evaluated)
    return clean_amount(cached)


members = {}

# Member Registry rows begin at row 6. Bond Record member rows begin at row 9,
# corresponding to registry row + 3. Current Bond Record layout uses:
# D:K = weekly entries, P = monthly earned, Q = deductions, R = overall net.
for r in range(6, 106):
    mid = text(reg.cell(r, 1).value).upper()
    name = text(reg.cell(r, 2).value)
    if not (mid and name):
        continue

    br = r + 3
    entries = []
    earned_from_entries = 0.0
    for c, week, entry in [
        (4, "Week 1", 1), (5, "Week 1", 2),
        (6, "Week 1", 3), (7, "Week 1", 4),
        (8, "Week 2", 1), (9, "Week 2", 2),
        (10, "Week 2", 3), (11, "Week 2", 4),
    ]:
        value = number(bond.cell(br, c).value)
        if value is not None and value != 0:
            earned_from_entries += value
            entries.append({"week": week, "entry": entry, "bonds": clean_amount(value)})

    # If future versions use additional weekly columns before the calculated
    # totals, do not accidentally treat P: S as activities. Current official
    # earning cells are D:K.
    deduction_fallback, _current_month_shop_fallback = month_transaction_totals(mid)
    # Shop spending is a public account-summary total of recorded shop
    # purchases. Keep the established portal behavior and include every
    # recorded shop purchase, even if a staff row has no date yet.
    shop_fallback = 0.0
    for rr in range(7, 207):
        tx_mid = text(ded.cell(rr, 3).value).upper()
        tx_type = text(ded.cell(rr, 5).value).upper()
        tx_amount = number(ded.cell(rr, 7).value)
        if tx_mid == mid and tx_type == "SHOP PURCHASE" and tx_amount is not None:
            shop_fallback += tx_amount

    monthly_fallback = earned_from_entries
    net_fallback = None

    # Monthly archive columns C:F are the finalized historical net snapshots.
    archive_total = 0.0
    for cc in range(3, 7):
        archive_total += number(arch.cell(r, cc).value) or 0.0
    net_fallback = archive_total + monthly_fallback - deduction_fallback

    status = text(reg.cell(r, 4).value).upper()
    if status not in ALLOWED_STATUSES:
        status = ""

    members[mid] = {
        "id": mid,
        "name": name,
        "rank": text(reg.cell(r, 3).value) or "—",
        "status": status,
        "joinDate": iso_date(reg.cell(r, 5).value) if reg.cell(r, 5).value else "",
        # Official award counts come directly from Member Registry F/G.
        "crests": int(number(reg.cell(r, 6).value) or 0),
        "medallion": int(number(reg.cell(r, 7).value) or 0),
        # Current Bond Record calculated columns are P/Q/R, not L/M/N.
        "monthlyEarned": calculated_bond_value(
            bond.cell(br, 16).value, monthly_fallback, "MONTHLY EARNED", mid
        ),
        "deductions": calculated_bond_value(
            bond.cell(br, 17).value, deduction_fallback, "DEDUCTIONS", mid
        ),
        "overallNet": calculated_bond_value(
            bond.cell(br, 18).value, net_fallback, "OVERALL NET", mid
        ),
        "shopSpending": clean_amount(shop_fallback),
        "weeklyEntries": entries,
    }

# Transactions are read directly from Deductions. Shop purchases remain outgoing
# Bonds and are reported separately from the workbook's authoritative deductions/net.
transactions = []
for r in range(7, 207):
    mid = text(ded.cell(r, 3).value).upper()
    date_value = ded.cell(r, 2).value
    typ = text(ded.cell(r, 5).value).upper()
    desc = text(ded.cell(r, 6).value)
    amount = number(ded.cell(r, 7).value)

    if not mid or mid not in members or typ not in TRANSACTION_TYPES or amount is None:
        continue

    transactions.append({
        "memberId": mid,
        "date": iso_date(date_value),
        "type": typ,
        "description": desc,
        "amount": clean_amount(amount),
    })

# Monthly Archive contains finalized historical values only.
monthly = {}
for r in range(6, 106):
    mid = text(arch.cell(r, 1).value).upper()
    if mid and mid in members:
        monthly[mid] = {
            "September": clean_amount(number(arch.cell(r, 3).value) or 0),
            "October": clean_amount(number(arch.cell(r, 4).value) or 0),
            "November": clean_amount(number(arch.cell(r, 5).value) or 0),
            "December": clean_amount(number(arch.cell(r, 6).value) or 0),
        }

# Only EARNED awards are public. Notes and recorder/admin fields are deliberately excluded.
awards = []
for r in range(7, 207):
    mid = text(awards_sheet.cell(r, 3).value).upper()
    category = text(awards_sheet.cell(r, 5).value).upper()
    name = text(awards_sheet.cell(r, 6).value)
    status = text(awards_sheet.cell(r, 7).value).upper()
    date_value = awards_sheet.cell(r, 2).value
    hosted_by = text(awards_sheet.cell(r, 9).value)

    if not mid or mid not in members:
        continue
    if category not in ALLOWED_AWARD_CATEGORIES:
        continue
    if status != "EARNED" or not name:
        continue

    award = {
        "memberId": mid,
        "date": iso_date(date_value),
        "category": category,
        "name": name,
        "status": "EARNED",
    }
    if hosted_by:
        award["hostedBy"] = hosted_by
    awards.append(award)

out = {
    "version": "1.3",
    "currency": "BONDS 💴",
    "source": "ELITE X Private Staff Records",
    "generatedAt": datetime.now().strftime("%Y-%m-%d"),
    "members": list(members.values()),
    "transactions": transactions,
    "awards": awards,
    "monthlyArchive": monthly,
    "bondGuidelines": BOND_GUIDELINES,
    "activityLog": [],
    "activityMappingNote": (
        "Current Activity Log has no Member ID, so detailed activity-log rows "
        "are not attributed to members. Bond Activity uses member-specific Bond Record entries."
    ),
}

with open("data.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

print("Wrote sanitized data.json")
print(f"Published members: {len(members)}")
print(f"Published earned awards: {len(awards)}")
      
