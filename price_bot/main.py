"""
Nintendo Preis-Monitor.

Verhalten:
  - Alle CHECK_INTERVAL_MIN Minuten (Default 15) wird der Preis geprueft.
  - Beim Start sofort eine Nachricht mit dem aktuellen Preis senden.
  - Zu den SCHEDULE_HOURS (Default 06, 12, 18 Uhr) taeglich eine Standard-
    Nachricht senden. Die Tageswechsel werden korrekt erkannt, ein
    Zeitpunkt pro Tag wird genau einmal gefeuert.
  - Wenn der Preis <= LOW_PRICE_THRESHOLD faellt, werden ALARM_BURST_COUNT
    Nachrichten kurz hintereinander gesendet. Solange der Preis drunter
    bleibt, wird der Alarm nicht wiederholt.
  - Bei Preisaenderungen zwischen zwei Checks wird (falls ALERT_ON_CHANGE)
    ebenfalls sofort eine Nachricht gesendet.

Usage:
  python main.py
  python main.py --once
"""
from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from config import (
    BASE_DIR,
    PRODUCT_NAME,
    PRODUCT_URL,
    SCHEDULE_TIMES,
    CHECK_INTERVAL_MIN,
    ALERT_ON_CHANGE,
    LOW_PRICE_THRESHOLD,
    ALARM_BURST_COUNT,
    validate,
)
from price_fetcher import fetch_price, PriceInfo
from state import read, write
from notifier import send as notify


# ---- Logging -------------------------------------------------------------
# stdout unbuffered: Log-Zeilen erscheinen SOFORT, nicht erst wenn der
# Prozess Puffer leert. Wichtig bei langlaufenden Daemons.
try:
    sys.stdout.reconfigure(line_buffering=True)  # Python 3.7+
except Exception:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("main")


# ---- Stop-Event ---------------------------------------------------------
# Event statt bool -> wait() kehrt SOFORT zurueck, wenn das Signal reinkommt,
# kein 30s-sleep-Blocker mehr.
_stop = threading.Event()


def _handle_signal(signum, frame):
    if _stop.is_set():
        log.warning("Zweites Signal -> hart beenden.")
        sys.exit(130)
    log.info(f"Signal {signum} -> beende ...")
    _stop.set()


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# ---- Helpers -------------------------------------------------------------
def _effective_price(price: PriceInfo) -> float:
    return price.discount_raw if price.is_discounted else price.raw_value


def _scheduled_push_due(state: dict) -> str | None:
    """
    Liefert den Push-Key (z.B. "19:30"), wenn JETZT eine geplante Push-Zeit
    erreicht ist und heute noch nicht gefeuert wurde. Sonst None.
    """
    now = datetime.now()
    today = now.date().isoformat()
    fired_today = set(state.get("fired_today", {}).get(today, []))
    for h, m in SCHEDULE_TIMES:
        scheduled = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if now >= scheduled:
            key = f"{h:02d}:{m:02d}"
            if key not in fired_today:
                return key
    return None


def _mark_scheduled_push(state: dict, key: str) -> None:
    today = datetime.now().date().isoformat()
    fired = state.setdefault("fired_today", {})
    # Alte Tage aufraeumen - wir brauchen nur heute
    fired = {today: fired.get(today, [])}
    if key not in fired[today]:
        fired[today].append(key)
    state["fired_today"] = fired


# ---- Nachrichten-Formatierung --------------------------------------------
def _format_regular_message(
    price: PriceInfo,
    trigger: str,
    changed: bool,
    old_value: str | None,
) -> str:
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    lines = [f"🎮 <b>{PRODUCT_NAME}</b>"]
    if price.is_discounted:
        lines.append(f"🔥 <b>{price.discount_amount}</b> (Aktion)")
        lines.append(f"   statt <s>{price.amount}</s>")
        if price.discount_end:
            lines.append(f"   gueltig bis {price.discount_end}")
    else:
        lines.append(f"💰 Preis: <b>{price.amount}</b>")
    lines.append(f"🕒 {now} ({trigger})")
    if changed and old_value:
        lines.append(f"⚠️ Preisaenderung: {old_value} → {price.display}")
    lines.append(f'\n<a href="{PRODUCT_URL}">Zur Nintendo-Seite</a>')
    return "\n".join(lines)


def _format_alarm_message(price: PriceInfo, i: int, n: int) -> tuple[str, str]:
    """Rueckgabe: (telegram_html, sms_plain)."""
    cur = price.display
    tg = (
        f"🚨 <b>PREISALARM ({i}/{n})</b>\n"
        f"{PRODUCT_NAME}\n"
        f"💥 <b>{cur}</b> (≤ {LOW_PRICE_THRESHOLD:.2f} €)\n"
        f'<a href="{PRODUCT_URL}">Jetzt im Nintendo eShop</a>'
    )
    # SMS: kurz und knackig (Single-Segment wenn moeglich)
    sms = (
        f"PREISALARM {i}/{n}: {PRODUCT_NAME} jetzt {cur} "
        f"(<={LOW_PRICE_THRESHOLD:.0f}€). {PRODUCT_URL}"
    )
    return tg, sms


def _send_alarm_burst(price: PriceInfo) -> None:
    n = max(1, ALARM_BURST_COUNT)
    log.info(f"LOW-PRICE ALARM -> sende {n} Nachrichten")
    for i in range(1, n + 1):
        tg, sms = _format_alarm_message(price, i, n)
        notify(
            tg,
            sms_message=sms,
            ntfy_title=f"PREISALARM ({i}/{n}) - {price.display}",
            ntfy_click_url=PRODUCT_URL,
            ntfy_priority=5,   # ntfy: max-Prio, umgeht Silent-Mode
            ntfy_tags=["rotating_light", "moneybag"],
        )
        if i < n:
            time.sleep(1.2)  # kurze Pause zwischen den Nachrichten


# ---- Ein Check -----------------------------------------------------------
def run_check(trigger: str, always_push: bool = False) -> None:
    """Preis holen, State aktualisieren, ggf. Telegram senden."""
    try:
        price = fetch_price()
    except Exception as e:
        log.error(f"Preis-Fetch fehlgeschlagen: {e}")
        # Fehler nur loggen - nicht bei jedem 15-Min-Check spammen.
        return

    state = read()
    old_value = state.get("price")
    new_value = price.display
    changed = (old_value is not None) and (old_value != new_value)

    # Snapshot fuer GitHub-Actions-Marker (s. Ende der Funktion)
    _today_key = datetime.now().date().isoformat()
    _fired_before = set(state.get("fired_today", {}).get(_today_key, []))
    _alarm_before = bool(state.get("low_price_alarm_sent", False))

    scheduled_key = _scheduled_push_due(state)
    # Aenderungs-Alarm NUR wenn der neue Preis auch unter der Schwelle liegt.
    # Sonst waere jede Zentcent-Aenderung eine Push-Nachricht.
    change_alert_due = (
        ALERT_ON_CHANGE
        and changed
        and _effective_price(price) <= LOW_PRICE_THRESHOLD
    )
    push_regular = (
        always_push
        or scheduled_key is not None
        or change_alert_due
    )
    if push_regular:
        reason = (
            f"Start" if always_push
            else scheduled_key if scheduled_key
            else f"{trigger} (Aenderung)"
        )
        log.info(f"PUSH -> reason={reason!r}")
        tg = _format_regular_message(price, reason, changed, old_value)
        short = (
            f"{PRODUCT_NAME}: {price.display}"
            + (f" (Aenderung von {old_value})" if changed and old_value else "")
            + f" - {PRODUCT_URL}"
        )
        notify(
            tg,
            sms_message=short,
            ntfy_title=f"{PRODUCT_NAME} - {price.display}",
            ntfy_click_url=PRODUCT_URL,
            ntfy_priority=4 if changed else 3,
            ntfy_tags=["video_game"],
        )
        if scheduled_key:
            _mark_scheduled_push(state, scheduled_key)

    # Low-price alarm
    effective = _effective_price(price)
    alarm_sent = bool(state.get("low_price_alarm_sent", False))
    if effective > 0 and effective <= LOW_PRICE_THRESHOLD:
        if not alarm_sent:
            _send_alarm_burst(price)
            state["low_price_alarm_sent"] = True
    else:
        # Preis wieder ueber Schwelle -> Flag zuruecksetzen fuer naechstes Mal
        if alarm_sent:
            log.info("Preis wieder ueber Schwelle - Alarm-Flag zurueckgesetzt")
        state["low_price_alarm_sent"] = False

    # Aktualisierten Preis ablegen
    state["price"] = new_value
    state["price_raw"] = price.raw_value
    state["discount_raw"] = price.discount_raw
    state["sales_status"] = price.sales_status
    state["updated_at"] = datetime.now().isoformat(timespec="seconds")
    write(state)

    # GitHub-Actions-Marker: erzeugt .state-dirty nur bei RELEVANTER Aenderung.
    # Der Workflow-Step committet und pusht price_state.json nur wenn dieser
    # Marker existiert. Dadurch werden nicht alle 15 Min unnoetige Commits
    # (nur updated_at aktualisiert) erzeugt.
    fired_after = set(state.get("fired_today", {}).get(_today_key, []))
    alarm_after = bool(state.get("low_price_alarm_sent", False))
    if (
        changed
        or scheduled_key
        or fired_after != _fired_before
        or alarm_after != _alarm_before
    ):
        try:
            (BASE_DIR / ".state-dirty").touch()
        except Exception as e:
            log.debug(f".state-dirty Marker konnte nicht geschrieben werden: {e}")


# ---- Main-Loop -----------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Nintendo Preis-Monitor")
    parser.add_argument("--once", action="store_true",
                        help="Einmaligen Check durchfuehren und beenden.")
    args = parser.parse_args()

    errs = validate()
    if errs:
        for e in errs:
            log.error(f"Config: {e}")
        log.error("Bitte .env anlegen und erneut starten.")
        sys.exit(1)

    log.info("===== Nintendo Preis-Monitor startet =====")
    log.info(f"Produkt         : {PRODUCT_NAME}")
    log.info(f"URL             : {PRODUCT_URL}")
    log.info(f"Check-Intervall : alle {CHECK_INTERVAL_MIN} Min")
    times_str = ", ".join(f"{h:02d}:{m:02d}" for h, m in SCHEDULE_TIMES)
    log.info(f"Standard-Pushes : {times_str}")
    log.info(f"Preis-Alarm     : <= {LOW_PRICE_THRESHOLD:.2f} € ({ALARM_BURST_COUNT}x)")
    log.info(f"Alarm bei Aender: {ALERT_ON_CHANGE}")

    # Beim Start: immer Nachricht senden - aber NUR im Daemon-Modus.
    # Im --once-Modus (GitHub Actions) ist jeder Run ein "Start" - das
    # wuerde alle 15 Minuten eine Nachricht erzeugen. Stattdessen greift
    # dort nur die Schedule-Logik (6/12/18 Uhr) plus Preis-Alarm.
    run_check(trigger="Start", always_push=not args.once)

    if args.once:
        log.info("--once gesetzt -> fertig.")
        return

    interval_s = max(60, CHECK_INTERVAL_MIN * 60)
    while not _stop.is_set():
        # wait() kehrt frueher zurueck, sobald das Event gesetzt wird (Ctrl+C)
        if _stop.wait(interval_s):
            break
        run_check(trigger="15min-check")

    log.info("===== Nintendo Preis-Monitor beendet =====")


if __name__ == "__main__":
    main()
