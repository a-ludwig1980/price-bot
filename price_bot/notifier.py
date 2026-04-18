"""
Unified Notifier: sendet eine Nachricht parallel an alle konfigurierten Kanaele.

Unterstuetzt:
  - Telegram (HTML formatiert)         - Pflicht
  - ntfy.sh (Push, KOSTENLOS)          - optional via NTFY_TOPIC
  - SMS via Twilio                     - optional via TWILIO_* Variablen

Nichtaktive Kanaele werden still uebersprungen.
"""
from __future__ import annotations

import logging
import re

from telegram_notifier import send_telegram
from sms_notifier import send_sms, is_configured as sms_is_configured
from ntfy_notifier import send_ntfy, is_configured as ntfy_is_configured

log = logging.getLogger("notify")


_TAG_RX = re.compile(r"<[^>]+>")
_ENTITY_RX = {
    "&nbsp;": " ",
    "&amp;": "&",
    "&lt;": "<",
    "&gt;": ">",
    "&quot;": '"',
}


def html_to_plain(html: str) -> str:
    t = _TAG_RX.sub("", html or "")
    for k, v in _ENTITY_RX.items():
        t = t.replace(k, v)
    lines = [ln.strip() for ln in t.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def send(
    html_message: str,
    sms_message: str | None = None,
    ntfy_title: str | None = None,
    ntfy_click_url: str | None = None,
    ntfy_priority: int = 3,
    ntfy_tags: list[str] | None = None,
) -> None:
    """
    Sendet an alle aktiven Kanaele:
      - Telegram: HTML
      - SMS: plain (aus html_message abgeleitet wenn sms_message=None)
      - ntfy: plain + optional Titel / Click-URL / Priority / Tags
    """
    # 1) Telegram (HTML) - Pflicht
    tg_ok = False
    try:
        tg_ok = send_telegram(html_message)
    except Exception as e:
        log.error(f"Telegram-Versand fehlgeschlagen: {e}")

    plain = sms_message if sms_message is not None else html_to_plain(html_message)

    failures: list[str] = []

    # 2) ntfy (Push, kostenlos)
    if ntfy_is_configured():
        ok = False
        try:
            ok = send_ntfy(
                plain,
                title=ntfy_title,
                priority=ntfy_priority,
                click_url=ntfy_click_url,
                tags=ntfy_tags,
            )
        except Exception as e:
            log.error(f"ntfy-Versand fehlgeschlagen: {e}")
        if not ok:
            failures.append("ntfy")

    # 3) SMS (Twilio)
    if sms_is_configured():
        ok = False
        try:
            ok = send_sms(plain)
        except Exception as e:
            log.error(f"SMS-Versand fehlgeschlagen: {e}")
        if not ok:
            failures.append("SMS")

    # Wenn mindestens ein Zusatzkanal gescheitert ist: Warnung via Telegram.
    if tg_ok and failures:
        try:
            send_telegram(
                f"⚠️ Zusatzkanal(e) fehlgeschlagen: {', '.join(failures)}"
            )
        except Exception:
            pass
