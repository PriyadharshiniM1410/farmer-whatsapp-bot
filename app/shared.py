"""
shared.py — Common data, session store, and sheet helpers.
Imported by worker.py, manager.py, and bot_logic.py.
"""

from app.sheets import get_manager_numbers, get_days_in_order

SESSIONS: dict = {}

# Icons for known market days. If a new/unexpected day name ever shows up
# on the sheet, get_day_icon() falls back to DEFAULT_DAY_ICON instead of
# breaking — no need to hardcode every possible day here.
DAY_ICONS = {"Monday": "🟦", "Wednesday": "🟧", "Friday": "🟥"}
DEFAULT_DAY_ICON = "⬜"


def is_manager(phone: str) -> bool:
    try:
        managers = get_manager_numbers()
        phone_last10 = str(phone).strip()[-10:]
        manager_last10 = {
            str(m).strip()[-10:]
            for m in managers
            if str(m).strip()
        }
        print("PHONE:", phone_last10)
        print("MANAGERS:", manager_last10)
        return phone_last10 in manager_last10
    except Exception as exc:
        print(f"is_manager error: {exc}")
        return False


def get_manager_numbers_set() -> set:
    try:
        return get_manager_numbers()
    except Exception:
        return set()


def get_days_order() -> list:
    """Market days in sheet order (e.g. ['Monday', 'Wednesday', 'Friday']),
    read dynamically from the Calculation sheet instead of hardcoded."""
    try:
        return get_days_in_order()
    except Exception as exc:
        print(f"get_days_order error: {exc}")
        return []


def get_day_icon(day: str) -> str:
    return DAY_ICONS.get(day, DEFAULT_DAY_ICON)