"""Descobre o seu TELEGRAM_CHAT_ID.

1. Crie um bot no @BotFather e copie o token.
2. Mande qualquer mensagem (/start) para o seu bot.
3. Rode:  TELEGRAM_BOT_TOKEN=xxx python scripts/get_chat_id.py
"""
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()
token = os.environ.get("TELEGRAM_BOT_TOKEN") or sys.exit("defina TELEGRAM_BOT_TOKEN")

r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=20)
r.raise_for_status()
updates = r.json().get("result", [])
if not updates:
    sys.exit("Nenhuma mensagem. Mande /start pro bot e rode de novo.")

for u in updates:
    msg = u.get("message") or u.get("edited_message") or {}
    chat = msg.get("chat", {})
    if chat:
        print(f"chat_id={chat['id']}  ({chat.get('first_name') or chat.get('title')})")
