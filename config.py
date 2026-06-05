import os
from dotenv import load_dotenv

load_dotenv(".env")


WHATSAPP_TOKEN   = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")
VERIFY_TOKEN     = os.getenv("VERIFY_TOKEN")
SHEET_ID         = os.getenv("SHEET_ID")
CREDS_FILE       = "credentials.json"

print("VERIFY_TOKEN LOADED:", VERIFY_TOKEN)