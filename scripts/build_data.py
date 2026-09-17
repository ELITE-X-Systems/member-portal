"""Build public ELITE X portal data from the private Excel workbook."""

import json
import sys
from datetime import date, datetime
from pathlib import Path

from openpyxl import load_workbook


# ------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------

ALLOWED_STATUS = {
    "ACTIVE",
    "ON LEAVE",
    "INACTIVE",
    "RESIGNED",
    "REMOVED",
}

ALLOWED_AWARD_CATEGORIES = {
    "MEDALLION",
    "CREST",
    "ACHIEVEMENT",
}

TRANSACTION_TYPES = {
    "DEDUCTION",
    "SHOP PURCHASE",
}


# ------------------------------------------------------------
# BASIC HELPERS
# ------------------------------------------------------------

def text(value):
    return str(value).strip() if value is not None else ""


def norm(value):
    return text(value).upper()


def number(value):
    if value in (None, ""):
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def clean_number(value):
    value = number(value)

    if value is None:
        return None

    return int(value) if value.is_integer() else value


def iso_date(value):
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")

    return text(value)


def headers(sheet, row):
    """Return a normalized header -> column map."""

    return {
        norm(sheet.cell(row, column).value): column
        for column in range(1, sheet.max_column + 1)
        if text(sheet.cell(row, column).value)
    }


def require_headers(sheet, row, required):
    result = headers(sheet, row)

    missing = [
        item
        for item in required
        if norm(item) not in result
    ]

    if missing:
        raise ValueError(
            f"{sheet.title}: missing header(s): {', '.join(missing)}"
        )

    return result


def canonical_week(value):
    """Convert 1, 1.0, '1', 'Week 1', etc. into 'Week 1'."""

    numeric = number(value)

    if numeric is not None and numeric.is_integer():
        return f"Week {int(numeric)}"

    raw = text(value)

    digits = "".join(
        char for char in raw
        if char.isdigit()
    )

    if digits:
        return f"Week {int(digits)}"

    return raw


# ------------------------------------------------------------
# ACTIVITY LOG
# ------------------------------------------------------------

def read_activity_log(sheet):
    """
    Activity Log:
    A = ID
    B = DATE
    C = ACTIVITY NAME
    D = TYPE
    E = WEEK
    F = # ENTRY
    """

    h = require_headers(
        sheet,
        6,
        [
            "ID",
            "DATE",
            "ACTIVITY NAME",
            "TYPE",
            "WEEK",
            "# ENTRY",
        ],
    )

    activities = []

    for row in range(7, sheet.max_row + 1):

        name = text(
            sheet.cell(row, h[norm("ACTIVITY NAME")]).value
        )

        week = canonical_week(
            sheet.cell(row, h[norm("WEEK")]).value
        )

        entry = number(
            sheet.cell(row, h[norm("# ENTRY")]).value
        )

        if not name or not week or entry is None:
            continue

        activities.append(
            {
                "week": week,
                "entry": int(entry),
                "name": name,
                "type": (
                    text(
                        sheet.cell(
                            row,
                            h[norm("TYPE")]
                        ).value
                    )
                    or "RECORDED ACTIVITY"
                ),
                "date": iso_date(
                    sheet.cell(
                        row,
                        h[norm("DATE")]
                    ).value
                ),
            }
        )

    return activities


# ------------------------------------------------------------
# BOND RECORD
# ------------------------------------------------------------

def read_bond_record(sheet, activity_log):

    h = require_headers(
        sheet,
        7,
        [
            "MEMBER ID",
            "MEMBER",
            "RANK",
            "MONTHLY EARNED 💴",
            "DEDUCTIONS 💴",
            "OVERALL NET 💴",
            "STATUS",
        ],
    )

    # Convert activity records into a lookup table.
    #
    # IMPORTANT:
    # We use a string key instead of a tuple so that nothing
    # containing this lookup is accidentally written to JSON.
    activity_lookup = {}

    for activity in activity_log:

        key = (
            activity["week"].upper()
            + "|"
            + str(activity["entry"])
        )

        activity_lookup[key] = activity

    # Detect the weekly activity columns from the spreadsheet.
    activity_columns = []
    current_week = None

    for column in range(1, sheet.max_column + 1):

        week_header = text(
            sheet.cell(7, column).value
        )

        activity_header = norm(
            sheet.cell(8, column).value
        )

        if week_header.upper().startswith("WEEK "):
            current_week = canonical_week(
                week_header
            )

        if (
            current_week
            and activity_header.startswith("ACTIVITY")
        ):

            activity_number = number(
                activity_header
                .replace("ACTIVITY", "")
                .replace("💴", "")
                .strip()
            )

            if activity_number is not None:

                activity_columns.append(
                    (
                        column,
                        current_week,
                        int(activity_number),
                    )
                )

    members = {}

    for row in range(9, sheet.max_row + 1):

        member_id = norm(
            sheet.cell(
                row,
                h[norm("MEMBER ID")]
            ).value
        )

        name = text(
            sheet.cell(
                row,
                h[norm("MEMBER")]
            ).value
        )

        if not member_id or not name:
            continue

        weekly_entries = []

        for column, week, entry_number in activity_columns:

            bonds = clean_number(
                sheet.cell(row, column).value
            )

            if bonds in (None, 0):
                continue

            key = (
                week.upper()
                + "|"
                + str(entry_number)
            )

            activity = activity_lookup.get(
                key,
                {}
            )

            weekly_entries.append(
                {
                    "week": week,
                    "entry": entry_number,
                    "bonds": bonds,
                    "name": activity.get(
                        "name",
                        f"Activity {entry_number}"
                    ),
                    "type": activity.get(
                        "type",
                        "RECORDED ACTIVITY"
                    ),
                    "date": activity.get(
                        "date",
                        ""
                    ),
                }
            )

        status = norm(
            sheet.cell(
                row,
                h[norm("STATUS")]
            ).value
        )

        members[member_id] = {
            "id": member_id,
            "name": name,
            "rank": (
                text(
                    sheet.cell(
                        row,
                        h[norm("RANK")]
                    ).value
                )
                or "—"
            ),
            "status": (
                status
                if status in ALLOWED_STATUS
                else ""
            ),
            "monthlyEarned": clean_number(
                sheet.cell(
                    row,
                    h[norm("MONTHLY EARNED 💴")]
                ).value
            ),
            "deductions": clean_number(
                sheet.cell(
                    row,
                    h[norm("DEDUCTIONS 💴")]
                ).value
            ),
            "overallNet": clean_number(
                sheet.cell(
                    row,
                    h[norm("OVERALL NET 💴")]
                ).value
            ),
            "weeklyEntries": weekly_entries,
        }

    return members


# ------------------------------------------------------------
# MEMBER REGISTRY
# ------------------------------------------------------------

def read_registry(sheet, members):

    h = require_headers(
        sheet,
        5,
        [
            "MEMBER ID",
            "MEMBER",
            "RANK",
            "STATUS",
            "JOIN DATE",
            "Crests",
            "Medallion",
        ],
    )

    id_column = h[norm("MEMBER ID")]

    registry_rows = {}

    for row in range(6, sheet.max_row + 1):

        member_id = norm(
            sheet.cell(row, id_column).value
        )

        if member_id:
            registry_rows[member_id] = row

    for member_id, member in members.items():

        row = registry_rows.get(member_id)

        if row is None:
            continue

        member["name"] = (
            text(
                sheet.cell(
                    row,
                    h[norm("MEMBER")]
                ).value
            )
            or member["name"]
        )

        member["rank"] = (
            text(
                sheet.cell(
                    row,
                    h[norm("RANK")]
                ).value
            )
            or member["rank"]
        )

        status = norm(
            sheet.cell(
                row,
                h[norm("STATUS")]
            ).value
        )

        if status in ALLOWED_STATUS:
            member["status"] = status

        member["joinDate"] = iso_date(
            sheet.cell(
                row,
                h[norm("JOIN DATE")]
            ).value
        )

        member["crests"] = int(
            number(
                sheet.cell(
                    row,
                    h[norm("Crests")]
                ).value
            )
            or 0
        )

        member["medallion"] = int(
            number(
                sheet.cell(
                    row,
                    h[norm("Medallion")]
                ).value
            )
            or 0
        )

    return members


# ------------------------------------------------------------
# ATTENDANCE
# ------------------------------------------------------------

def read_attendance(sheet, members):

    h = require_headers(
        sheet,
        7,
        [
            "MEMBER ID",
            "MEMBER",
            "ATTENDANCE BONDS 💴",
        ],
    )

    # Actual workbook structure:
    #
    # Week 1 = C:G
    # Week 2 = I:M
    # Week 3 = O:S
    # Week 4 = U:Y
    #
    # P.Att. columns are H, N, T, Z.
    # Attendance Bonds are AB.

    week_columns = []
    current_week = None

    for column in range(1, sheet.max_column + 1):

        week_header = text(
            sheet.cell(7, column).value
        )

        day_header = norm(
            sheet.cell(8, column).value
        )

        if week_header.upper().startswith("WEEK "):
            current_week = canonical_week(
                week_header
            )

        if (
            current_week
            and day_header == "MON"
        ):
            week_columns.append(
                (
                    current_week,
                    column
                )
            )

    for row in range(9, sheet.max_row + 1):

        member_id = norm(
            sheet.cell(
                row,
                h[norm("MEMBER ID")]
            ).value
        )

        if member_id not in members:
            continue

        weeks = []
        perfect_weeks = 0
        present_total = 0
        required_total = 0

        for week, monday_column in week_columns:

            values = [
                norm(
                    sheet.cell(
                        row,
                        monday_column + offset
                    ).value
                )
                for offset in range(5)
            ]

            present_days = sum(
                value == "✓"
                for value in values
            )

            perfect = present_days == 5

            if perfect:
                perfect_weeks += 1

            present_total += present_days
            required_total += 5

            labels = [
                "MON",
                "TUE",
                "WED",
                "THU",
                "FRI",
            ]

            weeks.append(
                {
                    "week": week,
                    "presentDays": present_days,
                    "requiredDays": 5,
                    "perfect": perfect,
                    "days": [
                        {
                            "label": labels[index],
                            "present": (
                                values[index] == "✓"
                            ),
                        }
                        for index in range(5)
                    ],
                }
            )

        members[member_id]["attendance"] = {
            "weeks": weeks,
            "perfectWeeks": perfect_weeks,
            "totalWeeks": len(week_columns),
            "perfectChronicle": (
                bool(week_columns)
                and perfect_weeks == len(week_columns)
            ),
            "bonus": (
                clean_number(
                    sheet.cell(
                        row,
                        h[norm("ATTENDANCE BONDS 💴")]
                    ).value
                )
                or 0
            ),
            "presentDays": present_total,
            "requiredDays": required_total,
        }

    return members


# ------------------------------------------------------------
# DEDUCTIONS / SHOP
# ------------------------------------------------------------

def read_transactions(sheet, members):

    h = require_headers(
        sheet,
        6,
        [
            "ID",
            "DATE",
            "MEMBER ID",
            "TRANSACTION TYPE",
            "REASON / ITEM",
            "AMOUNT 💴",
        ],
    )

    transactions = []

    for row in range(7, sheet.max_row + 1):

        member_id = norm(
            sheet.cell(
                row,
                h[norm("MEMBER ID")]
            ).value
        )

        transaction_type = norm(
            sheet.cell(
                row,
                h[norm("TRANSACTION TYPE")]
            ).value
        )

        amount = number(
            sheet.cell(
                row,
                h[norm("AMOUNT 💴")]
            ).value
        )

        if (
            member_id not in members
            or transaction_type not in TRANSACTION_TYPES
            or amount is None
        ):
            continue

        transactions.append(
            {
                "memberId": member_id,
                "date": iso_date(
                    sheet.cell(
                        row,
                        h[norm("DATE")]
                    ).value
                ),
                "type": transaction_type,
                "description": text(
                    sheet.cell(
                        row,
                        h[norm("REASON / ITEM")]
                    ).value
                ),
                "amount": clean_number(amount),
            }
        )

    return transactions


# ------------------------------------------------------------
# AWARDS
# ------------------------------------------------------------

def read_awards(sheet, members):

    h = require_headers(
        sheet,
        6,
        [
            "AWARD ID",
            "DATE",
            "MEMBER ID",
            "CATEGORY",
            "AWARD / ACHIEVEMENT",
            "STATUS",
        ],
    )

    awards = []

    for row in range(7, sheet.max_row + 1):

        member_id = norm(
            sheet.cell(
                row,
                h[norm("MEMBER ID")]
            ).value
        )

        category = norm(
            sheet.cell(
                row,
                h[norm("CATEGORY")]
            ).value
        )

        status = norm(
            sheet.cell(
                row,
                h[norm("STATUS")]
            ).value
        )

        name = text(
            sheet.cell(
                row,
                h[norm("AWARD / ACHIEVEMENT")]
            ).value
        )

        if (
            member_id not in members
            or category not in ALLOWED_AWARD_CATEGORIES
            or status != "EARNED"
            or not name
        ):
            continue

        awards.append(
            {
                "memberId": member_id,
                "date": iso_date(
                    sheet.cell(
                        row,
                        h[norm("DATE")]
                    ).value
                ),
                "category": category,
                "name": name,
                "status": "EARNED",
            }
        )

    return awards


# ------------------------------------------------------------
# MONTHLY ARCHIVE
# ------------------------------------------------------------

def read_monthly_archive(sheet, members):

    h = require_headers(
        sheet,
        5,
        [
            "MEMBER ID",
            "MEMBER",
        ],
    )

    archive = {}

    id_column = h[norm("MEMBER ID")]

    rows = {}

    for row in range(6, sheet.max_row + 1):

        member_id = norm(
            sheet.cell(row, id_column).value
        )

        if member_id:
            rows[member_id] = row

    for member_id in members:

        row = rows.get(member_id)

        if row is None:
            continue

        values = {}

        for column in range(3, sheet.max_column + 1):

            label = text(
                sheet.cell(5, column).value
            )

            if not label:
                continue

            value = clean_number(
                sheet.cell(row, column).value
            )

            if value is not None:
                values[label.title()] = value

        archive[member_id] = values

    return archive


# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------

def main():

    if len(sys.argv) != 2:
        raise SystemExit(
            "Usage: python scripts/build_data.py <private-workbook.xlsx>"
        )

    source = Path(sys.argv[1])

    if not source.exists():
        raise SystemExit(
            f"Workbook not found: {source}"
        )

    workbook = load_workbook(
        source,
        data_only=True
    )

    sheets = {
        name: workbook[name]
        for name in [
            "Member Registry",
            "Bond Record",
            "ATTENDANCE",
            "Deductions",
            "Awards & Achievements",
            "Monthly Archive",
            "Activity Log",
        ]
    }

    # Read the private workbook.
    activity_log = read_activity_log(
        sheets["Activity Log"]
    )

    members = read_bond_record(
        sheets["Bond Record"],
        activity_log
    )

    members = read_registry(
        sheets["Member Registry"],
        members
    )

    members = read_attendance(
        sheets["ATTENDANCE"],
        members
    )

    transactions = read_transactions(
        sheets["Deductions"],
        members
    )

    awards = read_awards(
        sheets["Awards & Achievements"],
        members
    )

    monthly_archive = read_monthly_archive(
        sheets["Monthly Archive"],
        members
    )

   # Public reference rules.
    guidelines = [
        {
            "label": "ATTENDANCE",
            "value": "2 Bonds",
            "detail": "Per attendance · Tuesday–Friday",
        },
        {
            "label": "ID INSPECTION",
            "value": "5 Bonds",
            "detail": "Per ID check · Monday",
        },
        {
            "label": "GAMBIT",
            "value": "+5–10 Bonds",
            "detail": "Maximum 30 per chronicle",
        },
        {
            "label": "CONQUEST",
            "value": "+15–20 Bonds",
            "detail": "Maximum 50 per chronicle",
        },
        {
            "label": "COMMISSION",
            "value": "+20–30 Bonds",
            "detail": "Maximum 50 per chronicle",
        },
        {
            "label": "WEEKLY LIMIT",
            "value": "100 Bonds",
            "detail": "Maximum earned per member per week",
        },
    ]

    output = {
        "version": "2.0",
        "currency": "BONDS 💴",
        "source": "ELITE X Private Staff Records",
        "generatedAt": date.today().isoformat(),
        "members": list(members.values()),
        "transactions": transactions,
        "awards": awards,
        "monthlyArchive": monthly_archive,
        "bondGuidelines": guidelines,

        # IMPORTANT:
        # This is now a LIST, not a dictionary with tuple keys.
        # Therefore JSON can serialize it safely.
        "activityLog": activity_log,
    }

    with open(
        "data.json",
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            output,
            file,
            ensure_ascii=False,
            indent=2
        )

    print(
        "Wrote data.json · "
        f"members={len(members)} · "
        f"transactions={len(transactions)} · "
        f"awards={len(awards)} · "
        f"activities={len(activity_log)}"
    )


if __name__ == "__main__":
    main()
