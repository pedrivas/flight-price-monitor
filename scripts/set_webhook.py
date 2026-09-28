"""Liga/desliga o webhook do Telegram, ou mostra o status atual.

Uso (lê TELEGRAM_BOT_TOKEN, WEBHOOK_URL e TELEGRAM_WEBHOOK_SECRET do .env):

    python scripts/set_webhook.py set       # aponta o Telegram pro webhook
    python scripts/set_webhook.py delete    # volta pro polling (getUpdates)
    python scripts/set_webhook.py info      # getWebhookInfo cru
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dotenv import load_dotenv  # noqa: E402

from monitor.telegram import TelegramClient  # noqa: E402


def main() -> None:
    load_dotenv()
    if len(sys.argv) != 2 or sys.argv[1] not in ("set", "delete", "info"):
        sys.exit(__doc__)
    action = sys.argv[1]
    client = TelegramClient()

    if action == "info":
        print(json.dumps(client.get_webhook_info(), indent=2, ensure_ascii=False))
        return

    if action == "delete":
        client.delete_webhook()
        print("webhook removido — voltou pro modo polling")
        return

    import os

    url = os.environ.get("WEBHOOK_URL") or sys.exit("defina WEBHOOK_URL no .env (ex: https://167-234-239-28.sslip.io/webhook/flight-tg)")
    secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET") or sys.exit("defina TELEGRAM_WEBHOOK_SECRET no .env")
    client.set_webhook(url, secret)
    print(f"webhook ativo: {url}")
    print(json.dumps(client.get_webhook_info(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
