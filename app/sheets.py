'sheets.py'
import time
import json
import os
import time
import datetime
import gspread
from google.oauth2.service_account import Credentials
from config import SHEET_ID, CREDS_FILE

CACHE_FILE = "sheet_data_cache.json"
CACHE_TTL = 300


# ── Scopes ────────────────────────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# ── Market → Day mapping ──────────────────────────────────────────────────
MARKETS = {
    "M1":  "Monday",    "M2":  "Monday",    "M3":  "Monday",    "M4":  "Monday",
    "M5":  "Wednesday", "M6":  "Wednesday", "M7":  "Wednesday", "M8":  "Wednesday",
    "M9":  "Friday",    "M10": "Friday",    "M11": "Friday",    "M12": "Friday",
}

PRODUCTS = [
    "Apple", "Banana", "Tomato", "Potato", "Onion",
    "Beans", "Chilli", "Brinjal", "Carrot", "Pine Apple",
]

PRODUCT_EMOJIS = ["🍎","🍌","🍅","🥔","🧅","🫘","🌶️","🍆","🥕","🍍"]

CALC_SHEET_NAME    = "Calculation"
HISTORY_SHEET_NAME = "History"
DETAILS_SHEET_NAME = "Details"

PREV_DATA_START_ROW = 6    # 0-indexed
CURR_DATA_START_ROW = 28   # 0-indexed
NUM_PRODUCTS        = 10
NUM_MARKETS         = 12

MARKET_COL = {
    "M1": 3,  "M2": 6,  "M3": 9,  "M4": 12,
    "M5": 15, "M6": 18, "M7": 21, "M8": 24,
    "M9": 27, "M10": 30, "M11": 33, "M12": 36,
}

# Total columns (0-indexed): AN=39, AO=40, AP=41, AQ=42, AR=43
TOTAL_ALLOC_COL  = 39   # AN — manager types here
TOTAL_SALES_COL  = 40   # AO
TOTAL_UNSOLD_COL = 41   # AP
TOTAL_SALESPCT   = 42   # AQ
TOTAL_UNSOLDPCT  = 43   # AR

# Details tab — Worker section column positions (0-indexed)
# Row 5  = Header, Row 6+ = data
# Worker section: cols 6-11
# Manager section: cols 1-3
DETAILS_WORKER_START_ROW = 5    # 0-indexed (row 6 in sheet)
DETAILS_COL_W_NO         = 6    # Worker No
DETAILS_COL_W_NAME       = 7    # Worker Name
DETAILS_COL_W_PHONE      = 8    # Worker Phone
DETAILS_COL_W_MONDAY     = 9    # Monday market
DETAILS_COL_W_WEDNESDAY  = 10   # Wednesday market
DETAILS_COL_W_FRIDAY     = 11   # Friday market

DETAILS_COL_M_NO         = 1    # Manager No
DETAILS_COL_M_NAME       = 2    # Manager Name
DETAILS_COL_M_PHONE      = 3    # Manager Phone

# ── Caches ────────────────────────────────────────────────────────────────
_CACHE: dict        = {"data": None, "ts": 0.0}
_WORKER_CACHE: dict = {"data": None, "ts": 0.0}
CACHE_TTL        = 30   # seconds — calculation sheet
WORKER_CACHE_TTL = 60   # seconds — worker assignments (changes rarely)


# ══════════════════════════════════════════════════════════════════════════
# CONNECTION
# ══════════════════════════════════════════════════════════════════════════

def _client():
    creds = Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPES)
    return gspread.authorize(creds)

def _spreadsheet():
    return _client().open_by_key(SHEET_ID)

def _calc_sheet():
    return _spreadsheet().worksheet(CALC_SHEET_NAME)

def _details_sheet():
    return _spreadsheet().worksheet(DETAILS_SHEET_NAME)

def _load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r') as f:
            try: return json.load(f)
            except: return {"data": None, "ts": 0}
    return {"data": None, "ts": 0}

def get_all_sheet_data(force: bool = False) -> list:
    cache = _load_cache()
    if not force and cache["data"] is not None and (time.time() - cache["ts"]) < CACHE_TTL:
        return cache["data"]
    
    ws = _calc_sheet()
    data = ws.get_all_values()
    with open(CACHE_FILE, 'w') as f:
        json.dump({"data": data, "ts": time.time()}, f)
    return data

def invalidate_cache():
    if os.path.exists(CACHE_FILE):
        os.remove(CACHE_FILE)

# ══════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════

def _safe_float(val) -> float | None:
    """Convert cell value → float. Returns None if blank/invalid."""
    if val is None or str(val).strip() == "":
        return None
    try:
        return float(str(val).replace(",", "").replace("%", "").strip())
    except ValueError:
        return None


# ══════════════════════════════════════════════════════════════════════════
# READ: CALCULATION SHEET
# ══════════════════════════════════════════════════════════════════════════

def get_all_markets() -> list:
    return [{"id": m, "day": d} for m, d in MARKETS.items()]


def get_markets_by_day(day: str) -> list:
    return [{"id": m, "day": d} for m, d in MARKETS.items()
            if d.lower() == day.lower()]


def get_market_allocations(market_id: str, all_data: list = None) -> dict:
    if all_data is None:
        all_data = get_all_sheet_data()
    col    = MARKET_COL[market_id]
    result = {}
    for i, product in enumerate(PRODUCTS):
        row_idx = CURR_DATA_START_ROW + i
        row     = all_data[row_idx] if row_idx < len(all_data) else []
        val     = row[col] if col < len(row) else ""
        result[product] = _safe_float(val) or 0.0
    return result


def get_sold_data(market_id: str, all_data: list = None) -> dict:
    if all_data is None:
        all_data = get_all_sheet_data()
    sold_col = MARKET_COL[market_id] + 1
    result   = {}
    for i, product in enumerate(PRODUCTS):
        row_idx = CURR_DATA_START_ROW + i
        row     = all_data[row_idx] if row_idx < len(all_data) else []
        val     = row[sold_col] if sold_col < len(row) else ""
        result[product] = _safe_float(val)
    return result


def build_market_status_map(all_data: list = None) -> dict:
    if all_data is None:
        all_data = get_all_sheet_data()
    status_map = {}
    for market_id in MARKETS:
        sold   = get_sold_data(market_id, all_data)
        filled = sum(1 for v in sold.values() if v is not None)
        if filled == NUM_PRODUCTS:
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
    total_alloc = total_sold = 0.0
    for market_id in MARKETS:
        allocs    = get_market_allocations(market_id, all_data)
        sold_data = get_sold_data(market_id, all_data)
        total_alloc += sum(allocs.values())
        total_sold  += sum(v for v in sold_data.values() if v is not None)
    return {"total_alloc": total_alloc, "total_sold": total_sold}


def all_markets_complete(all_data: list = None) -> bool:
    if all_data is None:
        all_data = get_all_sheet_data(force=True)
    for market_id in MARKETS:
        sold = get_sold_data(market_id, all_data)
        if any(v is None for v in sold.values()):
            return False
    return True


def is_day_complete(day: str, all_data: list = None) -> bool:
    """
    Check if ALL markets for a given day have 10/10 products filled.
    Monday   → M1 M2 M3 M4
    Wednesday→ M5 M6 M7 M8
    Friday   → M9 M10 M11 M12
    """
    if all_data is None:
        all_data = get_all_sheet_data()
    day_markets = [mid for mid, d in MARKETS.items() if d == day]
    for mid in day_markets:
        sold = get_sold_data(mid, all_data)
        if any(v is None for v in sold.values()):
            return False
    return True


def get_reallocation_view(market_id: str, all_data: list = None) -> list:
    """
    For a worker's completed market, show:
      - Each product: allocated, sold, remaining
      - Next day markets: what the sheet has allocated (includes reallocation)

    Returns list of dicts per product:
    [
      {
        "product":   "Apple",
        "emoji":     "🍎",
        "allocated": 156.0,
        "sold":      134.0,
        "remain":    22.0,
        "next_day_allocs": {"M5": 95.0, "M6": 88.0, "M7": 91.0, "M8": 85.0}
      },
      ...
    ]

    next_day_allocs = sheet formula result values (already includes
    Monday remaining redistributed to Wednesday markets by sheet formula).
    Worker sees: "My 22 Apple boxes are going to M5(95), M7(91)..." etc.
    """
    if all_data is None:
        all_data = get_all_sheet_data(force=True)  # force fresh — Monday just completed

    day = MARKETS.get(market_id, "")
    next_day_markets = {
        "Monday":    ["M5", "M6", "M7", "M8"],
        "Wednesday": ["M9", "M10", "M11", "M12"],
        "Friday":    [],
    }.get(day, [])

    allocs    = get_market_allocations(market_id, all_data)
    sold_data = get_sold_data(market_id, all_data)

    # Read next day allocations from sheet (formula result — includes reallocation)
    next_day_allocs = {}
    for mid in next_day_markets:
        next_day_allocs[mid] = get_market_allocations(mid, all_data)

    result = []
    for i, product in enumerate(PRODUCTS):
        allocated = allocs.get(product, 0.0)
        sold      = sold_data.get(product) or 0.0
        remain    = max(0.0, allocated - sold)

        # Next day split values from sheet for this product
        splits = {}
        for mid in next_day_markets:
            val = next_day_allocs[mid].get(product, 0.0)
            if val > 0:
                splits[mid] = val

        result.append({
            "product":        product,
            "emoji":          PRODUCT_EMOJIS[i],
            "allocated":      allocated,
            "sold":           sold,
            "remain":         remain,
            "next_day_allocs": splits,
        })

    return result


# ══════════════════════════════════════════════════════════════════════════
# READ: DETAILS SHEET — Worker & Manager assignments
# ══════════════════════════════════════════════════════════════════════════

def _get_details_rows(force: bool = False) -> dict:
    """
    Read Details tab once. Cached for WORKER_CACHE_TTL seconds.
    Returns:
    {
      "managers": [{"name": "Priya", "phone": "919876543210"}, ...],
      "workers":  [
        {"name": "Ravi", "phone": "919876543211",
         "Monday": "M1", "Wednesday": "M5", "Friday": "M9"},
        ...
      ]
    }
    """
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

        # Manager section (cols 1-3)
        m_phone = _cell(DETAILS_COL_M_PHONE)
        m_name  = _cell(DETAILS_COL_M_NAME)
        if m_phone and m_name and m_phone not in ("", "-"):
            managers.append({"name": m_name, "phone": m_phone})

        # Worker section (cols 6-11)
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
    """
    Return set of manager phone numbers from Details tab.
    Used by shared.py instead of hardcoded MANAGER_NUMBERS.
    """
    try:
        details = _get_details_rows()
        return {m["phone"] for m in details["managers"]}
    except Exception as exc:
        print(f"get_manager_numbers error: {exc}")
        return set()


def get_worker_by_phone(phone: str) -> dict | None:
    """
    Get worker info by phone number.
    Handles country codes (+91, 91) and extracts the last 10 digits to match with sheet.
    """
    # Clean string: remove decimals, spaces, or plus signs
    phone_clean = str(phone).strip().replace(".0", "").replace("+", "")
    
    # Extract last 10 digits if the number is longer (e.g., 9198439xxxxx -> 98439xxxxx)
    if len(phone_clean) > 10:
        phone_clean = phone_clean[-10:]
        
    try:
        for w in _get_details_rows()["workers"]:
            # Clean sheet number also just in case
            sheet_phone = str(w["phone"]).strip().replace(".0", "").replace("+", "")
            if len(sheet_phone) > 10:
                sheet_phone = sheet_phone[-10:]
                
            if sheet_phone == phone_clean:
                return w
    except Exception as exc:
        print(f"get_worker_by_phone error: {exc}")
    return None


def get_assigned_market(phone: str, day: str) -> str | None:
    """
    Get market assigned to a worker on a specific day.
    Returns "M1" etc. or None if not assigned.
    """
    worker = get_worker_by_phone(phone)
    if not worker:
        return None
    market = worker.get(day, "-")
    return market if market not in ("", "-") else None


def get_worker_by_market(market_id: str) -> dict | None:
    """
    Get the worker assigned to a specific market (any day).
    Returns worker dict or None.
    """
    try:
        for w in _get_details_rows()["workers"]:
            for day in ("Monday", "Wednesday", "Friday"):
                if w.get(day) == market_id:
                    return w
    except Exception as exc:
        print(f"get_worker_by_market error: {exc}")
    return None


def get_workers_by_day(day: str) -> list:
    """
    Get all workers assigned on a specific day.
    Returns [{"phone", "name", "market"}, ...]
    """
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


def get_all_markets_for_worker(phone: str) -> dict:
    """
    Get all markets assigned to a worker across all days.
    Returns {"Monday": "M1", "Wednesday": "M6", "Friday": "-"}
    """
    worker = get_worker_by_phone(phone)
    if not worker:
        return {"Monday": "-", "Wednesday": "-", "Friday": "-"}
    return {
        "Monday":    worker.get("Monday",    "-"),
        "Wednesday": worker.get("Wednesday", "-"),
        "Friday":    worker.get("Friday",    "-"),
    }


def invalidate_worker_cache():
    """Call when manager updates worker assignments in sheet."""
    _WORKER_CACHE["data"] = None
    _WORKER_CACHE["ts"]   = 0.0


# ══════════════════════════════════════════════════════════════════════════
# WRITE: sold boxes — immediate, one cell at a time
# ══════════════════════════════════════════════════════════════════════════

def write_sold_box(market_id: str, product_index: int, sold_value: float):
    """
    Write sold boxes for one product in one market.
    Invalidates cache so next read gets fresh data.
    """
    ws    = _calc_sheet()
    row_1 = CURR_DATA_START_ROW + product_index + 1
    col_1 = MARKET_COL[market_id] + 1 + 1
    ws.update_cell(row_1, col_1, sold_value)
    invalidate_cache()


# ══════════════════════════════════════════════════════════════════════════
# SHEET ROTATION
# ══════════════════════════════════════════════════════════════════════════

def rotate_sheets():
    """
    End-of-week rotation:
      Step 1: Archive Current Week → History tab
      Step 2: Copy Current Week    → Previous Week table
      Step 3: Reset Current Week
    """
    spreadsheet = _spreadsheet()
    ws          = spreadsheet.worksheet(CALC_SHEET_NAME)
    all_values  = ws.get_all_values()

    _archive_to_history(spreadsheet, all_values)
    _copy_current_to_previous(ws, all_values)
    _reset_current_week(ws)
    invalidate_cache()


def _archive_to_history(spreadsheet, all_values):
    try:
        hist_ws = spreadsheet.worksheet(HISTORY_SHEET_NAME)
    except gspread.WorksheetNotFound:
        hist_ws = spreadsheet.add_worksheet(
            HISTORY_SHEET_NAME, rows=1000, cols=50
        )

    today      = datetime.date.today()
    week_end   = today - datetime.timedelta(days=today.weekday() + 1)
    week_start = week_end - datetime.timedelta(days=6)
    month_name = week_start.strftime("%B %Y")
    date_range = (f"{week_start.strftime('%a %d %b')}"
                  f" – {week_end.strftime('%a %d %b %Y')}")

    existing_data = hist_ws.get_all_values()
    week_num      = sum(1 for row in existing_data
                        if row and "Week" in str(row[0])) + 1
    week_header   = f"Week {week_num}  |  {month_name}  |  {date_range}"

    col_header = ["Product"]
    for mid in MARKETS:
        col_header += [f"{mid} Allocated", f"{mid} Sold", f"{mid} Market%"]
    col_header += ["Total Allocated", "Total Sales",
                   "Total Unsold", "Total Sales%", "Total Unsales%"]

    data_rows = []
    for i, product in enumerate(PRODUCTS):
        curr_row = all_values[CURR_DATA_START_ROW + i]
        row_data = [product]
        for base_col in MARKET_COL.values():
            for offset in range(3):
                try:
                    raw = curr_row[base_col + offset]
                    val = _safe_float(raw)
                    row_data.append(val if val is not None else "")
                except IndexError:
                    row_data.append("")
        for tc in [TOTAL_ALLOC_COL, TOTAL_SALES_COL,
                   TOTAL_UNSOLD_COL, TOTAL_SALESPCT, TOTAL_UNSOLDPCT]:
            try:
                raw = curr_row[tc]
                val = _safe_float(raw)
                row_data.append(val if val is not None else "")
            except IndexError:
                row_data.append("")
        data_rows.append(row_data)

    next_row = len(existing_data) + 1
    if existing_data and any(existing_data[-1]):
        next_row += 1

    rows_to_write = [[week_header], col_header] + data_rows + [[""]]
    hist_ws.update(f"A{next_row}", rows_to_write, value_input_option="USER_ENTERED")

    try:
        hist_ws.format(f"A{next_row}", {
            "textFormat":      {"bold": True, "fontSize": 11},
            "backgroundColor": {"red": 0.2, "green": 0.6, "blue": 0.2},
        })
    except Exception:
        pass


def _copy_current_to_previous(ws, all_values):
    updates = []
    for i in range(NUM_PRODUCTS):
        curr_row   = all_values[CURR_DATA_START_ROW + i]
        prev_row_1 = PREV_DATA_START_ROW + i + 1

        try:
            total_alloc = _safe_float(curr_row[TOTAL_ALLOC_COL]) or 0.0
        except IndexError:
            total_alloc = 0.0

        for base_col in MARKET_COL.values():
            alloc_val = _safe_float(
                curr_row[base_col] if base_col < len(curr_row) else "") or 0.0
            updates.append(gspread.Cell(prev_row_1, base_col + 1, alloc_val))

            sold_val = _safe_float(
                curr_row[base_col + 1] if (base_col + 1) < len(curr_row) else "") or 0.0
            updates.append(gspread.Cell(prev_row_1, base_col + 2, sold_val))

            market_pct = (sold_val / total_alloc) if total_alloc > 0 else 0.0
            updates.append(gspread.Cell(prev_row_1, base_col + 3, market_pct))

    if updates:
        ws.update_cells(updates, value_input_option="RAW")


def _reset_current_week(ws):
    clears = []
    for i in range(NUM_PRODUCTS):
        row_1 = CURR_DATA_START_ROW + i + 1
        for base_col in MARKET_COL.values():
            sold_col_1 = base_col + 2
            clears.append(gspread.Cell(row_1, sold_col_1, ""))
        clears.append(gspread.Cell(row_1, TOTAL_ALLOC_COL + 1, ""))
    if clears:
        ws.update_cells(clears, value_input_option="RAW")