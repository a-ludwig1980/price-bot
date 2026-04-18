"""
Speichert den zuletzt gesehenen Preis persistent in price_state.json.
Wird genutzt um Aenderungen zu erkennen ('ALERT_ON_CHANGE').
"""
import json
import logging
from datetime import datetime

from config import STATE_FILE

log = logging.getLogger("state")


def read() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning(f"State nicht lesbar ({e}) - starte neu.")
        return {}


def write(data: dict) -> None:
    try:
        STATE_FILE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as e:
        log.warning(f"State nicht schreibbar: {e}")


def update_price(new_price: str) -> tuple[bool, str | None]:
    """
    Speichert den neuen Preis. Rueckgabe:
      (changed, old_price)
    """
    data = read()
    old = data.get("price")
    changed = old is not None and old != new_price
    data["price"] = new_price
    data["updated_at"] = datetime.now().isoformat(timespec="seconds")
    write(data)
    return changed, old
