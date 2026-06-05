from app.sheets import (
    get_market_allocations, get_markets_by_day, write_sold_box,
    all_markets_complete, MARKETS, PRODUCTS,
)
from app.whatsapp import send_text, send_buttons, send_list
from app.shared import (
    SESSIONS, MANAGER_NUMBERS, PRODUCT_EMOJIS, NUMBER_EMOJIS, DAY_ICONS,
    _read_sold_data_from_sheet,
)

# In-memory set of markets completed this week (locked permanently)
# Key: sender phone, Value: set of completed market_ids
COMPLETED_MARKETS: dict = {}


# ── Step 1–2: Greeting / session resume ───────────────────────────────────

def route_on_greeting(sender: str, session: dict):
    """
    CHANGE 2: Resume → directly ask product question.
    No "Welcome back" screen. No button tap needed.
    """
    if session.get("market_id") and session.get("mode") in ("entry", "review", "edit"):
        # Directly resume from where they left off
        market_id = session["market_id"]
        try:
            allocs    = get_market_allocations(market_id)
            sold_data = _read_sold_data_from_sheet(market_id)
        except Exception as exc:
            send_text(sender, f"❌ Error reading sheet: {exc}")
            return

        session["mode"]        = "entry"
        session["allocations"] = allocs
        session["sold_data"]   = sold_data
        SESSIONS[sender]       = session

        idx = session.get("product_index", 0)
        if idx >= len(PRODUCTS):
            send_review_screen(sender, session)
            return

        # Directly ask the pending product — no button, no screen
        send_text(sender,
            f"▶️ *Resuming {market_id}* — product {idx + 1}/{len(PRODUCTS)}"
        )
        _ask_product(sender, session)
    else:
        send_worker_menu(sender)


def send_worker_menu(sender: str):
    """
    CHANGE 1: All three days in ONE message. All Markets button removed.
    """
    SESSIONS.pop(sender, None)
    send_buttons(sender,
        "🌾 *AGRI MARKET BOT*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📅 Current Week Data Entry\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Select a day to begin:",
        [
            {"id": "day_monday",    "title": "🟦  Monday"},
            {"id": "day_wednesday", "title": "🟧  Wednesday"},
            {"id": "day_friday",    "title": "🟥  Friday"},
        ]
    )


def send_day_list(sender: str, day: str):
    icon = DAY_ICONS.get(day, "")
    markets = get_markets_by_day(day)
    is_mgr = sender in MANAGER_NUMBERS
    btn_prefix = "mgr_view_market_" if is_mgr else "market_"

    rows = []
    completed = COMPLETED_MARKETS.get(sender, set())

    for m in markets:
        market_id = m["id"]

        sold_data = _read_sold_data_from_sheet(market_id)
        filled_count = sum(
            1 for v in sold_data.values()
            if v is not None
        )

        if market_id in completed or filled_count == len(PRODUCTS):
            desc = "✅ Finished (Locked)"
        else:
            desc = f"✏️ {filled_count}/{len(PRODUCTS)} Entered"

        rows.append({
            "id": f"{btn_prefix}{market_id}",
            "title": market_id,
            "description": desc,
        })

    send_list(
        sender,
        f"{icon} *{day.upper()} MARKETS*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Markets: " + "  ".join(m["id"] for m in markets) + "\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Tap to select:",
        "Select Market",
        [{"title": f"{icon} {day}", "rows": rows}]
    )
# ── Steps 3–5: Market detail ───────────────────────────────────────────────

def send_market_detail(sender: str, market_id: str):
    """
    CHANGE 3: Market lock check.
    If worker is already in entry mode for another market → block.
    CHANGE 4: If market is completed → show locked message, no edit.
    """
    # CHANGE 4: Check if this market is already completed (locked)
    completed = COMPLETED_MARKETS.get(sender, set())
    if market_id in completed:
        day  = MARKETS.get(market_id, "")
        icon = DAY_ICONS.get(day, "📦")
        send_buttons(sender,
            f"{icon} *{market_id} — Already Completed* ✅\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"This market is locked.\n"
            f"Sales data has been saved to Google Sheets.\n"
            f"━━━━━━━━━━━━━━━━━━━━",
            [
                {"id": "day_monday",    "title": "🟦  Monday"},
                {"id": "day_wednesday", "title": "🟧  Wednesday"},
                {"id": "day_friday",    "title": "🟥  Friday"},
            ]
        )
        return

    # CHANGE 3: If already in entry for a DIFFERENT market → block
    session = SESSIONS.get(sender, {})
    active_market = session.get("market_id")
    if (active_market and active_market != market_id
            and session.get("mode") in ("entry", "review", "edit")):
        day_active = MARKETS.get(active_market, "")
        icon_active = DAY_ICONS.get(day_active, "📦")
        send_buttons(sender,
            f"🔒 *Market Locked*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"You are currently entering sales for:\n"
            f"{icon_active} *{active_market}*\n\n"
            f"Complete *{active_market}* first before\n"
            f"selecting *{market_id}*.\n"
            f"━━━━━━━━━━━━━━━━━━━━",
            [
                {"id": "resume_entry", "title": f"▶️  Return to {active_market}"},
                {"id": "menu",         "title": "🏠  Main Menu"},
            ]
        )
        return

    # Normal market detail flow
    try:
        allocs    = get_market_allocations(market_id)
        sold_data = _read_sold_data_from_sheet(market_id)
    except Exception as exc:
        send_text(sender, f"❌ Error reading sheet: {exc}")
        return

    filled_count = sum(1 for v in sold_data.values() if v is not None)
    all_filled   = filled_count == len(PRODUCTS)
    day          = MARKETS.get(market_id, "")
    icon         = DAY_ICONS.get(day, "📦")

    lines = []
    for i, (prod, boxes) in enumerate(allocs.items()):
        sold   = sold_data.get(prod)
        status = f"✅ {sold:.0f}" if sold is not None else "⬜ --"
        lines.append(f"{NUMBER_EMOJIS[i]} *{prod}* {boxes:.0f}bx | {status}")

    # ── CONDITION CHECK ───────────────────────────────────────────────────
    # Condition 1: Worker already finished (COMPLETED_MARKETS) → handled above
    # Condition 2: Sheet has all 10 filled BUT worker never pressed Finish
    #              → show data + warn + ask if they want to mark complete
    # Condition 3: Partially filled or empty → normal Enter Sales
    # ─────────────────────────────────────────────────────────────────────

    SESSIONS[sender] = {
        "mode":          "idle",
        "market_id":     market_id,
        "allocations":   allocs,
        "sold_data":     sold_data,
        "product_index": filled_count,
    }

    send_text(sender,
        f"{icon} *{market_id} | {day.upper()}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        + "\n".join(lines) +
        f"\n━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 Total: *{sum(allocs.values()):.0f} boxes* | "
        f"✏️ *{filled_count}/{len(PRODUCTS)} entered*"
    )

    if all_filled:
        # Condition 2: Sheet full but worker didn't press Finish
        # Show options: mark complete (lock) OR edit existing data
        send_buttons(sender,
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ *All 10 products filled in sheet.*\n"
            f"Did you finish entering sales for *{market_id}*?",
            [
                {"id": "finish_market",  "title": "🏁  Yes, Mark Complete"},
                {"id": "enter_sales",    "title": "✏️  No, Edit Data"},
                {"id": "day_monday",     "title": "◀  Back to Days"},
            ]
        )
    else:
        # Condition 3: Partial or empty → Enter Sales
        send_buttons(sender,
            f"What would you like to do with *{market_id}*?",
            [
                {"id": "enter_sales", "title": "✏️  Enter Sales"},
                {"id": "day_monday",  "title": "◀  Back to Days"},
                {"id": "menu",        "title": "🏠  Main Menu"},
            ]
        )


# ── Steps 5–11: Entry flow ─────────────────────────────────────────────────

def start_fresh_entry(sender: str, session: dict):
    if not session.get("market_id"):
        send_text(sender, "⚠️ Please select a market first. Send *hi* to start.")
        return

    market_id = session["market_id"]
    try:
        allocs    = get_market_allocations(market_id)
        sold_data = _read_sold_data_from_sheet(market_id)
    except Exception as exc:
        send_text(sender, f"❌ Error reading sheet: {exc}")
        return

    start_idx = next(
        (i for i, p in enumerate(PRODUCTS) if sold_data.get(p) is None), None
    )
    session["allocations"] = allocs
    session["sold_data"]   = sold_data

    if start_idx is None:
        session["mode"]          = "review"
        session["product_index"] = len(PRODUCTS)
        SESSIONS[sender]         = session
        send_review_screen(sender, session)
        return

    session["mode"]          = "entry"
    session["product_index"] = start_idx
    SESSIONS[sender]         = session

    day  = MARKETS.get(market_id, "")
    icon = DAY_ICONS.get(day, "📦")
    send_text(sender,
        f"{icon} *Sales Entry — Market {market_id}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Enter sold boxes for each product.\n"
        f"• Type a number and send.\n"
        f"• Type *skip* to skip a product.\n"
        f"• Type *review* to see all entries.\n"
        f"• Type *cancel* to pause.\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    _ask_product(sender, session)


def resume_entry(sender: str, session: dict):
    """Called from button press — same direct resume logic."""
    if not session.get("market_id"):
        send_text(sender, "⚠️ Session expired. Please select your market again.")
        send_worker_menu(sender)
        return

    market_id = session["market_id"]
    try:
        allocs    = get_market_allocations(market_id)
        sold_data = _read_sold_data_from_sheet(market_id)
    except Exception as exc:
        send_text(sender, f"❌ Error reading sheet: {exc}")
        return

    session["mode"]        = "entry"
    session["allocations"] = allocs
    session["sold_data"]   = sold_data
    SESSIONS[sender]       = session

    idx = session.get("product_index", 0)
    if idx >= len(PRODUCTS):
        send_review_screen(sender, session)
        return

    _ask_product(sender, session)


def pause_entry(sender: str, session: dict):
    session["mode"] = "idle"
    SESSIONS[sender] = session
    send_buttons(sender,
        "⏸️ *Entry Paused*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Your progress is saved.\n"
        "Send *hi* to resume.",
        [{"id": "menu", "title": "🏠  Main Menu"}]
    )


def _ask_product(sender: str, session: dict):
    idx      = session["product_index"]
    product  = PRODUCTS[idx]
    emoji    = PRODUCT_EMOJIS[idx]

    try:
        fresh_allocs = get_market_allocations(session["market_id"])
        session["allocations"] = fresh_allocs
        SESSIONS[sender] = session
    except Exception:
        pass

    alloc    = session["allocations"].get(product, 0)
    existing = session.get("sold_data", {}).get(product)

    if existing is not None:
        existing_note = (
            "\n⚠️ *Already in sheet: " + f"{existing:.0f}" + " boxes*\n"
            "Enter new value to overwrite, or type *skip*"
        )
    else:
        existing_note = ""

    send_text(sender,
        f"{emoji} *{product}*  ({idx + 1}/{len(PRODUCTS)})\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Market    : *{session['market_id']}*\n"
        f"Allocated : *{alloc:.0f} boxes*"
        + existing_note
        + "\n━━━━━━━━━━━━━━━━━━━━\n"
        f"How many boxes *sold*? _(0 to {alloc:.0f})_"
    )


def handle_entry_input(sender: str, text: str, session: dict):
    t = text.strip().lower()
    if t in ("cancel", "stop", "pause", "quit"):
        pause_entry(sender, session)
        return
    if t == "skip":
        _advance_product(sender, session, skipped=True)
        return
    if t == "review":
        session["mode"] = "review"
        SESSIONS[sender] = session
        send_review_screen(sender, session)
        return

    idx     = session["product_index"]
    product = PRODUCTS[idx]
    alloc   = session["allocations"].get(product, 0)

    try:
        sold = float(text.strip())
    except ValueError:
        send_text(sender,
            "⚠️ Invalid — enter a number.\n"
            f"Allocated: *{alloc:.0f} boxes*\n"
            "Or type *skip*."
        )
        return

    if sold < 0:
        send_text(sender, f"⚠️ Cannot be negative. Enter 0 to {alloc:.0f}.")
        return
    if sold > alloc:
        send_text(sender,
            f"⚠️ {sold:.0f} exceeds allocated {alloc:.0f} boxes.\n"
            f"Enter a value between 0 and {alloc:.0f}."
        )
        return

    session.pop("pending_sold", None)
    session.pop("pending_idx", None)
    SESSIONS[sender] = session

    _process_validated_input(sender, session, idx, product, sold)


def _process_validated_input(sender, session, idx, product, sold):
    market_id  = session["market_id"]
    fresh_sold = _read_sold_data_from_sheet(market_id)
    session["sold_data"] = fresh_sold
    existing = fresh_sold.get(product)

    if existing is not None:
        session["mode"]         = "overwrite_confirm"
        session["pending_sold"] = sold
        session["pending_idx"]  = idx
        SESSIONS[sender]        = session
        send_buttons(sender,
            f"⚠️ *{product}* already has data!\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Sheet value : *{existing:.0f} boxes*\n"
            f"Your input  : *{sold:.0f} boxes*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Overwrite?",
            [
                {"id": "overwrite_yes", "title": "✅  Yes, Overwrite"},
                {"id": "overwrite_no",  "title": "❌  No, Keep Old"},
            ]
        )
        return

    _write_and_advance(sender, session, idx, product, sold)


def handle_overwrite_text(sender, text, session):
    if text in ("yes", "y", "overwrite"):
        do_overwrite(sender, session)
    elif text in ("no", "n", "keep"):
        keep_existing(sender, session)
    else:
        send_buttons(sender, "Overwrite existing value?",
            [
                {"id": "overwrite_yes", "title": "✅  Yes, Overwrite"},
                {"id": "overwrite_no",  "title": "❌  No, Keep Old"},
            ]
        )


def do_overwrite(sender, session):
    idx  = session.get("pending_idx", 0)
    sold = session.get("pending_sold", 0)
    session["mode"]          = "entry"
    session["product_index"] = idx
    SESSIONS[sender]         = session
    _write_and_advance(sender, session, idx, PRODUCTS[idx], sold)


def keep_existing(sender, session):
    idx = session.get("pending_idx", 0)
    session["mode"]          = "entry"
    session["product_index"] = idx
    SESSIONS[sender]         = session
    send_text(sender, f"✅ Kept existing value for *{PRODUCTS[idx]}*.")
    _advance_product(sender, session)


def _write_and_advance(sender, session, idx, product, sold):
    market_id = session["market_id"]
    try:
        write_sold_box(market_id, idx, sold)
    except Exception as exc:
        send_text(sender, f"❌ Save failed: {exc}\nTry again.")
        return
    session["product_index"] = idx
    if "sold_data" not in session:
        session["sold_data"] = {}
    session["sold_data"][product] = sold
    SESSIONS[sender] = session
    send_text(sender, f"✅ *{product}* → {sold:.0f} boxes saved!")
    _advance_product(sender, session)


def _advance_product(sender, session, skipped=False):
    if skipped:
        send_text(sender, f"⏭️ Skipped *{PRODUCTS[session['product_index']]}*.")
    session["product_index"] = session["product_index"] + 1
    SESSIONS[sender] = session
    if session["product_index"] < len(PRODUCTS):
        session["mode"] = "entry"
        _ask_product(sender, session)
    else:
        session["mode"] = "review"
        SESSIONS[sender] = session
        send_text(sender, "✅ *All products entered!* Loading review…")
        send_review_screen(sender, session)


# ── Step 12: Review screen ─────────────────────────────────────────────────

def send_review_screen(sender: str, session: dict):
    market_id = session["market_id"]
    try:
        allocs    = get_market_allocations(market_id)
        sold_data = _read_sold_data_from_sheet(market_id)
    except Exception as exc:
        send_text(sender, f"❌ Error reading sheet: {exc}")
        return

    session["allocations"] = allocs
    session["sold_data"]   = sold_data
    session["mode"]        = "review"
    SESSIONS[sender]       = session

    day         = MARKETS.get(market_id, "")
    icon        = DAY_ICONS.get(day, "📦")
    total_alloc = sum(allocs.values())
    total_sold  = sum(v for v in sold_data.values() if v is not None)
    filled      = sum(1 for v in sold_data.values() if v is not None)
    sell_thru   = (total_sold / total_alloc * 100) if total_alloc > 0 else 0

    lines = []
    for i, (prod, boxes) in enumerate(allocs.items()):
        sold   = sold_data.get(prod)
        status = f"✅ {sold:.0f}" if sold is not None else "⬜ --"
        lines.append(f"{NUMBER_EMOJIS[i]} *{prod}* {boxes:.0f}bx | {status}")

    send_text(sender,
        f"{icon} *{market_id} — REVIEW*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        + "\n".join(lines) +
        f"\n━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 Allocated : *{total_alloc:.0f}*\n"
        f"💰 Sold      : *{total_sold:.0f}*\n"
        f"📊 Sell-thru : *{sell_thru:.1f}%*\n"
        f"✏️  Entries  : *{filled}/{len(PRODUCTS)}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Type a number (1 to {len(PRODUCTS)}) to edit a product."
    )
    send_buttons(sender,
        f"Ready to submit *{market_id}*?",
        [
            {"id": "finish_market", "title": "🏁  Finish Market"},
            {"id": "enter_sales",   "title": "✏️  Edit Product"},
            {"id": "menu",          "title": "🏠  Main Menu"},
        ]
    )


# ── Step 13: Edit product from review ─────────────────────────────────────

def start_edit_product(sender, session, product_idx):
    session["mode"]       = "edit"
    session["edit_index"] = product_idx
    SESSIONS[sender]      = session
    _ask_edit_product_prompt(sender, session)


def _ask_edit_product_prompt(sender, session):
    idx      = session["edit_index"]
    product  = PRODUCTS[idx]
    alloc    = session["allocations"].get(product, 0)
    existing = session.get("sold_data", {}).get(product)
    emoji    = PRODUCT_EMOJIS[idx]
    mid      = session["market_id"]

    if existing is not None:
        existing_note = "\n📋 *Current: " + f"{existing:.0f}" + " boxes*"
    else:
        existing_note = "\n📋 *No value yet*"

    send_text(sender,
        f"✏️ *Editing: {emoji} {product}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Market    : *{mid}*\n"
        f"Allocated : *{alloc:.0f} boxes*"
        + existing_note
        + f"\n━━━━━━━━━━━━━━━━━━━━\n"
        f"Enter new sold value (0 to {alloc:.0f})\n"
        f"Or type *back* to return."
    )


def handle_edit_input(sender, text, session):
    t = text.strip().lower()
    if t in ("back", "cancel", "review"):
        session["mode"] = "review"
        SESSIONS[sender] = session
        send_review_screen(sender, session)
        return

    idx     = session["edit_index"]
    product = PRODUCTS[idx]
    alloc   = session["allocations"].get(product, 0)

    try:
        sold = float(text.strip())
    except ValueError:
        send_text(sender, f"⚠️ Invalid — enter a number (0 to {alloc:.0f}).")
        return
    if sold < 0 or sold > alloc:
        send_text(sender, f"⚠️ Must be between 0 and {alloc:.0f}.")
        return

    market_id  = session["market_id"]
    fresh_sold = _read_sold_data_from_sheet(market_id)
    existing   = fresh_sold.get(product)
    session["sold_data"] = fresh_sold

    if existing is not None:
        session["mode"]             = "overwrite_confirm"
        session["pending_sold"]     = sold
        session["pending_idx"]      = idx
        session["return_to_review"] = True
        SESSIONS[sender]            = session
        send_buttons(sender,
            f"⚠️ *{product}* has *{existing:.0f}* in sheet.\n"
            f"Overwrite with *{sold:.0f}*?",
            [
                {"id": "overwrite_yes", "title": "✅  Yes, Overwrite"},
                {"id": "overwrite_no",  "title": "❌  No, Keep Old"},
            ]
        )
        return

    try:
        write_sold_box(market_id, idx, sold)
    except Exception as exc:
        send_text(sender, f"❌ Save failed: {exc}")
        return

    session["sold_data"][product] = sold
    session["mode"]               = "review"
    SESSIONS[sender]              = session
    send_text(sender, f"✅ *{product}* updated → {sold:.0f} boxes saved!")
    send_review_screen(sender, session)


# ── Steps 14–17: Market completion ────────────────────────────────────────

def complete_market(sender: str, session: dict):
    """
    CHANGE 4: After finish → market locked in COMPLETED_MARKETS.
    Same market tap → shows locked message (handled in send_market_detail).
    """
    market_id = session["market_id"]
    try:
        allocs    = get_market_allocations(market_id)
        sold_data = _read_sold_data_from_sheet(market_id)
    except Exception as exc:
        send_text(sender, f"❌ Error reading sheet: {exc}")
        return

    total_alloc = sum(allocs.values())
    total_sold  = sum(v for v in sold_data.values() if v is not None)
    sell_thru   = (total_sold / total_alloc * 100) if total_alloc > 0 else 0
    filled      = sum(1 for v in sold_data.values() if v is not None)
    day         = MARKETS.get(market_id, "")
    icon        = DAY_ICONS.get(day, "📦")

    lines = []
    for i, (prod, boxes) in enumerate(allocs.items()):
        sold = sold_data.get(prod)
        if sold is not None:
            lines.append(f"{PRODUCT_EMOJIS[i]} {prod}: {sold:.0f}/{boxes:.0f}")
        else:
            lines.append(f"{PRODUCT_EMOJIS[i]} {prod}: --/{boxes:.0f}")

    # CHANGE 4: Lock this market permanently for this worker
    if sender not in COMPLETED_MARKETS:
        COMPLETED_MARKETS[sender] = set()
    COMPLETED_MARKETS[sender].add(market_id)

    # Clear session
    SESSIONS.pop(sender, None)

    send_text(sender,
        f"🎉 *{market_id} — COMPLETED & LOCKED!*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        + "\n".join(lines) +
        f"\n━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 Total Allocated : *{total_alloc:.0f}*\n"
        f"💰 Total Sold      : *{total_sold:.0f}*\n"
        f"📊 Sell-Through    : *{sell_thru:.1f}%*\n"
        f"✏️  Entries        : *{filled}/{len(PRODUCTS)}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ {market_id} is now locked. Data saved to Google Sheets."
    )
    send_buttons(sender,
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Select another day to continue:",
        [
            {"id": "day_monday",    "title": "🟦  Monday"},
            {"id": "day_wednesday", "title": "🟧  Wednesday"},
            {"id": "day_friday",    "title": "🟥  Friday"},
        ]
    )

    try:
        if all_markets_complete():
            _notify_worker_all_complete(sender)
            import app.manager as mgr_module
            for mgr in MANAGER_NUMBERS:
                mgr_module.notify_all_complete(mgr)
    except Exception as exc:
        print(f"Completion check error: {exc}")


def _notify_worker_all_complete(sender: str):
    send_text(sender,
        "🏁 *All 12 Markets Complete!*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "✅ All sales data saved.\n"
        "Manager will close the week shortly."
    )