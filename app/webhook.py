from pyexpat.errors import messages

from flask import Blueprint, request, jsonify
from config import VERIFY_TOKEN
from app.bot_logic import handle_message, handle_interactive

bp = Blueprint("webhook", __name__)

@bp.route("/webhook", methods=["GET"])
def verify():
    """WhatsApp webhook verification handshake."""
    if (request.args.get("hub.mode") == "subscribe" and
            request.args.get("hub.verify_token") == VERIFY_TOKEN):
        return request.args.get("hub.challenge"), 200
    return "Forbidden", 403

@bp.route("/webhook", methods=["POST"])
def receive():
    data = request.get_json()
    print("🔥 FULL PAYLOAD:", data)

    try:
        entry = data.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0]
        value = changes.get("value", {})

        messages = value.get("messages", [])

        for msg in messages:

            print("================================")
            print("MSG ID :", msg.get("id"))
            print("TYPE   :", msg.get("type"))
            print("FROM   :", msg.get("from"))
            print("MSG    :", msg)
            print("================================")

            sender = msg.get("from")
            msg_type = msg.get("type")

            if msg_type == "text":
                text = msg.get("text", {}).get("body", "")
                handle_message(sender, text)

            elif msg_type == "interactive":
                itype = msg.get("interactive", {}).get("type")

                if itype == "button_reply":
                    handle_interactive(
                        sender,
                        msg["interactive"]["button_reply"]["id"]
                    )

                elif itype == "list_reply":
                    handle_interactive(
                        sender,
                        msg["interactive"]["list_reply"]["id"]
                    )

    except Exception as e:
        print("❌ WEBHOOK ERROR:", e)

    return jsonify({"status": "ok"}), 200