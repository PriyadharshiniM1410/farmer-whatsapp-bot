"""
worker.py — Worker workflow: greeting, dashboard, data entry, and market lock.
"""

from app.sheets import (
    get_market_allocations, write_sold_box,
    all_markets_complete,
    get_manager_numbers,
    get_worker_by_phone, get_sold_data,
    get_all_sheet_data, get_reallocation_view,
    build_market_map, get_products, get_product_emoji,
)
from app.whatsapp import send_text, send_buttons, send_list
from app.shared import SESSIONS, is_manager, get_day_icon, get_days_order

COMPLETED_MARKETS: dict = {}


# ── Helper ────────────────────────────────────────────────────────────────

def update_sheet_sold_qty(market_id: str, product_name: str, sold_val: int):
    """Write sold quantity to Google Sheets for the given product."""
    try:
        products = get_products()
        for idx, p_name in enumerate(products):
            if p_name == product_name:
                write_sold_box(market_id, idx, float(sold_val))
                return
    except Exception as exc:
        print(f"❌ update_sheet_sold_qty Error: {exc}")
        raise exc


# ── Step 1: Greeting & main menu ──────────────────────────────────────────

def route_on_greeting(sender: str, session: dict):
    """Identify worker and show assigned markets."""
    worker = get_worker_by_phone(sender)
    if not worker:
        send_text(sender, "⚠️ Your number is not registered.\nPlease contact your manager.")
        return

    name     = worker.get("name", "Worker")
    assigned = []
    for day in get_days_order():
        mid = worker.get(day, "-")
        if mid and mid != "-":
            assigned.append({"day": day, "market_id": mid})

    if not assigned:
        send_text(sender, f"👋 Hello *{name}*!\n⚠️ No markets assigned. Contact manager.")
        return

    all_data = get_all_sheet_data()
    products = get_products()
    SESSIONS[sender] = {"mode": "idle", "worker": worker, "name": name}

    status_lines   = []
    allocation_rows = []
    market_rows    = []

    for a in assigned:
        mid  = a["market_id"]
        day  = a["day"]
        icon = get_day_icon(day)

        sold    = get_sold_data(mid, all_data)
        filled  = sum(1 for v in sold.values() if v is not None and v != "")
        is_locked = mid in COMPLETED_MARKETS.get(sender, set())
        status  = "✅ Complete" if (is_locked or filled == len(products)) else "⬜ Not started"

        status_lines.append(f"{icon} *{mid}* — {day} | {status}")
        allocation_rows.append({
            "id":          f"view_realloc_{mid}",
            "title":       f"📦 View {mid} Allocation",
            "description": f"Check remaining stock for {mid}",
        })
        market_rows.append({
            "id":          f"market_{mid}",
            "title":       f"Open {mid}",
            "description": f"View/Enter entries for {day}",
        })

    sections_payload = [
        {"title": "Allocation Splits",  "rows": allocation_rows},
        {"title": "Market Schedule",    "rows": market_rows},
    ]

    body_text = (
        f"🌾 *AGRI MARKET BOT*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👋 Hello *{name}*!\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        + "\n".join(status_lines)
        + f"\n━━━━━━━━━━━━━━━━━━━━\n"
        f"👇 Select an option to view or enter data:"
    )

    send_list(
        to=sender,
        body=body_text,
        button_label="Select Option",
        sections=sections_payload,
    )


# ── Step 2: Sales dashboard ───────────────────────────────────────────────

def send_product_manifest_dashboard(sender: str, market_id: str):
    """Show the product sales dashboard for a market."""
    if market_id in COMPLETED_MARKETS.get(sender, set()):
        send_text(sender,
            f"🔒 *{market_id} is locked.*\n"
            "Data already submitted and verified."
        )
        route_on_greeting(sender, SESSIONS.get(sender, {}))
        return

    try:
        all_data   = get_all_sheet_data(force=True)
        market_map = build_market_map(all_data)
        products   = get_products(all_data)
        allocs     = get_market_allocations(market_id, all_data, market_map, products)
        sold_data  = get_sold_data(market_id, all_data, market_map, products)
    except Exception as exc:
        send_text(sender, f"❌ Error loading dashboard metrics: {exc}")
        return

    day      = market_map.get(market_id, {}).get("day", "Market")
    day_icon = get_day_icon(day)

    product_rows    = []
    filled_count    = 0
    total_allocated = 0
    total_sold      = 0

    for idx, p_name in enumerate(products):
        p_emoji = get_product_emoji(p_name)

        allocated    = allocs.get(p_name, 0) if isinstance(allocs, dict) else 0
        current_sold = sold_data.get(p_name, None) if isinstance(sold_data, dict) else None

        total_allocated += allocated

        if current_sold is not None and current_sold != "":
            filled_count += 1
            try:
                total_sold += int(float(current_sold))
            except ValueError:
                pass
            status_tag = f"✅ Sold: {int(float(current_sold))}"
        else:
            status_tag = "⬜ Pending Entry"

        product_rows.append({
            "id":          f"ep_{market_id}_{idx}",
            "title":       f"{p_emoji} {p_name}",
            "description": f"Alloc: {allocated:.0f} | {status_tag}",
        })

    session = SESSIONS.get(sender, {})
    SESSIONS[sender] = {
        **session,
        "market_id":      market_id,
        "current_market": market_id,
    }

    sell_thru = (total_sold / total_allocated * 100) if total_allocated > 0 else 0

    body_text = (
        f"{day_icon} *{market_id} — SALES DASHBOARD*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 Total Allocated : {total_allocated:.0f}\n"
        f"💰 Total Sold      : {total_sold}\n"
        f"📊 Sell-thru Qty   : {sell_thru:.1f}%\n"
        f"✏️ Logged Progress : *{filled_count}/{len(products)} Products*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👇 Tap below to select any product to enter or edit its numbers directly:"
    )

    send_list(
        to=sender,
        body=body_text,
        button_label="Select Product",
        sections=[{"title": "Select Product", "rows": product_rows}],
    )

    if filled_count == len(products):
        send_buttons(
            to=sender,
            body="✅ All products are completely filled out! If everything looks correct, submit your final sheet lock.",
            buttons=[{"id": f"submit_lock_{market_id}", "title": "🔒 Submit & Lock Market"}],
        )


# ── Step 3: Lock and finalize ─────────────────────────────────────────────

def complete_market(sender: str, session: dict):
    market_id = session.get("current_market") or session.get("market_id")
    if not market_id:
        route_on_greeting(sender, session)
        return

    try:
        all_data   = get_all_sheet_data(force=True)
        market_map = build_market_map(all_data)
        products   = get_products(all_data)
        allocs     = get_market_allocations(market_id, all_data, market_map, products)
        sold_data  = get_sold_data(market_id, all_data, market_map, products)
    except Exception:
        products, allocs, sold_data = get_products(), {}, {}

    COMPLETED_MARKETS.setdefault(sender, set()).add(market_id)
    SESSIONS.pop(sender, None)

    lines = [
        f"🎉 *{market_id} — COMPLETED & LOCKED!*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f" # │ Product      │Alloc│ Sold\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    ]
    for i, prod in enumerate(products):
        emoji = get_product_emoji(prod)
        alloc = allocs.get(prod, 0)
        sold  = sold_data.get(prod)
        sold_str = f"✅ {sold:.0f}" if sold is not None and sold != "" else "⬜ --"
        lines.append(f"{i + 1:>2} │ {emoji}{prod:<10} │{alloc:>4.0f} │{sold_str}")

    lines.append("━━━━━━━━━━━━━━━━━━━━\n✅ Data saved and locked to Google Sheets!")
    send_text(sender, "\n".join(lines))

    send_buttons(sender,
        "━━━━━━━━━━━━━━━━━━━━",
        [{"id": f"view_realloc_{market_id}", "title": "📦 View Allocation"}],
    )

    try:
        if all_markets_complete():
            import app.manager as mgr_module
            for mgr in get_manager_numbers():
                mgr_module.notify_all_complete(mgr)
    except Exception as exc:
        print(f"All complete check error: {exc}")


# ── Step 4: Allocation split view ─────────────────────────────────────────

def send_allocation_view(sender: str, market_id: str):
    all_data   = get_all_sheet_data(force=True)
    market_map = build_market_map(all_data)
    products   = get_products(all_data)

    day      = market_map.get(market_id, {}).get("day", "")
    icon     = get_day_icon(day)

    days_order = get_days_order()
    if day in days_order and days_order.index(day) + 1 < len(days_order):
        next_day = days_order[days_order.index(day) + 1]
    else:
        next_day = ""

    if not next_day:
        send_text(sender, "ℹ️ Friday is the last day. No reallocation needed.")
        return

    try:
        day_markets = [mid for mid, info in market_map.items() if info["day"] == day]
        pending     = []
        for mid in day_markets:
            sold   = get_sold_data(mid, all_data, market_map, products)
            filled = sum(1 for v in sold.values() if v is not None and v != "")
            if filled < len(products):
                pending.append(mid)
    except Exception as exc:
        send_text(sender, f"❌ Error: {exc}")
        return

    if pending:
        pending_str = ", ".join(pending)
        send_text(sender,
            f"{icon} *{day} — Allocation Status*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ {market_id} — Complete\n"
            + "\n".join(f"⏳ {mid} — Pending" for mid in pending)
            + f"\n━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ *{pending_str}* not finished yet.\n"
            f"Allocation view available once all {day} markets are complete."
        )
        return

    try:
        rows = get_reallocation_view(market_id, all_data)
    except Exception as exc:
        send_text(sender, f"❌ Error: {exc}")
        return

    next_markets = [mid for mid, info in market_map.items() if info["day"] == next_day]
    header = (
        f"{icon} *{market_id} — REALLOCATION PLAN*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 *Product*        | *Rem* | *Plan*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
    )

    table_lines = []
    for r in rows:
        prod_emoji = r["emoji"]
        prod_name  = r["product"]
        remain_qty = r["remain"]

        if remain_qty > 0:
            table_lines.append(f"{prod_emoji} *{prod_name:<8}* | {remain_qty:.0f} | 👇")
            total_next_alloc  = sum(r["next_day_allocs"].get(m, 0) for m in next_markets)
            accumulated_split = 0
            for idx, m in enumerate(next_markets):
                next_alloc = r["next_day_allocs"].get(m, 0)
                if total_next_alloc > 0 and next_alloc > 0:
                    if idx == len(next_markets) - 1:
                        exact_split = remain_qty - accumulated_split
                    else:
                        exact_split = round((next_alloc / total_next_alloc) * remain_qty)
                        accumulated_split += exact_split
                    if exact_split > 0:
                        table_lines.append(f"   └─ {m}: *{exact_split:.0f} boxes*")
            table_lines.append("")
        else:
            table_lines.append(f"{prod_emoji} *{prod_name:<8}* | 0   | ✅")

    send_text(sender,
        header + "\n".join(table_lines)
        + "━━━━━━━━━━━━━━━━━━━━\n🚛 *Load your truck as per the plan above!*"
    )
    send_buttons(sender, "━━━━━━━━━━━━━━━━━━━━", [{"id": "menu", "title": "🏠 Main Menu"}])