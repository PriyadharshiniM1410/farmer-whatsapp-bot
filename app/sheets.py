
import time
import datetime
import gspread
from google.oauth2.service_account import Credentials
from config import SHEET_ID, CREDS_FILE

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

CALC_SHEET_NAME    = "Calculation"
HISTORY_SHEET_NAME = "History"

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

# ── In-process cache (30 second TTL) ─────────────────────────────────────
_CACHE: dict = {"data": None, "ts": 0.0}
CACHE_TTL    = 30  # seconds


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


# ══════════════════════════════════════════════════════════════════════════
# CORE: SINGLE-CALL FULL READ  ← solves 429 quota errors
# ══════════════════════════════════════════════════════════════════════════

def get_all_sheet_data(force: bool = False) -> list:
    """
    Fetch ALL rows from Calculation sheet in ONE API call.
    Cached for CACHE_TTL seconds.

    Before fix:  Market Status  = 24 API calls  → 429 error
    After fix:   Market Status  =  1 API call   → no error
    """
    now = time.time()
    if not force and _CACHE["data"] is not None and (now - _CACHE["ts"]) < CACHE_TTL:
        return _CACHE["data"]
    ws             = _calc_sheet()
    data           = ws.get_all_values()
    _CACHE["data"] = data
    _CACHE["ts"]   = now
    return data


def invalidate_cache():
    """Call after every write so the next read fetches fresh data."""
    _CACHE["data"] = None
    _CACHE["ts"]   = 0.0


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
# READ FUNCTIONS (all accept pre-fetched all_data → zero extra API calls)
# ══════════════════════════════════════════════════════════════════════════

def get_all_markets() -> list:
    return [{"id": m, "day": d} for m, d in MARKETS.items()]


def get_markets_by_day(day: str) -> list:
    return [{"id": m, "day": d} for m, d in MARKETS.items()
            if d.lower() == day.lower()]


def get_market_allocations(market_id: str, all_data: list = None) -> dict:
    """
    Return {product: allocated_boxes} for a market from Current Week table.
    Pass all_data to avoid an extra API call.
    """
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
    """
    Return {product: sold_boxes | None} for a market.
    None = not yet entered.
    """
    if all_data is None:
        all_data = get_all_sheet_data()
    sold_col = MARKET_COL[market_id] + 1   # sold = allocated + 1
    result   = {}
    for i, product in enumerate(PRODUCTS):
        row_idx = CURR_DATA_START_ROW + i
        row     = all_data[row_idx] if row_idx < len(all_data) else []
        val     = row[sold_col] if sold_col < len(row) else ""
        result[product] = _safe_float(val)  # None if blank
    return result


def build_market_status_map(all_data: list = None) -> dict:
    """
    Return {market_id: "complete" | "in_progress" | "not_started"}
    ONE sheet read for all 12 markets.
    """
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
    """How many products have sold data for this market."""
    if all_data is None:
        all_data = get_all_sheet_data()
    sold = get_sold_data(market_id, all_data)
    return sum(1 for v in sold.values() if v is not None)


def compute_week_totals(all_data: list = None) -> dict:
    """Total allocated + sold across all 12 markets. ONE sheet read."""
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
    """True when every sold cell in Current Week is filled."""
    if all_data is None:
        all_data = get_all_sheet_data(force=True)  # force fresh for close-week
    for market_id in MARKETS:
        sold = get_sold_data(market_id, all_data)
        if any(v is None for v in sold.values()):
            return False
    return True


# ══════════════════════════════════════════════════════════════════════════
# WRITE: sold boxes — immediate, one cell at a time
# ══════════════════════════════════════════════════════════════════════════

def write_sold_box(market_id: str, product_index: int, sold_value: float):
    """
    Write sold boxes for one product in one market.
    Row  = CURR_DATA_START_ROW + product_index  (0-indexed → +1 for gspread)
    Col  = MARKET_COL[market_id] + 1 (sold offset) + 1 (gspread 1-indexed)
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
      Step 1: Archive Current Week → History tab (stacked, date-headed)
      Step 2: Copy Current Week    → Previous Week table (values only)
      Step 3: Reset Current Week   (clear sold + total allocated)
    """
    spreadsheet = _spreadsheet()
    ws          = spreadsheet.worksheet(CALC_SHEET_NAME)
    all_values  = ws.get_all_values()

    _archive_to_history(spreadsheet, all_values)
    _copy_current_to_previous(ws, all_values)
    _reset_current_week(ws)
    invalidate_cache()


# ── Step 1: Archive ────────────────────────────────────────────────────────

def _archive_to_history(spreadsheet, all_values):
    """
    Archive Current Week data into History tab (single tab, stacked).
    Format per week block:
      Row A : ══ Week N | Month YYYY | Mon DD Mon – Sun DD Mon YYYY ══
      Row B : Product | M1 Allocated | M1 Sold | M1 Market% | M2 ... | Totals
      Rows  : 10 product data rows
      Row   : blank separator
    """
    try:
        hist_ws = spreadsheet.worksheet(HISTORY_SHEET_NAME)
    except gspread.WorksheetNotFound:
        hist_ws = spreadsheet.add_worksheet(
            HISTORY_SHEET_NAME, rows=1000, cols=50
        )

    # ── Week date header ──────────────────────────────────────────
    today      = datetime.date.today()
    week_end   = today - datetime.timedelta(days=today.weekday() + 1)
    week_start = week_end - datetime.timedelta(days=6)
    month_name = week_start.strftime("%B %Y")
    date_range = (f"{week_start.strftime('%a %d %b')}"
                  f" – {week_end.strftime('%a %d %b %Y')}")

    existing_data = hist_ws.get_all_values()
    week_num      = sum(1 for row in existing_data
                        if row and "Week" in str(row[0])) + 1
    week_header   = f"══ Week {week_num}  |  {month_name}  |  {date_range}  ══"

    # ── Column header row ─────────────────────────────────────────
    col_header = ["Product"]
    for mid in MARKETS:
        col_header += [f"{mid} Allocated", f"{mid} Sold", f"{mid} Market%"]
    col_header += ["Total Allocated", "Total Sales",
                   "Total Unsold", "Total Sales%", "Total Unsales%"]

    # ── Product data rows ─────────────────────────────────────────
    data_rows = []
    for i, product in enumerate(PRODUCTS):
        curr_row = all_values[CURR_DATA_START_ROW + i]
        row_data = [product]

        for base_col in MARKET_COL.values():
            for offset in range(3):  # allocated, sold, market%
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

    # ── Append to History tab ────────────────────────────────────
    next_row = len(existing_data) + 1
    if existing_data and any(existing_data[-1]):
        next_row += 1   # blank separator between weeks

    rows_to_write = [[week_header], col_header] + data_rows + [[""]]
    hist_ws.update(
        f"A{next_row}",
        rows_to_write,
        value_input_option="USER_ENTERED"
    )

    # Bold + colour the week header row
    try:
        hist_ws.format(f"A{next_row}", {
            "textFormat":      {"bold": True, "fontSize": 11},
            "backgroundColor": {"red": 0.2, "green": 0.6, "blue": 0.2},
        })
    except Exception:
        pass


# ── Step 2: Copy Current → Previous ───────────────────────────────────────

def _copy_current_to_previous(ws, all_values):
    """
    Copy Current Week → Previous Week table.
    Copies: Allocated, Sold per market.
    Recalculates Market% = Sold / Total Allocated (stores as decimal).
    """
    updates = []
    for i in range(NUM_PRODUCTS):
        curr_row   = all_values[CURR_DATA_START_ROW + i]
        prev_row_1 = PREV_DATA_START_ROW + i + 1   # 1-indexed

        # Total Allocated from AN column (0-indexed 39)
        try:
            total_alloc = _safe_float(curr_row[TOTAL_ALLOC_COL]) or 0.0
        except IndexError:
            total_alloc = 0.0

        for base_col in MARKET_COL.values():
            # Allocated
            alloc_val = _safe_float(
                curr_row[base_col] if base_col < len(curr_row) else ""
            ) or 0.0
            updates.append(gspread.Cell(prev_row_1, base_col + 1, alloc_val))

            # Sold
            sold_val = _safe_float(
                curr_row[base_col + 1] if (base_col + 1) < len(curr_row) else ""
            ) or 0.0
            updates.append(gspread.Cell(prev_row_1, base_col + 2, sold_val))

            # Market% = Sold / Total Allocated
            market_pct = (sold_val / total_alloc) if total_alloc > 0 else 0.0
            updates.append(gspread.Cell(prev_row_1, base_col + 3, market_pct))

    if updates:
        ws.update_cells(updates, value_input_option="RAW")


# ── Step 3: Reset Current Week ────────────────────────────────────────────

def _reset_current_week(ws):
    """
    Clear Current Week:
      - Sold Boxes cells (12 markets × 10 products)
      - Total Allocated column AN (col 40, 1-indexed)
    Formulas stay intact → sheet auto-recalculates when manager
    enters new Total Allocated next week.
    """
    clears = []
    for i in range(NUM_PRODUCTS):
        row_1 = CURR_DATA_START_ROW + i + 1   # 1-indexed

        for base_col in MARKET_COL.values():
            sold_col_1 = base_col + 2   # sold offset(+1) + 1-index(+1)
            clears.append(gspread.Cell(row_1, sold_col_1, ""))

        # Clear Total Allocated — AN = col 40 (1-indexed)
        clears.append(gspread.Cell(row_1, TOTAL_ALLOC_COL + 1, ""))

    if clears:
        ws.update_cells(clears, value_input_option="RAW")
