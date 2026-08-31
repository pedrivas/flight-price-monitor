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
