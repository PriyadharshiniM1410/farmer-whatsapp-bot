import requests
from config import WHATSAPP_TOKEN, WHATSAPP_PHONE_ID

BASE_URL = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_ID}/messages"
HEADERS  = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}

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

def send_list(to: str, body: str, button_label: str, sections: list):
    """
    sections = [
      { "title": "Monday", "rows": [{"id":"market_M1","title":"M1","description":"Monday"}] }
    ]
    Max 10 rows total across all sections.
    """
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