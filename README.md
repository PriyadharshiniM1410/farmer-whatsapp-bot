# Farmer WhatsApp Bot

## Project Structure

```text
farmer-whatsapp-bot/
│
├── app/
│   ├── __init__.py
│   ├── bot_logic.py
│   ├── manager.py
│   ├── shared.py
│   ├── sheets.py
│   ├── webhook.py
│   ├── whatsapp.py
│   └── worker.py
│
├── config.py
├── run.py
├── requirements.txt
├── .env
├── credentials.json
└── README.md
```

## Prerequisites

* Python 3.10 or above
* WhatsApp Cloud API account
* Meta Developer Account
* Google Cloud Service Account
* Google Sheets access

## Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd farmer-whatsapp-bot
```

### 2. Create Virtual Environment

```bash
python -m venv venv
```

Activate:

Windows

```bash
venv\Scripts\activate
```

Linux/Mac

```bash
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

## Environment Variables

Create a `.env` file in the project root and add the required values.

Example:

```env
VERIFY_TOKEN=your_verify_token
WHATSAPP_TOKEN=your_whatsapp_token
PHONE_NUMBER_ID=your_phone_number_id
SPREADSHEET_ID=your_google_sheet_id
```

## Google Credentials

Place the Google Service Account file as:

```text
credentials.json
```

in the project root directory.


## Running the Application

Start the application:

```bash
python run.py
```

