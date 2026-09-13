"""
Generate the public ELITE X portal data from the PRIVATE Staff Records workbook.

Usage:
  python scripts/build_data.py "Elite-X Records.xlsx"

The generated data.json contains only member-facing fields.
Private workbook notes and internal award notes are never published.
"""
import sys
import json
from datetime import datetime, date
from openpyxl import load_workbook

if len(sys.argv) != 2:
    raise SystemExit("Usage: python scripts/build_data.py <private-workbook.xlsx>")

src = sys.argv[1]
wb = load_workbook(src, data_only=True)

reg = wb["Member Registry"]
bond = wb["Bond Record"]
ded = wb["Deductions"]
arch = wb["Monthly Archive"]
awards_sheet = wb["Awards & Achievements"]

ALLOWED_STATUSES = {"ACTIVE", "ON LEAVE", "INACTIVE", "RESIGNED", "REMOVED"}
ALLOWED_AWARD_CATEGORIES = {"MEDALLION", "CREST", "ACHIEVEMENT"}
ALLOWED_AWARD_STATUSES = {"EARNED", "PENDING", "REVOKED"}

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


members = {}

# Member Registry starts at row 6. Bond Record starts at row 9, so +3.
for r in range(6, 106):
    mid = text(reg.cell(r, 1).value)
    name = text(reg.cell(r, 2).value)

    if not (mid and name):
        continue

    br = r + 3
    entries = []

    for c, week, entry in [
        (4, "Week 1", 1), (5, "Week 1", 2),
        (6, "Week 1", 3), (7, "Week 1", 4),
        (8, "Week 2", 1), (9, "Week 2", 2),
        (10, "Week 2", 3), (11, "Week 2", 4),
    ]:
        value = number(bond.cell(br, c).value)
        if value is not None and value != 0:
            entries.append({
                "week": week,
                "entry": entry,
                "bonds": value,
            })

    status = text(reg.cell(r, 4).value).upper()
    if status not in ALLOWED_STATUSES:
        status = ""

    members[mid] = {
        "id": mid,
        "name": name,
        "rank": text(reg.cell(r, 3).value) or "—",
        "status": status,
        "joinDate": iso_date(reg.cell(r, 5).value) if reg.cell(r, 5).value else "",
        # Official award counts come directly from Member Registry.
        "crests": int(number(reg.cell(r, 6).value) or 0),
        "medallion": int(number(reg.cell(r, 7).value) or 0),
        # These values are authoritative calculated values from Bond Record.
        "monthlyEarned": number(bond.cell(br, 12).value),
        "deductions": number(bond.cell(br, 13).value),
        "overallNet": number(bond.cell(br, 14).value),
        "weeklyEntries": entries,
    }

# Transactions are read directly from Deductions. Shop purchases remain outgoing
# Bonds and are reported separately from the workbook's authoritative deductions/net.
transactions = []
shop_spending = {mid: 0.0 for mid in members}

for r in range(7, 207):
    mid = text(ded.cell(r, 3).value).upper()
    date_value = ded.cell(r, 2).value
    typ = text(ded.cell(r, 5).value).upper()
    desc = text(ded.cell(r, 6).value)
    amount = number(ded.cell(r, 7).value)

    if not mid or mid not in members or not typ or amount is None:
        continue

    transactions.append({
        "memberId": mid,
        "date": iso_date(date_value),
        "type": typ,
        "description": desc,
        "amount": amount,
    })

    if typ == "SHOP PURCHASE":
        shop_spending[mid] = shop_spending.get(mid, 0.0) + amount

for mid, member in members.items():
    member["shopSpending"] = shop_spending.get(mid, 0.0)

# Monthly Archive contains finalized historical values only.
monthly = {}
for r in range(6, 106):
    mid = text(arch.cell(r, 1).value).upper()
    if mid and mid in members:
        monthly[mid] = {
            "September": number(arch.cell(r, 3).value) or 0,
            "October": number(arch.cell(r, 4).value) or 0,
            "November": number(arch.cell(r, 5).value) or 0,
            "December": number(arch.cell(r, 6).value) or 0,
        }

# Only EARNED awards are public. Notes are deliberately excluded.
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
    if status not in ALLOWED_AWARD_STATUSES or status != "EARNED" or not name:
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
    "version": "1.2",
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
      
