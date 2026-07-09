import re
import time
import json
import os
import gspread
from google.oauth2.service_account import Credentials
from config import SHEET_ID, CREDS_FILE

CACHE_FILE = "sheet_data_cache.json"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

PRODUCT_EMOJI_MAP = {
    "apple":        "🍎",
    "banana":       "🍌",
    "tomato":       "🍅",
    "potato":       "🥔",
    "onion":        "🧅",
    "beans":        "🫘",
    "chilli":       "🌶️",
    "chili":        "🌶️",
    "brinjal":      "🍆",
    "eggplant":     "🍆",
    "carrot":       "🥕",
    "pine apple":   "🍍",
    "pineapple":    "🍍",
    "guava":        "🍈",
    "mango":        "🥭",
    "grapes":       "🍇",
    "orange":       "🍊",
    "lemon":        "🍋",
    "lime":         "🍋",
    "watermelon":   "🍉",
    "papaya":       "🫐",
    "cucumber":     "🥒",
    "cabbage":      "🥬",
    "cauliflower":  "🥦",
    "broccoli":     "🥦",
    "ginger":       "🫚",
    "garlic":       "🧄",
    "corn":         "🌽",
    "peas":         "🫛",
    "mushroom":     "🍄",
    "pumpkin":      "🎃",
    "sweet potato": "🍠",
    "beetroot":     "🍠",
    "coconut":      "🥥",
    "peach":        "🍑",
    "pear":         "🍐",
    "kiwi":         "🥝",
    "strawberry":   "🍓",
    "cherry":       "🍒",
    "avocado":      "🥑",
}
DEFAULT_EMOJI = "📦"


def get_product_emoji(product_name: str) -> str:
    """Return an emoji for a product name (case-insensitive), or a default box emoji."""
    return PRODUCT_EMOJI_MAP.get(str(product_name).strip().lower(), DEFAULT_EMOJI)


CALC_SHEET_NAME    = "Calculation"
DETAILS_SHEET_NAME = "Details"

# Column (0-based) in the Calculation sheet that holds the product name.
PRODUCT_COL = 2  # column C

DETAILS_WORKER_START_ROW = 5
DETAILS_COL_W_NO         = 6
DETAILS_COL_W_NAME       = 7
DETAILS_COL_W_PHONE      = 8
DETAILS_COL_W_MONDAY     = 9
DETAILS_COL_W_WEDNESDAY  = 10
DETAILS_COL_W_FRIDAY     = 11

DETAILS_COL_M_NO    = 1
DETAILS_COL_M_NAME  = 2
DETAILS_COL_M_PHONE = 3

_CACHE: dict        = {"data": None, "ts": 0.0}
_WORKER_CACHE: dict = {"data": None, "ts": 0.0}
CACHE_TTL        = 30
WORKER_CACHE_TTL = 60


# ── Connection ────────────────────────────────────────────────────────────
def _client():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if creds_json:
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPES)
    return gspread.authorize(creds)

def _spreadsheet():
    return _client().open_by_key(SHEET_ID)

def _calc_sheet():
    return _spreadsheet().worksheet(CALC_SHEET_NAME)

def _details_sheet():
    return _spreadsheet().worksheet(DETAILS_SHEET_NAME)


# ── Cache ─────────────────────────────────────────────────────────────────

def _load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            try:
                return json.load(f)
            except Exception:
                return {"data": None, "ts": 0}
    return {"data": None, "ts": 0}


def get_all_sheet_data(force: bool = False) -> list:
    cache = _load_cache()
    if not force and cache["data"] is not None and (time.time() - cache["ts"]) < CACHE_TTL:
        return cache["data"]
    ws = _calc_sheet()
    data = ws.get_all_values()
    with open(CACHE_FILE, "w") as f:
        json.dump({"data": data, "ts": time.time()}, f)
    return data


def invalidate_cache():
    if os.path.exists(CACHE_FILE):
        os.remove(CACHE_FILE)


# ── Helpers ───────────────────────────────────────────────────────────────

def _safe_float(val) -> float | None:
    """Convert cell value to float. Returns None if blank or invalid."""
    if val is None or str(val).strip() == "":
        return None
    try:
        return float(str(val).replace(",", "").replace("%", "").strip())
    except ValueError:
        return None


def _forward_fill(row: list) -> list:
    """Fill blank cells with the last non-blank value seen to the left.
    Needed because merged cells (like the Monday/Wednesday/Friday day
    header) only carry their value in the first cell of the merge."""
    filled = []
    last = ""
    for v in row:
        v = str(v).strip()
        if v:
            last = v
        filled.append(last)
    return filled


_MARKET_ID_RE = re.compile(r"^M\d+$")


def _find_market_header_row(all_data: list):
    """Scan the sheet and find the row that lists the market IDs (M1, M2, ...).
    Returns the 0-based row index, or None if not found."""
    for idx, row in enumerate(all_data):
        matches = sum(1 for cell in row if _MARKET_ID_RE.match(str(cell).strip()))
        if matches >= 2:
            return idx
    return None


# ── Read: Calculation sheet layout (fully dynamic) ─────────────────────────

def build_market_map(all_data: list = None) -> dict:
    """Dynamically discover every market on the Calculation sheet: its column
    position, its Final Allocated / Sold Boxes columns, and which day it
    belongs to (Monday/Wednesday/Friday/etc — read straight from the sheet,
    not hardcoded).

    Returns: { "M1": {"start_col": 3, "final_alloc_col": 5, "sold_col": 6, "day": "Monday"}, ... }
    (columns are 0-based, matching gspread's get_all_values() list format)
    """
    if all_data is None:
        all_data = get_all_sheet_data()

    market_row_idx = _find_market_header_row(all_data)
    if market_row_idx is None:
        return {}

    market_row = all_data[market_row_idx]
    day_row = all_data[market_row_idx - 1] if market_row_idx - 1 >= 0 else []
    
    """Only forward-fill starting from the first market's column. Otherwise a
    row label like "Day" sitting in an earlier column (e.g. column C) can
    bleed into market columns that genuinely don't have their own day text
    yet (e.g. if a day's merged header cell is misaligned in the sheet)."""
    
    market_cols = [c for c, v in enumerate(market_row) if _MARKET_ID_RE.match(str(v).strip())]
    first_market_col = min(market_cols) if market_cols else 0
    day_row_filled = ([""] * first_market_col
                       + _forward_fill(day_row[first_market_col:]))

    markets = {}
    for col_idx, val in enumerate(market_row):
        val = str(val).strip()
        if _MARKET_ID_RE.match(val):
            day = day_row_filled[col_idx] if col_idx < len(day_row_filled) else ""
            markets[val] = {
                "start_col":       col_idx,
                "final_alloc_col": col_idx + 2,
                "sold_col":        col_idx + 3,
                "day":             day,
            }
    return markets


def get_data_start_row(all_data: list = None):
    """0-based row index where product rows begin (right under the sub-header
    row that has Auto Allocated / Adjustment / Final Allocated / ...)."""
    if all_data is None:
        all_data = get_all_sheet_data()
    market_row_idx = _find_market_header_row(all_data)
    if market_row_idx is None:
        return None
    return market_row_idx + 2  # +1 = sub-header row, +2 = first product row


def get_products(all_data: list = None) -> list:
    """Dynamically read the product names straight from the sheet's Product
    column, starting right after the header rows and stopping at the first
    blank row. No more hardcoded PRODUCTS list."""
    if all_data is None:
        all_data = get_all_sheet_data()
    start_row = get_data_start_row(all_data)
    if start_row is None:
        return []

    products = []
    row_idx = start_row
    while row_idx < len(all_data):
        row = all_data[row_idx]
        name = row[PRODUCT_COL].strip() if PRODUCT_COL < len(row) else ""
        if not name:
            break
        products.append(name)
        row_idx += 1
    return products


def get_days_in_order(market_map: dict = None) -> list:
    """Distinct market days in left-to-right sheet order (e.g. Monday, Wednesday, Friday)."""
    if market_map is None:
        market_map = build_market_map()
    ordered = sorted(market_map.values(), key=lambda m: m["start_col"])
    days = []
    for m in ordered:
        if m["day"] and m["day"] not in days:
            days.append(m["day"])
    return days


def get_markets_by_day(day: str, market_map: dict = None) -> list:
    if market_map is None:
        market_map = build_market_map()
    return [{"id": mid, "day": info["day"]} for mid, info in market_map.items()
            if info["day"].lower() == day.lower()]


def get_next_day_markets(market_id: str, market_map: dict = None) -> list:
    """Market IDs belonging to whichever market day comes right after market_id's day."""
    if market_map is None:
        market_map = build_market_map()
    days_order = get_days_in_order(market_map)
    day = market_map.get(market_id, {}).get("day", "")
    if day not in days_order:
        return []
    idx = days_order.index(day)
    if idx + 1 >= len(days_order):
        return []
    next_day = days_order[idx + 1]
    return [mid for mid, info in market_map.items() if info["day"] == next_day]


# ── Read: Calculation sheet values ──────────────────────────────────────────

def get_market_allocations(market_id: str, all_data: list = None,
                            market_map: dict = None, products: list = None) -> dict:
    if all_data is None:
        all_data = get_all_sheet_data()
    if market_map is None:
        market_map = build_market_map(all_data)
    if products is None:
        products = get_products(all_data)

    info = market_map.get(market_id)
    if not info:
        return {}
    col = info["final_alloc_col"]
    start_row = get_data_start_row(all_data)

    result = {}
    for i, product in enumerate(products):
        row_idx = start_row + i
        row = all_data[row_idx] if row_idx < len(all_data) else []
        val = row[col] if col < len(row) else ""
        result[product] = _safe_float(val) or 0.0
    return result


def get_sold_data(market_id: str, all_data: list = None,
                   market_map: dict = None, products: list = None) -> dict:
    if all_data is None:
        all_data = get_all_sheet_data()
    if market_map is None:
        market_map = build_market_map(all_data)
    if products is None:
        products = get_products(all_data)

    info = market_map.get(market_id)
    if not info:
        return {}
    col = info["sold_col"]
    start_row = get_data_start_row(all_data)

    result = {}
    for i, product in enumerate(products):
        row_idx = start_row + i
        row = all_data[row_idx] if row_idx < len(all_data) else []
        val = row[col] if col < len(row) else ""
        result[product] = _safe_float(val)
    return result


def build_market_status_map(all_data: list = None) -> dict:
    if all_data is None:
        all_data = get_all_sheet_data()
    market_map = build_market_map(all_data)
    products   = get_products(all_data)
    num_products = len(products)

    status_map = {}
    for market_id in market_map:
        sold = get_sold_data(market_id, all_data, market_map, products)
        filled = sum(1 for v in sold.values() if v is not None)
        if num_products and filled == num_products:
            status_map[market_id] = "complete"
        elif filled > 0:
            status_map[market_id] = "in_progress"
        else:
            status_map[market_id] = "not_started"
    return status_map


def count_filled(market_id: str, all_data: list = None) -> int:
    if all_data is None:
        all_data = get_all_sheet_data()
    sold = get_sold_data(market_id, all_data)
    return sum(1 for v in sold.values() if v is not None)


def compute_week_totals(all_data: list = None) -> dict:
    if all_data is None:
        all_data = get_all_sheet_data()
    market_map = build_market_map(all_data)
    products   = get_products(all_data)

    total_alloc = total_sold = 0.0
    for market_id in market_map:
        allocs    = get_market_allocations(market_id, all_data, market_map, products)
        sold_data = get_sold_data(market_id, all_data, market_map, products)
        total_alloc += sum(allocs.values())
        total_sold  += sum(v for v in sold_data.values() if v is not None)
    return {"total_alloc": total_alloc, "total_sold": total_sold}


def all_markets_complete(all_data: list = None) -> bool:
    if all_data is None:
        all_data = get_all_sheet_data(force=True)
    market_map = build_market_map(all_data)
    products   = get_products(all_data)
    for market_id in market_map:
        sold = get_sold_data(market_id, all_data, market_map, products)
        if any(v is None for v in sold.values()):
            return False
    return True


def get_reallocation_view(market_id: str, all_data: list = None) -> list:
    if all_data is None:
        all_data = get_all_sheet_data(force=True)

    market_map = build_market_map(all_data)
    products   = get_products(all_data)

    next_day_markets = get_next_day_markets(market_id, market_map)

    allocs    = get_market_allocations(market_id, all_data, market_map, products)
    sold_data = get_sold_data(market_id, all_data, market_map, products)

    next_day_allocs = {}
    for mid in next_day_markets:
        next_day_allocs[mid] = get_market_allocations(mid, all_data, market_map, products)

    result = []
    for product in products:
        allocated = allocs.get(product, 0.0)
        sold      = sold_data.get(product) or 0.0
        remain    = max(0.0, allocated - sold)

        splits = {}
        for mid in next_day_markets:
            val = next_day_allocs[mid].get(product, 0.0)
            if val > 0:
                splits[mid] = val

        result.append({
            "product":         product,
            "emoji":           get_product_emoji(product),
            "allocated":       allocated,
            "sold":            sold,
            "remain":          remain,
            "next_day_allocs": splits,
        })

    return result


# ── Read: Details sheet ───────────────────────────────────────────────────

def _get_details_rows(force: bool = False) -> dict:
    now = time.time()
    if (not force
            and _WORKER_CACHE["data"] is not None
            and (now - _WORKER_CACHE["ts"]) < WORKER_CACHE_TTL):
        return _WORKER_CACHE["data"]

    ws   = _details_sheet()
    rows = ws.get_all_values()

    managers = []
    workers  = []

    for row in rows[DETAILS_WORKER_START_ROW:]:
        if not any(str(v).strip() for v in row):
            continue

        def _cell(col):
            val = str(row[col]).strip() if col < len(row) else ""
            return val.replace(".0", "").strip()

        m_phone = _cell(DETAILS_COL_M_PHONE)
        m_name  = _cell(DETAILS_COL_M_NAME)
        if m_phone and m_name and m_phone not in ("", "-"):
            managers.append({"name": m_name, "phone": m_phone})

        w_phone = _cell(DETAILS_COL_W_PHONE)
        w_name  = _cell(DETAILS_COL_W_NAME)
        if w_phone and w_name and w_phone not in ("", "-"):
            workers.append({
                "name":      w_name,
                "phone":     w_phone,
                "Monday":    _cell(DETAILS_COL_W_MONDAY)    or "-",
                "Wednesday": _cell(DETAILS_COL_W_WEDNESDAY) or "-",
                "Friday":    _cell(DETAILS_COL_W_FRIDAY)    or "-",
            })

    data = {"managers": managers, "workers": workers}
    _WORKER_CACHE["data"] = data
    _WORKER_CACHE["ts"]   = now
    return data


def get_manager_numbers() -> set:
    try:
        details = _get_details_rows()
        return {m["phone"] for m in details["managers"]}
    except Exception as exc:
        print(f"get_manager_numbers error: {exc}")
        return set()


def get_worker_by_phone(phone: str) -> dict | None:
    phone_clean = str(phone).strip().replace(".0", "").replace("+", "")
    if len(phone_clean) > 10:
        phone_clean = phone_clean[-10:]
    try:
        for w in _get_details_rows()["workers"]:
            sheet_phone = str(w["phone"]).strip().replace(".0", "").replace("+", "")
            if len(sheet_phone) > 10:
                sheet_phone = sheet_phone[-10:]
            if sheet_phone == phone_clean:
                return w
    except Exception as exc:
        print(f"get_worker_by_phone error: {exc}")
    return None


def get_workers_by_day(day: str) -> list:
    result = []
    try:
        for w in _get_details_rows()["workers"]:
            market = w.get(day, "-")
            if market and market not in ("", "-"):
                result.append({
                    "phone":  w["phone"],
                    "name":   w["name"],
                    "market": market,
                })
    except Exception as exc:
        print(f"get_workers_by_day error: {exc}")
    return result


# ── Write ─────────────────────────────────────────────────────────────────

def write_sold_box(market_id: str, product_index: int, sold_value: float):
    ws = _calc_sheet()
    all_data = get_all_sheet_data()

    market_map = build_market_map(all_data)
    info = market_map.get(market_id)
    if not info:
        raise ValueError(f"Unknown market_id: {market_id}")

    start_row = get_data_start_row(all_data)
    row_1 = start_row + product_index + 1          # +1 to convert 0-based → 1-based for gspread
    col_1 = info["sold_col"] + 1                    # +1 to convert 0-based → 1-based for gspread

    ws.update_cell(row_1, col_1, sold_value)
    invalidate_cache()