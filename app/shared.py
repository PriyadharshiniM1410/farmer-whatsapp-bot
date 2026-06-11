"""
shared.py — Common data, session store, and sheet helpers.
Imported by worker.py, manager.py, and bot_logic.py.
"""

from app.sheets import ( get_manager_numbers)

SESSIONS: dict = {}

PRODUCT_EMOJIS = ["🍎", "🍌", "🍅", "🥔", "🧅", "🫘", "🌶️", "🍆", "🥕", "🍍"]
DAY_ICONS      = {"Monday": "🟦", "Wednesday": "🟧", "Friday": "🟥"}
DAYS_ORDER     = ["Monday", "Wednesday", "Friday"]


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

