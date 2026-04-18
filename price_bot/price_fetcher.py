"""
Preis-Abfrage fuer Nintendo-DE-Produktseiten.

Strategie:
  1. NSUID (Nintendo-System-UID) ermitteln:
       - aus config.NSUID (env NSUID), falls gesetzt
       - sonst: HTML der Produktseite holen und NSUID rauslesen
  2. Offizielle Preis-API aufrufen:
       GET https://api.ec.nintendo.com/v1/price?country=DE&lang=de&ids=<NSUID>
     Liefert JSON mit regular_price und (bei Aktionen) discount_price.

Die API ist derselbe Endpoint, den die Nintendo-Seite selbst per JavaScript
anspricht -> keine Scraping-Heuristik noetig, Preis ist strukturiert.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass

import requests

from config import (
    PRODUCT_URL,
    REQUEST_TIMEOUT,
    MAX_RETRIES,
    USER_AGENT,
)
try:
    from config import NSUID  # optional
except ImportError:
    NSUID = ""

log = logging.getLogger("price")

API_URL = "https://api.ec.nintendo.com/v1/price"
API_COUNTRY = "DE"
API_LANG = "de"


@dataclass
class PriceInfo:
    amount: str                    # "69,99 €"
    raw_value: float               # 69.99
    currency: str                  # "EUR"
    sales_status: str              # "onsale" / "not_yet_for_sale" / ...
    discount_amount: str | None    # z.B. "49,99 €" wenn Aktion
    discount_raw: float | None     # z.B. 49.99
    discount_end: str | None       # ISO-Datum oder None

    @property
    def is_discounted(self) -> bool:
        return self.discount_amount is not None

    @property
    def display(self) -> str:
        if self.is_discounted:
            return f"{self.discount_amount} (Aktion, statt {self.amount})"
        return self.amount


# -------------------------------------------------------------------------
# HTTP helpers
# -------------------------------------------------------------------------
def _http_get(url: str, **kwargs) -> requests.Response:
    last_exc: Exception | None = None
    headers = kwargs.pop("headers", {})
    headers.setdefault("User-Agent", USER_AGENT)
    headers.setdefault("Accept-Language", "de-DE,de;q=0.9,en;q=0.8")
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT, **kwargs)
            r.raise_for_status()
            return r
        except Exception as e:
            last_exc = e
            log.warning(f"HTTP-Fehler (Versuch {attempt}/{MAX_RETRIES}): {e}")
            time.sleep(min(2 ** attempt, 10))
    raise RuntimeError(f"GET {url} fehlgeschlagen: {last_exc}")


# -------------------------------------------------------------------------
# NSUID-Ermittlung
# -------------------------------------------------------------------------
_NSUID_RX = re.compile(
    r'nsuid["\']?\s*[:=]\s*["\']?(\d{10,})',
    re.I,
)


def _nsuid_from_html() -> str:
    log.info(f"Hole NSUID aus {PRODUCT_URL}")
    r = _http_get(PRODUCT_URL)
    m = _NSUID_RX.search(r.text)
    if not m:
        raise RuntimeError("NSUID nicht in der Produktseite gefunden")
    nsuid = m.group(1)
    log.info(f"NSUID: {nsuid}")
    return nsuid


def _get_nsuid() -> str:
    if NSUID:
        return str(NSUID).strip()
    return _nsuid_from_html()


# -------------------------------------------------------------------------
# Preis-API
# -------------------------------------------------------------------------
def _fetch_api_price(nsuid: str) -> PriceInfo:
    log.info(f"Preis-API fuer NSUID {nsuid}")
    r = _http_get(
        API_URL,
        params={"country": API_COUNTRY, "lang": API_LANG, "ids": nsuid},
    )
    data = r.json()
    prices = data.get("prices") or []
    if not prices:
        raise RuntimeError(f"Preis-API lieferte keine Eintraege: {data}")
    entry = prices[0]

    reg = entry.get("regular_price") or {}
    disc = entry.get("discount_price") or {}

    if not reg.get("amount"):
        raise RuntimeError(f"Kein regular_price im API-Response: {entry}")

    return PriceInfo(
        amount=reg.get("amount", ""),
        raw_value=float(reg.get("raw_value") or 0.0),
        currency=reg.get("currency", ""),
        sales_status=entry.get("sales_status", ""),
        discount_amount=disc.get("amount") if disc else None,
        discount_raw=float(disc["raw_value"]) if disc.get("raw_value") else None,
        discount_end=disc.get("end_datetime") if disc else None,
    )


# -------------------------------------------------------------------------
# Public
# -------------------------------------------------------------------------
def fetch_price() -> PriceInfo:
    """Holt aktuellen Preis via Nintendo Preis-API. Raises bei Fehlern."""
    nsuid = _get_nsuid()
    price = _fetch_api_price(nsuid)
    log.info(
        f"Preis: {price.display} "
        f"(raw={price.raw_value}, status={price.sales_status})"
    )
    return price
