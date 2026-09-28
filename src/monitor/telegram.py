from __future__ import annotations

import os

import requests

API = "https://api.telegram.org/bot{token}/{method}"


class TelegramClient:
    """Cliente fino da Bot API — sem lógica de negócio."""

    def __init__(self, token: str | None = None, chat_id: str | None = None) -> None:
        self.token = token or os.environ["TELEGRAM_BOT_TOKEN"]
        self.chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")

    def send_message(self, text: str, chat_id: str | int | None = None) -> None:
        resp = requests.post(
            API.format(token=self.token, method="sendMessage"),
            json={
                "chat_id": chat_id or self.chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            },
            timeout=20,
        )
        resp.raise_for_status()

    def get_updates(self, offset: int | None = None, timeout: int = 0) -> list[dict]:
        params: dict[str, int] = {"timeout": timeout}
        if offset is not None:
            params["offset"] = offset
        resp = requests.get(
            API.format(token=self.token, method="getUpdates"),
            params=params,
            timeout=timeout + 20,
        )
        resp.raise_for_status()
        return resp.json().get("result", [])

    def set_webhook(self, url: str, secret_token: str) -> dict:
        """Aponta o Telegram pra mandar updates via POST em `url` em vez de
        depender de getUpdates. `secret_token` vem de volta no header
        X-Telegram-Bot-Api-Secret-Token de cada POST — é isso que autentica
        o webhook (ver server.py)."""
        resp = requests.post(
            API.format(token=self.token, method="setWebhook"),
            json={
                "url": url,
                "secret_token": secret_token,
                "allowed_updates": ["message", "edited_message"],
            },
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()

    def delete_webhook(self) -> dict:
        """Desliga o webhook e libera getUpdates de novo (polling local)."""
        resp = requests.post(API.format(token=self.token, method="deleteWebhook"), timeout=20)
        resp.raise_for_status()
        return resp.json()

    def get_webhook_info(self) -> dict:
        resp = requests.get(API.format(token=self.token, method="getWebhookInfo"), timeout=20)
        resp.raise_for_status()
        return resp.json().get("result", {})
