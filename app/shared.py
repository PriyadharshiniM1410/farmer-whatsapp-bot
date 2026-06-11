

from app.sheets import (
    get_all_sheet_data,
    get_market_allocations,
    get_sold_data,
    build_market_status_map,
    count_filled,
    compute_week_totals,
    MARKETS, PRODUCTS,
    MARKET_COL, CURR_DATA_START_ROW,
)

# ─── Config ────────────────────────────────────────────────────────────────
MANAGER_NUMBERS = {"918825877427"}   # Add more: "91XXXXXXXXXX"

# ─── Session store ─────────────────────────────────────────────────────────
# Shared keys (both roles):
#   mode             : str   — current bot state
#   market_id        : str   — e.g. "M3"
#
# Worker-specific:
#   allocations      : {product: float}
#   sold_data        : {product: float|None}
#   product_index    : int
#   edit_index       : int
#   pending_sold     : float
#   pending_idx      : int
#   return_to_review : bool
#
# Manager-specific:
#   mgr_context      : str   — "dashboard"|"status"|"summary"|"product_summary"|
#                              "market_review"|"market_edit"|"close_confirm"
#   edit_market_id   : str   — market being edited by manager
#   edit_product_idx : int   — product index being edited by manager
SESSIONS: dict = {}

PRODUCT_EMOJIS = ["🍎","🍌","🍅","🥔","🧅","🫘","🌶️","🍆","🥕","🍍"]
NUMBER_EMOJIS  = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
DAY_ICONS      = {"Monday": "🟦", "Wednesday": "🟧", "Friday": "🟥"}
DAYS_ORDER     = ["Monday", "Wednesday", "Friday"]


# ─── Sheet helpers ─────────────────────────────────────────────────────────
# ALL functions below accept optional all_data parameter.
# Pass pre-fetched all_data to avoid extra API calls.
# If not passed, fetches once from cache.

def _read_sold_data_from_sheet(market_id: str, all_data: list = None) -> dict:
    """
    Return {product: sold|None} for one market.

    OLD: made its own _calc_sheet() + get_all_values() call each time
    NEW: uses get_all_sheet_data() cache — no extra API call
    """
    try:
        if all_data is None:
            all_data = get_all_sheet_data()
        return get_sold_data(market_id, all_data)
    except Exception as exc:
        print(f"_read_sold_data_from_sheet error: {exc}")
        return {p: None for p in PRODUCTS}


def _build_market_status_map(all_data: list = None) -> dict:
    """
    Return {market_id: "complete"|"in_progress"|"not_started"}
    for all 12 markets.

    OLD: called _calc_sheet() + get_all_values() — 1 API call per status check
    NEW: uses get_all_sheet_data() cache — same data reused across all 12 markets
    """
    try:
        if all_data is None:
            all_data = get_all_sheet_data()
        return build_market_status_map(all_data)
    except Exception as exc:
        print(f"_build_market_status_map error: {exc}")
        return {mid: "not_started" for mid in MARKETS}


def _count_filled(market_id: str, all_data: list = None) -> int:
    """
    Count filled products for a market.

    OLD: called _read_sold_data_from_sheet() which made its own API call
    NEW: reuses all_data passed in — zero extra API calls
    """
    try:
        if all_data is None:
            all_data = get_all_sheet_data()
        return count_filled(market_id, all_data)
    except Exception as exc:
        print(f"_count_filled error: {exc}")
        return 0


def _compute_week_totals(all_data: list = None) -> dict:
    """
    Compute total_alloc and total_sold across all 12 markets.

    OLD: called get_market_allocations(mid) + _read_sold_data_from_sheet(mid)
         per market = 24 API calls for 12 markets → 429 error
    NEW: ONE get_all_sheet_data() call, all 12 markets read from same data
    """
    try:
        if all_data is None:
            all_data = get_all_sheet_data()
        return compute_week_totals(all_data)
    except Exception as exc:
        print(f"_compute_week_totals error: {exc}")
        return {"total_alloc": 0, "total_sold": 0}