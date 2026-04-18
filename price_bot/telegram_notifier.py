"""Telegram-Benachrichtigung."""
import logging
import requests

from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, REQUEST_TIMEOUT

log = logging.getLogger("telegram")


def send_telegram(message: str) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Telegram nicht konfiguriert - Nachricht nicht gesendet.")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    try:
        r = requests.post(url, data=payload, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        log.info("Telegram gesendet.")
        return True
    except Exception as e:
        log.error(f"Telegram Fehler: {e}")
        return False
