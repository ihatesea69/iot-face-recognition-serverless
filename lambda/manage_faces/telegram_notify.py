"""Minimal Telegram Bot API client for Lambda notifications."""

from __future__ import annotations

import json
import os
from urllib import error, request


TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
TELEGRAM_API_BASE = "https://api.telegram.org"


def telegram_enabled() -> bool:
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)


def send_telegram_message(text: str) -> bool:
    """Send a plain-text Telegram message. Returns False when disabled or failed."""
    if not telegram_enabled():
        return False

    url = f"{TELEGRAM_API_BASE}/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = json.dumps(
        {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "disable_web_page_preview": False,
        }
    ).encode("utf-8")
    req = request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=10) as response:
            body = json.loads(response.read().decode("utf-8") or "{}")
            if not body.get("ok"):
                print(f"Telegram API rejected message: {body}")
                return False
            return True
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"Telegram HTTP error {exc.code}: {body}")
        return False
    except Exception as exc:  # pragma: no cover - defensive logging path
        print(f"Telegram send failed: {exc}")
        return False
