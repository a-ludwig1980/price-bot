"""
SMS-Versand via Twilio (optional).

Konfiguration in .env:
  TWILIO_ACCOUNT_SID=AC...
  TWILIO_AUTH_TOKEN=...
  TWILIO_FROM=+491701234567     # verifizierte Twilio-Absender-Nummer
  SMS_TO=+491701234567          # Empfaenger (du selbst)

Wenn eine dieser Variablen leer ist, wird SMS uebersprungen - der Bot
laeuft dann nur mit Telegram. Keine Hardabhaengigkeit vom twilio-Paket:
wenn `pip install twilio` fehlt, wird ebenfalls uebersprungen.
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger("sms")

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM = os.getenv("TWILIO_FROM", "")
SMS_TO = os.getenv("SMS_TO", "")


def is_configured() -> bool:
    return bool(
        TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM and SMS_TO
    )


def _client():
    try:
        from twilio.rest import Client  # type: ignore
    except ImportError:
        log.warning("twilio-Paket nicht installiert - SMS uebersprungen.")
        return None
    try:
        return Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    except Exception as e:
        log.error(f"Twilio-Client fehlgeschlagen: {e}")
        return None


def send_sms(text: str) -> bool:
    if not is_configured():
        log.debug("SMS nicht konfiguriert - skip.")
        return False
    c = _client()
    if c is None:
        return False
    # SMS sind in Segmenten zu ~160 Zeichen abgerechnet - Text kuerzen
    # auf einen vernuenftigen Rahmen (4 Segmente = ~600 Zeichen).
    text = text.strip()[:600]
    try:
        msg = c.messages.create(body=text, from_=TWILIO_FROM, to=SMS_TO)
        log.info(f"SMS gesendet (sid={msg.sid})")
        return True
    except Exception as e:
        log.error(f"SMS-Fehler: {e}")
        return False
