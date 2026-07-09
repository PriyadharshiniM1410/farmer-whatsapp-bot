import requests
from config import WHATSAPP_TOKEN, WHATSAPP_PHONE_ID

BASE_URL = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_ID}/messages"
HEADERS  = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}

MAX_LIST_ROWS = 10  # WhatsApp's hard limit on interactive list rows per message


def send_text(to: str, text: str):
    payload = {"messaging_product": "whatsapp", "to": to,
               "type": "text", "text": {"body": text}}
    r = requests.post(BASE_URL, json=payload, headers=HEADERS)
    print("SEND STATUS:", r.status_code)
    print("SEND RESPONSE:", r.text)

def send_buttons(to: str, body: str, buttons: list):
    payload = {
        "messaging_product": "whatsapp", "to": to, "type": "interactive",
        "interactive": {
            "type": "button", "body": {"text": body},
            "action": {"buttons": [
                {"type": "reply", "reply": {"id": b["id"], "title": b["title"]}}
                for b in buttons[:3]
            ]}
        }
    }
    r = requests.post(BASE_URL, json=payload, headers=HEADERS)
    print("SEND STATUS:", r.status_code)
    print("SEND RESPONSE:", r.text)


def _send_list_single(to: str, body: str, button_label: str, sections: list):
    """Fire a single WhatsApp interactive list message (assumes <= MAX_LIST_ROWS total rows)."""
    payload = {
        "messaging_product": "whatsapp", "to": to, "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": body},
            "action": {
                "button": button_label,
                "sections": sections
            }
        }
    }
    r = requests.post(BASE_URL, json=payload, headers=HEADERS)
    print("SEND STATUS:", r.status_code)
    print("SEND RESPONSE:", r.text)


def _chunk_sections(sections: list, max_rows: int) -> list:
    """Split sections into batches so each batch has at most `max_rows` rows total.
    Keeps a section together when it fits; splits a section across batches only
    if the section itself is bigger than max_rows."""
    batches = []
    current_batch: list = []
    current_count = 0

    for section in sections:
        rows = section.get("rows", [])

        # Section fits fully in the current batch.
        if current_count + len(rows) <= max_rows:
            current_batch.append(section)
            current_count += len(rows)
            continue

        # Doesn't fit — close out the current batch first (if it has anything).
        if current_batch:
            batches.append(current_batch)
            current_batch = []
            current_count = 0

        # Section itself is small enough to start a fresh batch with.
        if len(rows) <= max_rows:
            current_batch = [section]
            current_count = len(rows)
        else:
            # Section alone is bigger than max_rows — split its rows up.
            title = section.get("title", "")
            for i in range(0, len(rows), max_rows):
                batches.append([{"title": title, "rows": rows[i:i + max_rows]}])

    if current_batch:
        batches.append(current_batch)

    return batches


def send_list(to: str, body: str, button_label: str, sections: list):
    """
    sections = [
      { "title": "Monday", "rows": [{"id":"market_M1","title":"M1","description":"Monday"}] }
    ]
    WhatsApp allows a MAX of 10 rows total across all sections in one list message.
    If the caller passes more than that, this automatically splits it into
    multiple list messages (Part 1/2, Part 2/2, ...) instead of failing silently.
    """
    total_rows = sum(len(s.get("rows", [])) for s in sections)

    if total_rows <= MAX_LIST_ROWS:
        _send_list_single(to, body, button_label, sections)
        return

    batches = _chunk_sections(sections, MAX_LIST_ROWS)
    total_parts = len(batches)
    for i, batch in enumerate(batches, start=1):
        part_body = f"{body}\n_(Part {i}/{total_parts})_"
        _send_list_single(to, part_body, button_label, batch)