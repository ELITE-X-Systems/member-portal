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

ALLOWED_AWARD_CATEGORIES = {"MEDALLION", "CREST", "ACHIEVEMENT"}
ALLOWED_AWARD_STATUSES = {"EARNED", "PENDING", "REVOKED"}

def text(value):
    return str(value).strip() if value is not None else ""

def iso_date(value):
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    return text(value)

members = {}

for r in range(6, 106):
    mid = text(reg.cell(r, 1).value)
    name = text(reg.cell(r, 2).value)

    if not (mid and name):
        continue

    # Bond Record rows mirror Member Registry rows with a +3 offset.
    br = r + 3
    entries = []

    for c, week, entry in [
        (4, "Week 1", 1), (5, "Week 1", 2),
        (6, "Week 1", 3), (7, "Week 1", 4),
        (8, "Week 2", 1), (9, "Week 2", 2),
        (10, "Week 2", 3), (11, "Week 2", 4)
    ]:
        value = bond.cell(br, c).value
        if value not in (None, 0, ""):
            entries.append({
                "week": week,
                "entry": entry,
                "bonds": float(value)
            })

    join_date = reg.cell(r, 5).value

    members[mid] = {
        "id": mid,
        "name": name,
        "rank": text(reg.cell(r, 3).value) or "Initiate",
        "status": text(reg.cell(r, 4).value),
        "joinDate": iso_date(join_date) if join_date else "",
        "crests": int(float(reg.cell(r, 6).value or 0)),
        "medallion": int(float(reg.cell(r, 7).value or 0)),
        # ID status is retained because it is an existing public portal field.
        "idStatus": text(bond.cell(br, 15).value),
        "monthlyEarned": float(bond.cell(br, 12).value or 0),
        "deductions": float(bond.cell(br, 13).value or 0),
        "overallNet": float(bond.cell(br, 14).value or 0),
        "weeklyEntries": entries
    }

transactions = []

for r in range(7, 207):
    mid = text(ded.cell(r, 3).value)
    date_value = ded.cell(r, 2).value
    typ = text(ded.cell(r, 5).value)
    desc = text(ded.cell(r, 6).value)
    amount = ded.cell(r, 7).value

    if mid and typ and amount is not None:
        transactions.append({
            "memberId": mid,
            "date": iso_date(date_value),
            "type": typ,
            "description": desc,
            "amount": float(amount)
        })

monthly = {}

for r in range(6, 106):
    mid = text(arch.cell(r, 1).value)

    if mid and mid in members:
        monthly[mid] = {
            "September": float(arch.cell(r, 3).value or 0),
            "October": float(arch.cell(r, 4).value or 0),
            "November": float(arch.cell(r, 5).value or 0),
            "December": float(arch.cell(r, 6).value or 0)
        }

# Only EARNED awards are published to the public portal.
# Pending/revoked records remain private staff-record information.
awards = []

for r in range(7, 207):
    mid = text(awards_sheet.cell(r, 3).value)
    category = text(awards_sheet.cell(r, 5).value).upper()
    name = text(awards_sheet.cell(r, 6).value)
    status = text(awards_sheet.cell(r, 7).value).upper()
    date_value = awards_sheet.cell(r, 2).value
    hosted_by = text(awards_sheet.cell(r, 9).value)

    if not mid or mid not in members:
        continue

    if category not in ALLOWED_AWARD_CATEGORIES:
        continue

    if status not in ALLOWED_AWARD_STATUSES:
        continue

    if status != "EARNED" or not name:
        continue

    award = {
        "memberId": mid,
        "date": iso_date(date_value),
        "category": category,
        "name": name,
        "status": "EARNED"
    }

    if hosted_by:
        award["hostedBy"] = hosted_by

    awards.append(award)

out = {
    "version": "1.1",
    "currency": "BONDS 💴",
    "source": "ELITE X Private Staff Records",
    "generatedAt": datetime.now().strftime("%Y-%m-%d"),
    "members": list(members.values()),
    "transactions": transactions,
    "awards": awards,
    "monthlyArchive": monthly,
    "activityLog": [],
    "activityMappingNote": (
        "Current Activity Log has no Member ID, so detailed activity-log rows "
        "are not attributed to members."
    )
}

with open("data.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

print("Wrote sanitized data.json")
print(f"Published members: {len(members)}")
print(f"Published earned awards: {len(awards)}")
  
