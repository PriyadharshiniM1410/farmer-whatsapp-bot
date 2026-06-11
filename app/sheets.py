import time
import json
import os
import datetime
import gspread
from google.oauth2.service_account import Credentials
from config import SHEET_ID, CREDS_FILE

CACHE_FILE = "sheet_data_cache.json"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

MARKETS = {
    "M1":  "Monday",    "M2":  "Monday",    "M3":  "Monday",    "M4":  "Monday",
    "M5":  "Wednesday", "M6":  "Wednesday", "M7":  "Wednesday", "M8":  "Wednesday",
    "M9":  "Friday",    "M10": "Friday",    "M11": "Friday",    "M12": "Friday",
}

PRODUCTS = [
    "Apple", "Banana", "Tomato", "Potato", "Onion",
    "Beans", "Chilli", "Brinjal", "Carrot", "Pine Apple",
]

PRODUCT_EMOJIS = ["🍎", "🍌", "🍅", "🥔", "🧅", "🫘", "🌶️", "🍆", "🥕", "🍍"]

CALC_SHEET_NAME    = "Calculation"
HISTORY_SHEET_NAME = "History"
DETAILS_SHEET_NAME = "Details"

PREV_DATA_START_ROW = 6
CURR_DATA_START_ROW = 28
NUM_PRODUCTS        = 10
NUM_MARKETS         = 12

MARKET_COL = {
    "M1": 3,  "M2": 6,  "M3": 9,  "M4": 12,
    "M5": 15, "M6": 18, "M7": 21, "M8": 24,
    "M9": 27, "M10": 30, "M11": 33, "M12": 36,
}

TOTAL_ALLOC_COL  = 39
TOTAL_SALES_COL  = 40
TOTAL_UNSOLD_COL = 41
TOTAL_SALESPCT   = 42
TOTAL_UNSOLDPCT  = 43

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


# ── Read: Calculation sheet ───────────────────────────────────────────────

def get_markets_by_day(day: str) -> list:
    return [{"id": m, "day": d} for m, d in MARKETS.items()
            if d.lower() == day.lower()]


def get_market_allocations(market_id: str, all_data: list = None) -> dict:
    if all_data is None:
        all_data = get_all_sheet_data()
    col = MARKET_COL[market_id]
    result = {}
    for i, product in enumerate(PRODUCTS):
        row_idx = CURR_DATA_START_ROW + i
        row = all_data[row_idx] if row_idx < len(all_data) else []
        val = row[col] if col < len(row) else ""
        result[product] = _safe_float(val) or 0.0
    return result


def get_sold_data(market_id: str, all_data: list = None) -> dict:
    if all_data is None:
        all_data = get_all_sheet_data()
    sold_col = MARKET_COL[market_id] + 1
    result = {}
    for i, product in enumerate(PRODUCTS):
        row_idx = CURR_DATA_START_ROW + i
        row = all_data[row_idx] if row_idx < len(all_data) else []
        val = row[sold_col] if sold_col < len(row) else ""
        result[product] = _safe_float(val)
    return result


def build_market_status_map(all_data: list = None) -> dict:
    if all_data is None:
        all_data = get_all_sheet_data()
    status_map = {}
    for market_id in MARKETS:
        sold = get_sold_data(market_id, all_data)
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


def get_reallocation_view(market_id: str, all_data: list = None) -> list:
    if all_data is None:
        all_data = get_all_sheet_data(force=True)

    day = MARKETS.get(market_id, "")
    next_day_markets = {
        "Monday":    ["M5", "M6", "M7", "M8"],
        "Wednesday": ["M9", "M10", "M11", "M12"],
        "Friday":    [],
    }.get(day, [])

    allocs    = get_market_allocations(market_id, all_data)
    sold_data = get_sold_data(market_id, all_data)

    next_day_allocs = {}
    for mid in next_day_markets:
        next_day_allocs[mid] = get_market_allocations(mid, all_data)

    result = []
    for i, product in enumerate(PRODUCTS):
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
            "emoji":           PRODUCT_EMOJIS[i],
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
    ws    = _calc_sheet()
    row_1 = CURR_DATA_START_ROW + product_index + 1
    col_1 = MARKET_COL[market_id] + 1 + 1
    ws.update_cell(row_1, col_1, sold_value)
    invalidate_cache()


# ── Sheet rotation ────────────────────────────────────────────────────────

def rotate_sheets():
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
        hist_ws = spreadsheet.add_worksheet(HISTORY_SHEET_NAME, rows=1000, cols=50)

    today      = datetime.date.today()
    week_end   = today - datetime.timedelta(days=today.weekday() + 1)
    week_start = week_end - datetime.timedelta(days=6)
    month_name = week_start.strftime("%B %Y")
    date_range = (f"{week_start.strftime('%a %d %b')}"
                  f" – {week_end.strftime('%a %d %b %Y')}")

    existing_data = hist_ws.get_all_values()
    week_num      = sum(1 for row in existing_data if row and "Week" in str(row[0])) + 1
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
            clears.append(gspread.Cell(row_1, base_col + 2, ""))
        clears.append(gspread.Cell(row_1, TOTAL_ALLOC_COL + 1, ""))
    if clears:
        ws.update_cells(clears, value_input_option="RAW")
