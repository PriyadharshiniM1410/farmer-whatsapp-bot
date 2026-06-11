"""
shared.py — Common data, session store, sheet helpers
======================================================
Imported by worker.py, manager.py, bot_logic.py

"""

from app.sheets import (
    get_all_sheet_data,
    get_market_allocations,
    get_sold_data,
    build_market_status_map,
    count_filled,
    compute_week_totals,
    get_manager_numbers,        # ← NEW: from Details tab
    MARKETS, PRODUCTS,
    MARKET_COL, CURR_DATA_START_ROW,
)

# ─── Session store ─────────────────────────────────────────────────────────
SESSIONS: dict = {}

# ─── Display helpers ───────────────────────────────────────────────────────
PRODUCT_EMOJIS = ["🍎","🍌","🍅","🥔","🧅","🫘","🌶️","🍆","🥕","🍍"]
NUMBER_EMOJIS  = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
DAY_ICONS      = {"Monday": "🟦", "Wednesday": "🟧", "Friday": "🟥"}
DAYS_ORDER     = ["Monday", "Wednesday", "Friday"]

# ─── Manager numbers ───────────────────────────────────────────────────────
# Fetched fresh from Details tab each time is_manager() is called.
# No hardcoding — manager changes in sheet reflect immediately.
"""
def is_manager(phone: str) -> bool:
    
    Check if a phone number belongs to a manager.
    Reads from Details tab via sheets.py cache (60s TTL).
    
    try:
        return str(phone).strip() in get_manager_numbers()
    except Exception as exc:
        print(f"is_manager error: {exc}")
        return False
    
"""
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

# Keep MANAGER_NUMBERS as a property-like callable for
# backward compatibility with any code that does:
#   sender in MANAGER_NUMBERS
# Usage: replace  `sender in MANAGER_NUMBERS`
#         with    `is_manager(sender)`
# But also expose a set for legacy use if needed:
def get_manager_numbers_set() -> set:
    try:
        return get_manager_numbers()
    except Exception:
        return set()


# ─── Sheet helpers ─────────────────────────────────────────────────────────
# All functions accept optional all_data to avoid extra API calls.

def _read_sold_data_from_sheet(market_id: str, all_data: list = None) -> dict:
    """Return {product: sold|None} for one market."""
    try:
        if all_data is None:
            all_data = get_all_sheet_data()
        return get_sold_data(market_id, all_data)
    except Exception as exc:
        print(f"_read_sold_data_from_sheet error: {exc}")
        return {p: None for p in PRODUCTS}


def _build_market_status_map(all_data: list = None) -> dict:
    """Return {market_id: complete|in_progress|not_started} for all 12."""
    try:
        if all_data is None:
            all_data = get_all_sheet_data()
        return build_market_status_map(all_data)
    except Exception as exc:
        print(f"_build_market_status_map error: {exc}")
        return {mid: "not_started" for mid in MARKETS}


def _count_filled(market_id: str, all_data: list = None) -> int:
    """Count filled products for a market."""
    try:
        if all_data is None:
            all_data = get_all_sheet_data()
        return count_filled(market_id, all_data)
    except Exception as exc:
        print(f"_count_filled error: {exc}")
        return 0


def _compute_week_totals(all_data: list = None) -> dict:
    """Total allocated + sold across all 12 markets."""
    try:
        if all_data is None:
            all_data = get_all_sheet_data()
        return compute_week_totals(all_data)
    except Exception as exc:
        print(f"_compute_week_totals error: {exc}")
        return {"total_alloc": 0, "total_sold": 0}