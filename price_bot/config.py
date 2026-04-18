"""
Zentrale Konfiguration fuer den Nintendo Preis-Monitor.

Pflicht: .env Datei (siehe .env.example). Keine hardcodierten Tokens.
"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except Exception:
    pass


# --- Telegram -------------------------------------------------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


# --- Ziel-URL und Produktbezeichnung --------------------------------------
PRODUCT_URL = os.getenv(
    "PRODUCT_URL",
    "https://www.nintendo.com/de-de/Spiele/Nintendo-Switch-Download-Software/"
    "Marvel-s-Guardians-of-the-Galaxy-Cloud-Version-1987417.html",
)
PRODUCT_NAME = os.getenv(
    "PRODUCT_NAME",
    "Marvel's Guardians of the Galaxy (Cloud Version)",
)

# Nintendo NSUID. Optional: wenn gesetzt, wird die Produktseite nicht
# mehr geladen, wir fragen direkt die Preis-API an.
# Fuer Marvel's GotG Cloud Version DE: 70010000042763
NSUID = os.getenv("NSUID", "70010000042763")


# --- Schedule -------------------------------------------------------------
# Uhrzeiten zu denen taeglich eine 'Standard'-Nachricht kommt.
# Format: komma-separiert, entweder volle Stunden ('6') oder HH:MM ('19:30').
# ENV-Variable: SCHEDULE_TIMES="06:00,12:00,19:30"
# Aliasname SCHEDULE_HOURS wird als Fallback gelesen (Backcompat).
_raw = os.getenv("SCHEDULE_TIMES") or os.getenv("SCHEDULE_HOURS", "6,12,18")


def _parse_schedule(raw: str) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            if ":" in token:
                h_s, m_s = token.split(":", 1)
                h, m = int(h_s), int(m_s)
            else:
                h, m = int(token), 0
            if 0 <= h <= 23 and 0 <= m <= 59:
                out.append((h, m))
        except Exception:
            continue
    return sorted(set(out))


SCHEDULE_TIMES: list[tuple[int, int]] = _parse_schedule(_raw) or [(6, 0), (12, 0), (18, 0)]

# Wie oft der Preis im Hintergrund geprueft wird (Minuten).
CHECK_INTERVAL_MIN = int(os.getenv("CHECK_INTERVAL_MIN", "15"))


# --- HTTP -----------------------------------------------------------------
REQUEST_TIMEOUT = 20  # Sekunden
MAX_RETRIES = 3
USER_AGENT = os.getenv(
    "USER_AGENT",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36",
)


# --- Pfade ----------------------------------------------------------------
BASE_DIR = Path(__file__).parent
STATE_FILE = BASE_DIR / "price_state.json"


# --- Preis-Alarme ---------------------------------------------------------
# 1) Preisaenderungs-Alarm zwischen zwei Checks.
ALERT_ON_CHANGE = os.getenv("ALERT_ON_CHANGE", "true").lower() in ("1", "true", "yes")

# 2) Low-Price-Alarm: wenn der Preis UNTER dieser Schwelle faellt, werden
#    N (ALARM_BURST_COUNT) Nachrichten kurz hintereinander gesendet.
#    Solange der Preis unter der Schwelle bleibt, wird der Burst nicht
#    wiederholt. Wenn der Preis wieder drueber geht und spaeter wieder
#    drunter, wird erneut gefeuert.
LOW_PRICE_THRESHOLD = float(os.getenv("LOW_PRICE_THRESHOLD", "50.0"))
ALARM_BURST_COUNT = int(os.getenv("ALARM_BURST_COUNT", "3"))


def validate() -> list[str]:
    errs = []
    if not TELEGRAM_TOKEN:
        errs.append("TELEGRAM_TOKEN fehlt (.env)")
    if not TELEGRAM_CHAT_ID:
        errs.append("TELEGRAM_CHAT_ID fehlt (.env)")
    if not PRODUCT_URL:
        errs.append("PRODUCT_URL fehlt")
    if not SCHEDULE_TIMES:
        errs.append("SCHEDULE_TIMES leer")
    return errs
