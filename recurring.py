"""Process due recurring expense templates into real expenses."""

import calendar
from datetime import datetime

import database as db


def _add_one_month(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    y, m = dt.year, dt.month
    if m == 12:
        y, m = y + 1, 1
    else:
        m += 1
    day = min(dt.day, calendar.monthrange(y, m)[1])
    return datetime(y, m, day).strftime("%Y-%m-%d")


def process_due(user_id: int) -> int:
    """Create expenses for recurring items due on or before today."""
    today = datetime.now().strftime("%Y-%m-%d")
    due_rows = db.get_due_recurring(user_id, today)
    posted = 0
    for row in due_rows:
        db.add_expense(
            user_id=user_id,
            amount=float(row["amount"]),
            description=f"{row['description']} (recurring)",
            category_id=int(row["category_id"]),
            date=today,
        )
        next_due = _add_one_month(row["next_due_date"])
        while next_due <= today:
            next_due = _add_one_month(next_due)
        db.update_recurring_next_due(int(row["id"]), user_id, next_due)
        posted += 1
    return posted
