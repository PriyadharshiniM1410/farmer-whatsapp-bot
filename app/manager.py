from app.sheets import (
    get_all_sheet_data,
    get_market_allocations, get_markets_by_day, get_sold_data,
    write_sold_box, all_markets_complete, rotate_sheets,
    build_market_status_map, count_filled, compute_week_totals,
    MARKETS, PRODUCTS,
)
from app.whatsapp import send_text, send_buttons, send_list
from app.shared import (
    SESSIONS, is_manager, PRODUCT_EMOJIS, DAY_ICONS, DAYS_ORDER,
    get_manager_numbers_set,
)


# ── M-1: Manager Menu ──────────────────────────────────────────────────────

def send_manager_menu(sender: str):
    SESSIONS.pop(sender, None)
    send_buttons(sender,
        "👋 *Welcome, Manager!*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🌾 *AGRO MARKET — Operations*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "What would you like to do?",
        [
            {"id": "mgr_dashboard",       "title": "📊  Overview"},
            {"id": "mgr_product_summary", "title": "🔍  Product Summary"},
            {"id": "mgr_close_week",      "title": "🔄  Close Week"},
        ]
    )


# ── M-2: Combined Overview (Dashboard + Market Status + Sales Summary) ─────

def send_dashboard(sender: str):
    """ONE sheet read → shows everything: sales totals + day-wise status + market grid."""
    SESSIONS[sender] = {"mode": "idle"}
    try:
        all_data   = get_all_sheet_data()
        status_map = build_market_status_map(all_data)
        totals     = compute_week_totals(all_data)
    except Exception as exc:
        send_text(sender, f"❌ Error reading sheet: {exc}")
        return

    total_alloc = totals["total_alloc"]
    total_sold  = totals["total_sold"]
    unsold      = total_alloc - total_sold
    sell_thru   = (total_sold / total_alloc * 100) if total_alloc > 0 else 0

    completed = sum(1 for s in status_map.values() if s == "complete")
    in_prog   = sum(1 for s in status_map.values() if s == "in_progress")
    pending   = sum(1 for s in status_map.values() if s == "not_started")

    # ── Section 1: Sales totals ──
    lines = [
        "📊 *WEEKLY OVERVIEW*",
        "━━━━━━━━━━━━━━━━━━━━",
        f"📦 Allocated  : *{total_alloc:,.0f} boxes*",
        f"💰 Sold       : *{total_sold:,.0f} boxes*",
        f"🔴 Unsold     : *{unsold:,.0f} boxes*",
        f"📈 Sell-thru  : *{sell_thru:.1f}%*",
        "━━━━━━━━━━━━━━━━━━━━",
        f"✅ Complete   : *{completed}/12*",
        f"🟡 In Progress: *{in_prog}/12*",
        f"❌ Not Started: *{pending}/12*",
        "━━━━━━━━━━━━━━━━━━━━",
    ]

    # ── Section 2: Day-wise breakdown + market grid ──
    for day in DAYS_ORDER:
        icon     = DAY_ICONS[day]
        day_mkts = get_markets_by_day(day)

        # Day totals
        d_alloc = d_sold = 0.0
        for m in day_mkts:
            allocs    = get_market_allocations(m["id"], all_data)
            sold_data = get_sold_data(m["id"], all_data)
            d_alloc  += sum(allocs.values())
            d_sold   += sum(v for v in sold_data.values() if v is not None)
        d_pct = (d_sold / d_alloc * 100) if d_alloc > 0 else 0

        lines.append(f"{icon} *{day}*  {d_sold:,.0f}/{d_alloc:,.0f} ({d_pct:.0f}%)")

        # Market grid per day
        for m in day_mkts:
            mid    = m["id"]
            status = status_map.get(mid, "not_started")
            dot    = {"complete": "✅", "in_progress": "🟡", "not_started": "❌"}[status]
            filled = count_filled(mid, all_data)
            lines.append(f"  {dot} {mid}  ({filled}/{len(PRODUCTS)})")

    send_text(sender, "\n".join(lines))

    # ── Tap market to view/edit ──
    sections = []
    for day in DAYS_ORDER:
        icon     = DAY_ICONS[day]
        day_mkts = get_markets_by_day(day)
        rows = []
        for m in day_mkts:
            mid    = m["id"]
            status = status_map.get(mid, "not_started")
            dot    = {"complete": "✅", "in_progress": "🟡", "not_started": "❌"}[status]
            filled = count_filled(mid, all_data)
            rows.append({
                "id":          f"mgr_view_market_{mid}",
                "title":       f"{dot} {mid}",
                "description": f"{filled}/{len(PRODUCTS)} products — Tap to view/edit",
            })
        sections.append({"title": f"{icon} {day}", "rows": rows})

    send_list(sender, "Tap a market to view details:", "Select Market", sections)


# ── M-3: Market Review ─────────────────────────────────────────────────────

def send_market_review(sender: str, market_id: str):
    """ONE sheet read → full market data with edit option."""
    try:
        all_data  = get_all_sheet_data()
        allocs    = get_market_allocations(market_id, all_data)
        sold_data = get_sold_data(market_id, all_data)
    except Exception as exc:
        send_text(sender, f"❌ Error reading sheet: {exc}")
        return

    day         = MARKETS.get(market_id, "")
    icon        = DAY_ICONS.get(day, "📦")
    total_alloc = sum(allocs.values())
    total_sold  = sum(v for v in sold_data.values() if v is not None)
    sell_thru   = (total_sold / total_alloc * 100) if total_alloc > 0 else 0
    filled      = sum(1 for v in sold_data.values() if v is not None)

    lines = []
    for i, (prod, alloc) in enumerate(allocs.items()):
        sold   = sold_data.get(prod)
        status = f"{sold:.0f}" if sold is not None else "⏳ --"
        lines.append(f"{PRODUCT_EMOJIS[i]} *{prod:<12}* {alloc:.0f} → {status}")

    send_text(sender,
        f"{icon} *{market_id} | {day.upper()}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        + "\n".join(lines) +
        f"\n━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 Allocated : *{total_alloc:.0f}*\n"
        f"💰 Sold      : *{total_sold:.0f}*\n"
        f"📊 Sell-thru : *{sell_thru:.1f}%*\n"
        f"✏️  Entries  : *{filled}/{len(PRODUCTS)}*"
    )
    send_buttons(sender, f"━━━━━━━━━━━━━━━━━━━━\nActions for *{market_id}*:",
        [
            {"id": f"mgr_edit_market_{market_id}", "title": "✏️  Edit Market"},
            {"id": "mgr_dashboard",                "title": "◀  Back to Overview"},
            {"id": "menu",                         "title": "🏠  Main Menu"},
        ]
    )


# ── M-4: Market Status (backward compat → redirects to dashboard) ──────────

def send_market_status(sender: str):
    """Redirect to combined overview."""
    send_dashboard(sender)


# ── M-5: Sales Summary (backward compat → redirects to dashboard) ──────────

def send_sales_summary(sender: str):
    """Redirect to combined overview."""
    send_dashboard(sender)


# ── M-6: Product Summary ───────────────────────────────────────────────────

def launch_product_summary(sender: str):
    SESSIONS[sender] = {"mode": "mgr_product_select"}
    rows = [
        {
            "id":          f"mgr_product_{i}",
            "title":       f"{PRODUCT_EMOJIS[i]} {PRODUCTS[i]}",
            "description": "Tap to see allocated vs sold across all markets",
        }
        for i in range(len(PRODUCTS))
    ]
    send_list(sender,
        "🔍 *PRODUCT-WISE SUMMARY*\n━━━━━━━━━━━━━━━━━━━━\nSelect a product:",
        "Select Product", [{"title": "Products", "rows": rows}]
    )


def send_product_summary(sender: str, product_idx: int):
    """ONE sheet read for all markets of one product."""
    product = PRODUCTS[product_idx]
    emoji   = PRODUCT_EMOJIS[product_idx]

    try:
        all_data = get_all_sheet_data()
    except Exception as exc:
        send_text(sender, f"❌ Error reading sheet: {exc}")
        return

    total_alloc = total_sold = 0.0
    market_lines = []

    for mid in MARKETS:
        allocs    = get_market_allocations(mid, all_data)
        sold_data = get_sold_data(mid, all_data)
        alloc     = allocs.get(product, 0)
        sold      = sold_data.get(product)
        total_alloc += alloc
        if sold is not None:
            total_sold += sold
            pct = (sold / alloc * 100) if alloc > 0 else 0
            market_lines.append(f"  {mid}: {sold:.0f}/{alloc:.0f} ({pct:.0f}%)")
        else:
            market_lines.append(f"  {mid}: ⏳ Pending")

    unsold    = total_alloc - total_sold
    sell_thru = (total_sold / total_alloc * 100) if total_alloc > 0 else 0

    send_text(sender,
        f"{emoji} *{product} — Week Summary*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 Allocated : *{total_alloc:,.0f}*\n"
        f"💰 Sold      : *{total_sold:,.0f}*\n"
        f"🔴 Unsold    : *{unsold:,.0f}*\n"
        f"📊 Sell-thru : *{sell_thru:.1f}%*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        "*Market Breakdown:*\n" + "\n".join(market_lines)
    )
    send_buttons(sender, "━━━━━━━━━━━━━━━━━━━━",
        [
            {"id": "mgr_product_summary", "title": "◀  All Products"},
            {"id": "mgr_dashboard",       "title": "📊  Overview"},
            {"id": "menu",                "title": "🏠  Main Menu"},
        ]
    )


# ── M-7: Edit Market ───────────────────────────────────────────────────────

def start_market_edit(sender: str, market_id: str):
    try:
        all_data  = get_all_sheet_data()
        allocs    = get_market_allocations(market_id, all_data)
        sold_data = get_sold_data(market_id, all_data)
    except Exception as exc:
        send_text(sender, f"❌ Error reading sheet: {exc}")
        return

    SESSIONS[sender] = {
        "mode":           "mgr_market_edit_select",
        "edit_market_id": market_id,
        "allocations":    allocs,
        "sold_data":      sold_data,
    }
    rows = [
        {
            "id":          f"mgr_product_edit_{i}",
            "title":       f"{PRODUCT_EMOJIS[i]} {PRODUCTS[i]}",
            "description": f"Current: {sold_data.get(PRODUCTS[i]):.0f} boxes"
                           if sold_data.get(PRODUCTS[i]) is not None else "Current: Not entered",
        }
        for i in range(len(PRODUCTS))
    ]
    send_list(sender,
        f"✏️ *Edit Market {market_id}*\n━━━━━━━━━━━━━━━━━━━━\nSelect a product:",
        "Select Product", [{"title": f"Market {market_id}", "rows": rows}]
    )


def ask_edit_product(sender: str, session: dict, product_idx: int):
    product  = PRODUCTS[product_idx]
    alloc    = session["allocations"].get(product, 0)
    existing = session["sold_data"].get(product)
    emoji    = PRODUCT_EMOJIS[product_idx]
    mid      = session["edit_market_id"]

    session["edit_product_idx"] = product_idx
    session["mode"]             = "mgr_market_edit"
    SESSIONS[sender]            = session

    note = (f"\n📋 *Current: {existing:.0f} boxes*"
            if existing is not None else "\n📋 *No value yet*")

    send_text(sender,
        f"✏️ *Manager Edit — {emoji} {product}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Market    : *{mid}*\n"
        f"Allocated : *{alloc:.0f} boxes*"
        f"{note}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Enter new sold value _(0 – {alloc:.0f})_\n"
        f"Or type *back* to return."
    )


def handle_mgr_edit_input(sender: str, text: str, session: dict):
    if text.strip().lower() in ("back", "cancel"):
        send_market_review(sender, session.get("edit_market_id", ""))
        return

    idx     = session.get("edit_product_idx", 0)
    product = PRODUCTS[idx]
    alloc   = session["allocations"].get(product, 0)
    mid     = session["edit_market_id"]

    try:
        sold = float(text.strip())
    except ValueError:
        send_text(sender, f"⚠️ Invalid — enter a number (0–{alloc:.0f}).")
        return

    if not (0 <= sold <= alloc):
        send_text(sender, f"⚠️ Must be between *0* and *{alloc:.0f}*.")
        return

    fresh_sold = get_sold_data(mid)
    existing   = fresh_sold.get(product)
    session["sold_data"] = fresh_sold

    if existing is not None:
        session.update({"mode": "mgr_edit_overwrite",
                        "pending_sold": sold, "pending_idx": idx})
        SESSIONS[sender] = session
        send_buttons(sender,
            f"⚠️ *{product}* already has *{existing:.0f}* boxes.\n"
            f"Overwrite with *{sold:.0f}*?",
            [{"id": "mgr_edit_overwrite_yes", "title": "✅  Yes, Overwrite"},
             {"id": "mgr_edit_overwrite_no",  "title": "❌  No, Cancel"}]
        )
        return

    _do_mgr_write(sender, session, idx, product, sold, mid)


def handle_mgr_edit_overwrite_text(sender, text, session):
    if text in ("yes", "y"):
        do_mgr_edit_overwrite(sender, session)
    elif text in ("no", "n", "cancel"):
        cancel_mgr_edit_overwrite(sender, session)
    else:
        send_buttons(sender, "Overwrite?",
            [{"id": "mgr_edit_overwrite_yes", "title": "✅  Yes"},
             {"id": "mgr_edit_overwrite_no",  "title": "❌  No"}]
        )


def do_mgr_edit_overwrite(sender, session):
    idx  = session.get("pending_idx", 0)
    sold = session.get("pending_sold", 0)
    session.update({"mode": "mgr_market_edit", "edit_product_idx": idx})
    SESSIONS[sender] = session
    _do_mgr_write(sender, session, idx, PRODUCTS[idx], sold, session["edit_market_id"])


def cancel_mgr_edit_overwrite(sender, session):
    send_text(sender, "✅ Kept existing value.")
    send_market_review(sender, session.get("edit_market_id", ""))


def _do_mgr_write(sender, session, idx, product, sold, market_id):
    try:
        write_sold_box(market_id, idx, sold)
    except Exception as exc:
        send_text(sender, f"❌ Save failed: {exc}")
        return
    session.setdefault("sold_data", {})[product] = sold
    SESSIONS[sender] = session
    send_text(sender, f"✅ *{product}* → {sold:.0f} boxes saved!")
    send_market_review(sender, market_id)


# ── M-8: All Complete Alert ────────────────────────────────────────────────

def notify_all_complete(sender: str):
    try:
        all_data = get_all_sheet_data()
        totals   = compute_week_totals(all_data)
    except Exception:
        totals = {"total_alloc": 0, "total_sold": 0}

    ta  = totals["total_alloc"]
    ts  = totals["total_sold"]
    pct = (ts / ta * 100) if ta > 0 else 0

    send_text(sender,
        "🏁 *All Markets Completed!*\n━━━━━━━━━━━━━━━━━━━━\n"
        "✅ 12/12 Markets Complete\n\n"
        f"📦 Allocated : *{ta:,.0f}*\n"
        f"💰 Sold      : *{ts:,.0f}*\n"
        f"📊 Sell-thru : *{pct:.1f}%*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Type *close week* or tap below:"
    )
    send_buttons(sender, "━━━━━━━━━━━━━━━━━━━━",
        [{"id": "mgr_close_week", "title": "🔄  Close Week"}]
    )


# ── M-9: Close Week ────────────────────────────────────────────────────────

def handle_close_week_request(sender: str):
    if not is_manager(sender):
        send_text(sender, "🔒 Only the manager can close the week.")
        return

    try:
        complete = all_markets_complete()
    except Exception:
        complete = False

    msg = (
        "🔐 *Close Week Confirmation*\n━━━━━━━━━━━━━━━━━━━━\n"
        "✅ All 12 markets complete!\n\n"
        if complete else
        "⚠️ *Warning: Incomplete Markets*\n━━━━━━━━━━━━━━━━━━━━\n"
        "Some markets still have missing data.\n\n"
    )
    send_buttons(sender,
        msg +
        "This will:\n"
        "• Move Current → Previous Week\n"
        "• Archive Previous → History\n"
        "• Reset Current Week\n"
        "━━━━━━━━━━━━━━━━━━━━\nConfirm?",
        [
            {"id": "close_confirm_yes", "title": "✅  Confirm Close"},
            {"id": "close_confirm_no",  "title": "❌  Cancel"},
        ]
    )
    SESSIONS[sender] = {"mode": "close_confirm"}


def handle_close_confirm_text(sender: str, text: str):
    if text in ("yes", "y", "confirm", "close"):
        do_close_week(sender)
    elif text in ("no", "n", "cancel"):
        SESSIONS.pop(sender, None)
        send_text(sender, "✅ Week close cancelled.")
        send_manager_menu(sender)
    else:
        send_buttons(sender, "Confirm week close?",
            [{"id": "close_confirm_yes", "title": "✅  Confirm"},
             {"id": "close_confirm_no",  "title": "❌  Cancel"}]
        )


def do_close_week(sender: str):
    if not is_manager(sender):
        send_text(sender, "🔒 Access denied.")
        return

    SESSIONS.pop(sender, None)
    send_text(sender,
        "🔄 *Processing…*\n━━━━━━━━━━━━━━━━━━━━\n"
        "Archiving data… Updating history… Preparing new week… ⏳"
    )
    try:
        rotate_sheets()
        send_text(sender,
            "✅ *Week Closed Successfully!*\n━━━━━━━━━━━━━━━━━━━━\n"
            "📊 Current → Previous Week\n"
            "🗂️  Previous → History\n"
            "📋 New Week → Ready\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Workers can begin new week data entry."
        )
        send_manager_menu(sender)
    except Exception as exc:
        send_text(sender, f"❌ Week close failed: {exc}\nCheck Google Sheet manually.")


# ── Backward compat alias ──────────────────────────────────────────────────
send_market_detail_status = send_market_review