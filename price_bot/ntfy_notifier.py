"""
ntfy.sh Push-Nachrichten (KOSTENLOS, open source).

Funktionsweise:
  1. Auf dem Handy: App "ntfy" installieren (iOS/Android).
  2. In der App: auf '+' tippen, Topic-Namen eingeben (irgendwas Eindeutiges).
  3. In der .env: NTFY_TOPIC=<derselbe-name>
  4. Fertig. Jede Nachricht an https://ntfy.sh/<TOPIC> landet als
     Push-Benachrichtigung auf dem Handy.

Optional:
  NTFY_SERVER=https://ntfy.sh        (Default)
  NTFY_TOKEN=tk_...                  (nur wenn privater Server mit Auth)
  NTFY_PRIORITY=5                    (1-5; 5 = max, ignoriert Silent Mode)
"""
from __future__ import annotations

import logging
import os
import time

import requests

log = logging.getLogger("ntfy")

NTFY_SERVER = os.getenv("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "").strip()
NTFY_TOKEN = os.getenv("NTFY_TOKEN", "").strip()


def is_configured() -> bool:
    return bool(NTFY_TOPIC)


def send_ntfy(
    message: str,
    title: str | None = None,
    priority: int | None = None,
    click_url: str | None = None,
    tags: list[str] | None = None,
    max_retries: int = 3,
) -> bool:
    """
    Sendet eine Push-Nachricht an ntfy mit Retry bei transienten Fehlern.
    """
    if not is_configured():
        log.debug("ntfy nicht konfiguriert - skip.")
        return False
    url = f"{NTFY_SERVER}/{NTFY_TOPIC}"
    headers = {}
    if title:
        # Title-Header nimmt kein Non-ASCII - Fallback: Title in Body rendern.
        try:
            title.encode("ascii")
            headers["Title"] = title
        except UnicodeEncodeError:
            message = f"{title}\n{message}"
    if priority is not None:
        headers["Priority"] = str(priority)
    if click_url:
        headers["Click"] = click_url
    if tags:
        headers["Tags"] = ",".join(tags)
    if NTFY_TOKEN:
        headers["Authorization"] = f"Bearer {NTFY_TOKEN}"

    last_exc: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            r = requests.post(
                url,
                data=message.encode("utf-8"),
                headers=headers,
                timeout=15,
            )
            r.raise_for_status()
            log.info(f"ntfy gesendet (topic={NTFY_TOPIC}, attempt={attempt})")
            return True
        except Exception as e:
            last_exc = e
            log.warning(
                f"ntfy-Fehler (Versuch {attempt}/{max_retries}): {e}"
            )
            if attempt < max_retries:
                time.sleep(min(2 ** attempt, 10))
    log.error(f"ntfy endgueltig fehlgeschlagen: {last_exc}")
    return False
