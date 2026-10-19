"""Map a project control task to an ERP cost line. Master data rules live here."""
from datetime import date

WBS_TO_COST_CENTRE = {"A-100": "1000-01", "A-200": "1000-02", "B-100": "2000-01"}
CURRENCIES = {"DKK", "EUR"}


class ValidationError(ValueError):
    pass


def map_task(task):
    for field in ("id", "wbs", "amount_ore", "currency", "booked_on"):
        if task.get(field) in (None, ""):
            raise ValidationError(f"missing {field}")
    if task["wbs"] not in WBS_TO_COST_CENTRE:
        raise ValidationError(f"unknown wbs {task['wbs']}")
    if not isinstance(task["amount_ore"], int) or task["amount_ore"] < 0:
        raise ValidationError("amount_ore must be a whole number of at least 0")
    if task["currency"] not in CURRENCIES:
        raise ValidationError(f"unsupported currency {task['currency']}")
    try:
        date.fromisoformat(task["booked_on"])
    except ValueError:
        raise ValidationError(f"bad date {task['booked_on']}") from None
    return {"external_id": task["id"], "cost_centre": WBS_TO_COST_CENTRE[task["wbs"]], "amount_ore": task["amount_ore"],
            "currency": task["currency"], "booked_on": task["booked_on"], "text": task.get("title", "")}
