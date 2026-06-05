"""
bot_logic.py — Entry point: routes messages to worker or manager modules.

Imports all business logic from:
  app/shared.py   — SESSIONS, constants, sheet helpers
  app/worker.py   — Worker workflow 
  app/manager.py  — Manager workflow 
"""

import re

from app.shared import SESSIONS, MANAGER_NUMBERS
from app.whatsapp import send_text
import app.worker as worker
import app.manager as manager


# ══════════════════════════════════════════════════════════════════════════
#  PUBLIC ENTRY POINTS
# ══════════════════════════════════════════════════════════════════════════

def handle_message(sender: str, text: str):
    """Route plain-text messages based on role + session mode."""
    try:
        t       = text.strip()
        t_lower = t.lower()
        session = SESSIONS.get(sender, {})
        mode    = session.get("mode", "idle")
        is_mgr  = sender in MANAGER_NUMBERS

        # ── Close week command ──
        if t_lower in ("close week", "closeweek", "close_week"):
            manager.handle_close_week_request(sender)
            return

        # ── Mode-specific routing ──
        if mode == "entry":
            worker.handle_entry_input(sender, t, session)
            return
        if mode == "edit":
            worker.handle_edit_input(sender, t, session)
            return
        if mode == "overwrite_confirm":
            worker.handle_overwrite_text(sender, t_lower, session)
            return
        if mode == "close_confirm":
            manager.handle_close_confirm_text(sender, t_lower)
            return

        # Manager modes
        if is_mgr and mode == "mgr_market_edit":
            manager.handle_mgr_edit_input(sender, t, session)
            return
        if is_mgr and mode == "mgr_edit_overwrite":
            manager.handle_mgr_edit_overwrite_text(sender, t_lower, session)
            return

        # ── Greeting ──
        if any(w in t_lower for w in ("hi", "hello", "menu", "start", "help")):
            if is_mgr:
                manager.send_manager_menu(sender)
            else:
                worker.route_on_greeting(sender, session)
            return

        # ── Direct market code: "M3" ──
        if re.match(r"^m\d{1,2}$", t_lower):
            mid = t_lower.upper()
            if is_mgr:
                manager.send_market_review(sender, mid)
            else:
                worker.send_market_detail(sender, mid)
            return

        # ── Manager: numeric product selection in product summary ──
        if is_mgr and mode == "mgr_product_select" and t.isdigit():
            idx = int(t) - 1
            if 0 <= idx < len(SESSIONS):  # bounds checked inside send_product_summary
                manager.send_product_summary(sender, idx)
                return

        if is_mgr:
            manager.send_manager_menu(sender)
        else:
            worker.send_worker_menu(sender)

    except Exception as exc:
        print(f"❌ handle_message ERROR: {exc}")
        send_text(sender, "⚠️ Something went wrong. Send *hi* to restart.")


def handle_interactive(sender: str, button_id: str):
    """Route button / list-row taps."""
    try:
        session = SESSIONS.get(sender, {})
        is_mgr  = sender in MANAGER_NUMBERS

        # ── Shared navigation ──
        if button_id == "menu":
            manager.send_manager_menu(sender) if is_mgr else worker.send_worker_menu(sender)
            return
        if button_id == "all_markets":
            worker.send_all_markets_list(sender)
            return
        if button_id in ("day_monday", "day_wednesday", "day_friday"):
            day_map = {"day_monday": "Monday", "day_wednesday": "Wednesday",
                       "day_friday": "Friday"}
            worker.send_day_list(sender, day_map[button_id])
            return

        # ─────────────────────────────────────────────────────────────────
        #  MANAGER BUTTONS
        # ─────────────────────────────────────────────────────────────────
        if is_mgr:
            if button_id == "mgr_dashboard":
                manager.send_dashboard(sender)
            elif button_id == "mgr_market_status":
                manager.send_market_status(sender)
            elif button_id == "mgr_sales_summary":
                manager.send_sales_summary(sender)
            elif button_id == "mgr_product_summary":
                manager.launch_product_summary(sender)
            elif button_id == "mgr_close_week":
                manager.handle_close_week_request(sender)
            elif button_id.startswith("mgr_view_market_"):
                mid = button_id.replace("mgr_view_market_", "").upper()
                manager.send_market_review(sender, mid)
            elif button_id.startswith("mgr_edit_market_"):
                mid = button_id.replace("mgr_edit_market_", "").upper()
                manager.start_market_edit(sender, mid)
            elif button_id.startswith("mgr_product_edit_"):
                idx = int(button_id.replace("mgr_product_edit_", ""))
                manager.ask_edit_product(sender, session, idx)
            elif button_id.startswith("mgr_product_"):
                idx = int(button_id.replace("mgr_product_", ""))
                manager.send_product_summary(sender, idx)
            elif button_id == "close_confirm_yes":
                manager.do_close_week(sender)
            elif button_id == "close_confirm_no":
                SESSIONS.pop(sender, None)
                send_text(sender, "✅ Week close cancelled.")
                manager.send_manager_menu(sender)
            elif button_id == "mgr_edit_overwrite_yes":
                manager.do_mgr_edit_overwrite(sender, session)
            elif button_id == "mgr_edit_overwrite_no":
                manager.cancel_mgr_edit_overwrite(sender, session)
            else:
                manager.send_manager_menu(sender)
            return

        # ─────────────────────────────────────────────────────────────────
        #  WORKER BUTTONS
        # ─────────────────────────────────────────────────────────────────
        if button_id.startswith("market_"):
            worker.send_market_detail(sender, button_id.replace("market_", "").upper())
        elif button_id == "enter_sales":
            worker.start_fresh_entry(sender, session)
        elif button_id == "resume_entry":
            worker.resume_entry(sender, session)
        elif button_id == "cancel_entry":
            worker.pause_entry(sender, session)
        elif button_id == "overwrite_yes":
            worker.do_overwrite(sender, session)
        elif button_id == "overwrite_no":
            worker.keep_existing(sender, session)
        elif button_id == "finish_market":
            worker.complete_market(sender, session)
        elif button_id.startswith("edit_product_"):
            idx = int(button_id.replace("edit_product_", ""))
            worker.start_edit_product(sender, session, idx)
        elif button_id == "close_confirm_yes":
            manager.do_close_week(sender)
        elif button_id == "close_confirm_no":
            SESSIONS.pop(sender, None)
            send_text(sender, "✅ Week close cancelled.")
        else:
            worker.send_worker_menu(sender)

    except Exception as exc:
        print(f"❌ handle_interactive ERROR: {exc}")
        send_text(sender, "⚠️ Something went wrong. Send *hi* to restart.")