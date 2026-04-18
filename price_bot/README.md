# Nintendo Preis-Monitor

Schickt zu festen Uhrzeiten (Default **06 / 12 / 18 Uhr**) den aktuellen
Preis einer Nintendo-Produktseite via Telegram. Beim Start kommt sofort
ein erster Preis-Push. Optional Alarm bei Preisänderung zwischen den
Checks.

**Zwei Betriebsmodi**:
- **Lokal** als dauerhafter Prozess (macOS, `./bootstrap.sh`)
- **GitHub Actions** als Cron-Scheduler (siehe unten)

## Projektstruktur

```
EifelBot/                          # Repo-Root
├── .github/workflows/
│   └── price-check.yml            # GitHub-Actions-Cron (alle 15 Min)
├── .gitignore                     # ignoriert .env, .venv/, __pycache__
├── bootstrap.sh                   # macOS-Setup fuer lokalen Betrieb
└── price_bot/
    ├── main.py                    # Einstieg, Scheduler, --once-Modus
    ├── config.py                  # Token, URL, Uhrzeiten aus .env / env
    ├── price_fetcher.py           # Nintendo Preis-API + HTML-Fallback
    ├── state.py                   # price_state.json lesen/schreiben
    ├── notifier.py                # Dispatcher: Telegram + ntfy + SMS
    ├── telegram_notifier.py       # Telegram Bot-API
    ├── ntfy_notifier.py           # ntfy.sh Push (kostenlos)
    ├── sms_notifier.py            # Twilio SMS (optional)
    ├── requirements.txt
    ├── .env.example
    ├── price_state.json           # persistenter Zustand (wird committet)
    └── README.md
```

## Setup (macOS, one-shot)

```bash
cd /Users/alex/Entwicklung/Projekte/EifelBot
./bootstrap.sh
```

Das Script installiert Homebrew/Python 3.12, legt ein venv an,
installiert die Pakete und fragt bei fehlender `.env` nach
`TELEGRAM_TOKEN` / `TELEGRAM_CHAT_ID`.

## Nützliche Kommandos

```bash
./bootstrap.sh            # voller Lauf + Start
./bootstrap.sh --once     # ein einzelner Preis-Check, dann Ende
./bootstrap.sh --no-start # nur Setup
./bootstrap.sh --update   # brew + pip force-upgrade
```

Manueller Start ohne bootstrap:

```bash
cd price_bot
source .venv/bin/activate
python main.py            # dauerhafter Scheduler
python main.py --once     # einmalig
```

## Konfiguration (`.env`)

### Pflicht (Telegram)
| Variable              | Default                            | Bedeutung                               |
|-----------------------|------------------------------------|-----------------------------------------|
| `TELEGRAM_TOKEN`      | –                                  | Bot-Token                               |
| `TELEGRAM_CHAT_ID`    | –                                  | Chat-ID                                 |

### Produkt
| Variable              | Default                            | Bedeutung                               |
|-----------------------|------------------------------------|-----------------------------------------|
| `PRODUCT_URL`         | Marvel's GotG Cloud Version (DE)   | überwachte Produktseite                 |
| `PRODUCT_NAME`        | Marvel's Guardians … (Cloud …)     | Anzeigename in Nachrichten              |
| `NSUID`               | `70010000042763`                   | Nintendo-System-UID für Direkt-API      |

### Ablauf
| Variable              | Default                            | Bedeutung                               |
|-----------------------|------------------------------------|-----------------------------------------|
| `SCHEDULE_HOURS`      | `6,12,18`                          | Stunden für Standard-Pushes             |
| `CHECK_INTERVAL_MIN`  | `15`                               | Background-Check-Intervall (Min)        |
| `ALERT_ON_CHANGE`     | `true`                             | Nachricht bei Preisänderung             |
| `LOW_PRICE_THRESHOLD` | `50.0`                             | Alarm-Schwelle in €                     |
| `ALARM_BURST_COUNT`   | `3`                                | Anzahl Nachrichten bei Preis-Alarm      |

### Zusätzliche Kanäle (alle optional)

**ntfy.sh — Push-Nachrichten (kostenlos, empfohlen)**

Funktional wie SMS (Push aufs Handy), aber gratis und ohne Registrierung.

1. App **ntfy** im App Store / Play Store installieren
2. In der App „+" → Topic-Name eintragen (möglichst eindeutig, z. B. `alex-nintendo-xyz123`)
3. In der `.env`:

```
NTFY_TOPIC=alex-nintendo-xyz123
```

Fertig. Bei Preisalarmen kommt eine Push-Nachricht mit `Priority 5` (durchbricht Silent-Mode).

| Variable      | Default            | Bedeutung                                   |
|---------------|--------------------|---------------------------------------------|
| `NTFY_TOPIC`  | –                  | Topic-Name. Wenn leer: ntfy aus             |
| `NTFY_SERVER` | `https://ntfy.sh`  | Bei self-hosted Server                      |
| `NTFY_TOKEN`  | –                  | Bei Auth-geschütztem Server                 |

**SMS via Twilio (kostenpflichtig, optional)**

~0,08 €/SMS in DE, Trial-Credits bei Anmeldung. Benötigt Account + verifizierte Absender-Nummer.

| Variable              | Bedeutung                                   |
|-----------------------|---------------------------------------------|
| `TWILIO_ACCOUNT_SID`  | Account SID (Dashboard)                     |
| `TWILIO_AUTH_TOKEN`   | Auth Token                                  |
| `TWILIO_FROM`         | Twilio-Absender (E.164: `+49…`)            |
| `SMS_TO`              | Empfänger (deine Nummer)                    |

Wenn eine der 4 Variablen leer ist, wird SMS übersprungen — keine Fehler.

## Nachrichten-Typen

| Wann | Inhalt |
|---|---|
| **Beim Start** | 1× Standard-Message mit aktuellem Preis |
| **06/12/18 Uhr** | 1× Standard-Message (einmal pro Stunde pro Tag) |
| **Zwischen Checks (alle 15 Min)** | nur intern prüfen. Kein Push, außer: |
| Preis hat sich geändert | 1× Message (wenn `ALERT_ON_CHANGE=true`) |
| Preis fällt unter 50 € | **3× Message hintereinander** („Preisalarm 1/3, 2/3, 3/3") |
| Preis wieder ≥ 50 € | kein Push, aber Alarm-Flag wird zurückgesetzt |

## Wie die Preiserkennung funktioniert

Nintendo rendert den Preis statisch im HTML:

```html
<div class="plm-price__main">69,99&nbsp;€</div>
```

`price_fetcher.py` liest den Selektor `.plm-price__main`, normalisiert
`&nbsp;` und prüft, ob der Text Zahl + Währungssymbol enthält.
Fallbacks: `.pla-price`, `meta[itemprop='price']`, Regex im rohen HTML.

## Wenn Nintendo das Markup ändert

In [price_fetcher.py:extract_price](price_fetcher.py) die Liste der
CSS-Selektoren erweitern. Der Code loggt Titel der Seite bei
Nicht-Fund, damit du zielgerichtet den richtigen neuen Selektor
finden kannst.

---

## Deployment auf GitHub Actions

Damit der Bot 24/7 läuft, ohne dass dein Mac an sein muss.

Der Workflow [`.github/workflows/price-check.yml`](../.github/workflows/price-check.yml)
läuft alle 15 Minuten via Cron und führt intern `python main.py --once` aus.
Bei relevanter Änderung (Preis, Alarm-Flag, Schedule-Feuerung) wird
`price_state.json` automatisch zurück committet — sonst nicht.

### 1. Privates Repo anlegen & pushen

```bash
cd /Users/alex/Entwicklung/Projekte/EifelBot
git init
git add .
git commit -m "initial: price-bot"

# GitHub-CLI (empfohlen):
gh repo create price-bot --private --source=. --push

# ...oder manuell auf github.com ein Repo anlegen, dann:
# git remote add origin git@github.com:USER/price-bot.git
# git push -u origin main
```

### 2. Secrets einrichten

**Settings → Secrets and variables → Actions → Secrets**:

| Name | Beispielwert |
|------|--------------|
| `TELEGRAM_TOKEN` | `123456789:ABC…` (**vor Einfügen rotieren**, BotFather `/revoke`) |
| `TELEGRAM_CHAT_ID` | `8504254536` |
| `NTFY_TOPIC` | `marvelSwitchPriceBot51597` (optional, aber empfohlen) |

Optional (nur wenn tatsächlich SMS gewünscht):
`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM`, `SMS_TO`.

### 3. Variables einrichten (nicht-sensitive Config)

**Settings → Secrets and variables → Actions → Variables**:

| Name | Wert |
|------|------|
| `PRODUCT_URL` | `https://www.nintendo.com/de-de/Spiele/...1987417.html` |
| `PRODUCT_NAME` | `Marvel's Guardians of the Galaxy (Cloud Version)` |
| `NSUID` | `70010000042763` |
| `SCHEDULE_TIMES` | `06:00,12:00,18:00` |
| `LOW_PRICE_THRESHOLD` | `50.0` |
| `ALARM_BURST_COUNT` | `3` |
| `ALERT_ON_CHANGE` | `true` |

Wenn du eine Variable nicht setzt, greifen die Defaults aus [`config.py`](config.py).

### 4. Workflow manuell triggern

1. GitHub Repo → **Actions** → **Nintendo Price Monitor** → **Run workflow**
2. Im Log erwartet:
   ```
   PUSH -> reason='Start'
   [telegram] Telegram gesendet.
   [ntfy] ntfy gesendet (topic=…, attempt=1)
   chore(state): update price state [skip ci]
   ```
3. Telegram + ntfy-Push kommen am Handy an
4. Im Repo: neuer Commit von `price-bot <price-bot@users.noreply.github.com>`

### 5. Wie es täglich läuft

- Cron feuert alle 15 Min
- Die meisten Runs ändern **nichts** Relevantes → kein Commit, saubere History
- Zu 06:00 / 12:00 / 18:00 (Berlin-Zeit, via `TZ=Europe/Berlin`) → Push + Commit
- Bei Preisänderung oder Unterschreiten der 50 €-Schwelle → Push + Commit
- Erwartete Commit-Frequenz: **3–5 pro Tag**

### Trade-offs

- **Schedule-Drift**: GitHub-Cron ist nicht sekundengenau. Dein 19:30-Push kann zwischen 19:30 und ~19:45 kommen. Die `now >= scheduled`-Logik garantiert aber, dass er genau **einmal pro Tag** feuert.
- **Actions-Minuten**: ~30 s pro Run × 96 Runs × 30 Tage ≈ 1440 Min/Monat → passt bequem in die 2000 Gratis-Min für private Repos.
- **State-Verlust**: Falls der allererste Workflow-Run fehlschlägt und `price_state.json` nie ins Repo kommt, liest der zweite Run `{}` → kein `changed`-Vergleich möglich, aber der Run selbst funktioniert und legt den State dann an.

### Lokal parallel laufen lassen?

Möglich aber **nicht empfehlenswert** — beide würden unabhängig Pushes senden. Wenn du lokal entwickelst, halte den lokalen Prozess kurz an (`Ctrl+C`) oder stelle in der lokalen `.env` sehr lange Intervalle ein.

