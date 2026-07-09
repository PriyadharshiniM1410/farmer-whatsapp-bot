"""
bot_logic.py — Entry point: routes messages to worker or manager modules.

Imports all business logic from:
  app/shared.py   — SESSIONS, constants, sheet helpers
  app/worker.py   — Worker workflow
  app/manager.py  — Manager workflow
"""

import re
from app.shared import SESSIONS, is_manager
from app.sheets import get_products, get_product_emoji
from app.whatsapp import send_text
import app.worker as worker
import app.manager as manager


def handle_message(sender: str, text: str):
    """Route plain-text messages based on role + session mode."""
    try:
        t       = text.strip()
        t_lower = t.lower()
        session = SESSIONS.get(sender, {})
        mode    = session.get("mode", "idle")
        is_mgr  = is_manager(sender)

        if mode == "waiting_for_sold_qty":
            market_id = session.get("current_market")
            prod_idx  = session.get("current_prod_idx")

            products = get_products()
            if not (0 <= prod_idx < len(products)):
                send_text(sender, "⚠️ Something went wrong. Send *hi* to restart.")
                session["mode"] = "idle"
                return
            p_name = products[prod_idx]

            if t.isdigit():
                sold_val = int(t)

                all_data  = worker.get_all_sheet_data()
                allocs    = worker.get_market_allocations(market_id, all_data)
                allocated = allocs.get(p_name, 0)

                if sold_val > allocated:
                    send_text(sender,
                        f"⚠️ *{p_name}* — you entered *{sold_val}*, but only "
                        f"*{allocated:.0f} boxes* were allocated to {market_id}.\n"
                        f"Please enter a number between 0 and {allocated:.0f}."
                    )
                    return

                worker.update_sheet_sold_qty(market_id, p_name, sold_val)
                send_text(sender, f"✅ *{p_name}* → *{sold_val} boxes* saved successfully!")
                session["mode"] = "idle"
                worker.send_product_manifest_dashboard(sender, market_id)
            else:
                send_text(sender, "⚠️ Invalid input. Please reply with a valid number only.")
            return

        if is_mgr and mode == "mgr_market_edit":
            manager.handle_mgr_edit_input(sender, t, session)
            return
        if is_mgr and mode == "mgr_edit_overwrite":
            manager.handle_mgr_edit_overwrite_text(sender, t_lower, session)
            return

        if any(w in t_lower for w in ("hi", "hello", "menu", "start", "help")):
            if is_mgr:
                manager.send_manager_menu(sender)
            else:
                worker.route_on_greeting(sender, session)
            return

        if re.match(r"^m\d{1,2}$", t_lower):
            mid = t_lower.upper()
            if is_mgr:
                manager.send_market_review(sender, mid)
            else:
                worker.send_product_manifest_dashboard(sender, mid)
            return

        if is_mgr and mode == "mgr_product_select" and t.isdigit():
            idx = int(t) - 1
            if 0 <= idx < len(SESSIONS):
                manager.send_product_summary(sender, idx)
                return

        if is_mgr:
            manager.send_manager_menu(sender)
        else:
            worker.route_on_greeting(sender, session)

    except Exception as exc:
        print(f"❌ handle_message ERROR: {exc}")
        send_text(sender, "⚠️ Something went wrong. Send *hi* to restart.")


def handle_interactive(sender: str, button_id: str):
    """Intercept clicks from WhatsApp buttons and list popup rows."""
    try:
        session = SESSIONS.get(sender, {})
        is_mgr  = is_manager(sender)

        if button_id == "menu":
            if is_mgr:
                manager.send_manager_menu(sender)
            else:
                worker.route_on_greeting(sender, session)
            return

        if button_id.startswith("view_realloc_"):
            mid = button_id.replace("view_realloc_", "").upper()
            worker.send_allocation_view(sender, mid)
            return

        if button_id.startswith("ep_"):
            parts     = button_id.split("_")
            market_id = parts[1]
            prod_idx  = int(parts[2])

            products = get_products()
            if not (0 <= prod_idx < len(products)):
                send_text(sender, "⚠️ Something went wrong. Send *hi* to restart.")
                return
            p_name  = products[prod_idx]
            p_emoji = get_product_emoji(p_name)

            all_data    = worker.get_all_sheet_data()
            allocs      = worker.get_market_allocations(market_id, all_data)
            sold_data   = worker.get_sold_data(market_id, all_data)

            allocated    = allocs.get(p_name, 0)
            current_sold = sold_data.get(p_name)
            sold_str     = f"{int(float(current_sold))}" if current_sold is not None and current_sold != "" else "None"

            SESSIONS[sender] = {
                "mode":            "waiting_for_sold_qty",
                "current_market":  market_id,
                "current_prod_idx": prod_idx,
                "worker":          session.get("worker"),
                "name":            session.get("name"),
            }

            send_text(sender,
                f"{p_emoji} *{p_name} — Data Entry*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"Market    : *{market_id}*\n"
                f"Allocated : {allocated:.0f} boxes\n"
                f"Current   : {sold_str} boxes\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📝 Reply with the total boxes sold (0 to {allocated:.0f}):"
            )
            return

        if is_mgr:
            if button_id == "mgr_dashboard":
                manager.send_dashboard(sender)
            elif button_id == "mgr_market_status":
                manager.send_market_status(sender)
            elif button_id == "mgr_sales_summary":
                manager.send_sales_summary(sender)
            elif button_id == "mgr_product_summary":
                manager.launch_product_summary(sender)
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
            elif button_id == "mgr_edit_overwrite_yes":
                manager.do_mgr_edit_overwrite(sender, session)
            elif button_id == "mgr_edit_overwrite_no":
                manager.cancel_mgr_edit_overwrite(sender, session)
            else:
                manager.send_manager_menu(sender)
            return

        if button_id.startswith("market_"):
            mid = button_id.replace("market_", "").upper()
            worker.send_product_manifest_dashboard(sender, mid)
            return
        elif button_id == "finish_market":
            worker.complete_market(sender, session)
        elif button_id.startswith("submit_lock_"):
            worker.complete_market(sender, session)
        else:
            worker.route_on_greeting(sender, session)

    except Exception as exc:
        print(f"❌ handle_interactive ERROR: {exc}")
        send_text(sender, "⚠️ Something went wrong. Send *hi* to restart.")