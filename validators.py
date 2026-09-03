from datetime import datetime


def validate_month_str(month: str) -> tuple[bool, str]:
    """Validate YYYY-MM budget month format."""
    month = (month or "").strip()
    if not month:
        return False, "Month is required."
    try:
        datetime.strptime(month, "%Y-%m")
    except ValueError:
        return False, "Month must be in YYYY-MM format (e.g. 2026-07)."
    return True, month


def validate_expense_form(amount: str, description: str, category_id: str, date: str) -> tuple[list[str], dict | None]:
    errors: list[str] = []
    cleaned: dict = {}

    try:
        amount_val = float((amount or "").strip())
        if amount_val <= 0:
            errors.append("Amount must be greater than 0.")
        else:
            cleaned["amount"] = amount_val
    except ValueError:
        errors.append("Amount must be a valid number.")

    desc = (description or "").strip()
    if not desc:
        errors.append("Description cannot be empty.")
    else:
        cleaned["description"] = desc

    if not (category_id or "").strip():
        errors.append("Please select a category.")
    else:
        cleaned["category_id"] = int(category_id)

    date_val = (date or "").strip()
    if not date_val:
        errors.append("Please select a date.")
    else:
        try:
            datetime.strptime(date_val, "%Y-%m-%d")
            cleaned["date"] = date_val
        except ValueError:
            errors.append("Date must be in YYYY-MM-DD format.")

    if errors:
        return errors, None
    return [], cleaned
