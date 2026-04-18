#!/usr/bin/env bash
# ============================================================================
# Nintendo Preis-Monitor - One-Shot Setup & Start (macOS)
#
# Erledigt in einem Rutsch:
#   1. Homebrew installieren/aktualisieren
#   2. Python 3.12 via brew installieren
#   3. Virtual Env anlegen (price_bot/.venv)
#   4. Python-Pakete aus requirements.txt installieren
#   5. .env interaktiv anlegen (Telegram-Token + Chat-ID abfragen), falls fehlt
#   6. Anwendung starten (python main.py)
#
# Usage:
#   ./bootstrap.sh               # voller Lauf + Start
#   ./bootstrap.sh --once        # Setup + EINMAL Preis pruefen und beenden
#   ./bootstrap.sh --no-start    # nur Setup, nicht starten
#   ./bootstrap.sh --update      # brew + pip zwingend updaten
# ============================================================================
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${SCRIPT_DIR}/price_bot"
VENV_DIR="${APP_DIR}/.venv"
PYTHON_FORMULA="python@3.12"

# ---- CLI Args ---------------------------------------------------------------
DO_START=1
FORCE_UPDATE=0
PASSTHROUGH_ARGS=()
for arg in "$@"; do
  case "$arg" in
    --no-start)  DO_START=0 ;;
    --update)    FORCE_UPDATE=1 ;;
    --help|-h)
      sed -n '2,20p' "$0"; exit 0 ;;
    *) PASSTHROUGH_ARGS+=("$arg") ;;
  esac
done

# ---- Pretty printing --------------------------------------------------------
c_green=$'\033[1;32m'; c_yellow=$'\033[1;33m'; c_red=$'\033[1;31m'
c_blue=$'\033[1;34m'; c_reset=$'\033[0m'
step() { echo ""; echo "${c_blue}===>${c_reset} ${c_blue}$*${c_reset}"; }
info() { echo "${c_green}[✓]${c_reset} $*"; }
warn() { echo "${c_yellow}[!]${c_reset} $*"; }
err()  { echo "${c_red}[x]${c_reset} $*" >&2; }

trap 'err "Abbruch - letzter Befehl fehlgeschlagen (Zeile $LINENO)"; exit 1' ERR

# ---- 1. Homebrew ------------------------------------------------------------
step "1/6  Homebrew pruefen"
if ! command -v brew >/dev/null 2>&1; then
  warn "Homebrew nicht gefunden - installiere jetzt."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi
if [[ -x /opt/homebrew/bin/brew ]]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
elif [[ -x /usr/local/bin/brew ]]; then
  eval "$(/usr/local/bin/brew shellenv)"
fi
info "Homebrew: $(brew --version | head -n1)"

if [[ $FORCE_UPDATE -eq 1 ]]; then
  info "brew update ..."
  brew update
fi

# ---- 2. Python --------------------------------------------------------------
step "2/6  Python installieren (${PYTHON_FORMULA})"
if ! brew list --formula --versions "$PYTHON_FORMULA" >/dev/null 2>&1; then
  brew install "$PYTHON_FORMULA"
elif [[ $FORCE_UPDATE -eq 1 ]]; then
  brew upgrade "$PYTHON_FORMULA" || true
else
  info "${PYTHON_FORMULA} bereits installiert."
fi

PYTHON_BIN="$(brew --prefix)/opt/${PYTHON_FORMULA}/bin/python3.12"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3)"
fi
info "Python: $($PYTHON_BIN --version) ($PYTHON_BIN)"

# ---- 3. Virtual Env ---------------------------------------------------------
step "3/6  Virtual Env anlegen"
if [[ ! -d "$VENV_DIR" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
  info "venv angelegt: $VENV_DIR"
else
  info "venv bereits vorhanden."
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
info "aktiv: $(python --version) ($(which python))"

# ---- 4. Python-Pakete -------------------------------------------------------
step "4/6  Python-Pakete installieren"
pip install --upgrade pip >/dev/null
PIP_FLAGS=""
[[ $FORCE_UPDATE -eq 1 ]] && PIP_FLAGS="--upgrade"
pip install $PIP_FLAGS -r "${APP_DIR}/requirements.txt"
info "requirements.txt installiert."

# ---- 5. .env anlegen (interaktiv, wenn fehlt) -------------------------------
step "5/6  .env pruefen"
ENV_FILE="${APP_DIR}/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  if [[ ! -f "${APP_DIR}/.env.example" ]]; then
    err ".env.example fehlt - kann .env nicht anlegen."
    exit 1
  fi
  cp "${APP_DIR}/.env.example" "$ENV_FILE"
  warn ".env aus .env.example angelegt."
  if [[ -t 0 && -t 1 ]]; then
    echo ""
    echo "${c_blue}Telegram-Konfiguration eingeben${c_reset}"
    echo "(Enter leer lassen, um den Default zu behalten)"
    read -r -p "TELEGRAM_TOKEN   : " tg_token
    read -r -p "TELEGRAM_CHAT_ID : " tg_chat
    read -r -p "SCHEDULE_HOURS [6,12,18]: " sched

    [[ -n "$tg_token" ]] && sed -i '' "s#^TELEGRAM_TOKEN=.*#TELEGRAM_TOKEN=${tg_token}#" "$ENV_FILE"
    [[ -n "$tg_chat"  ]] && sed -i '' "s#^TELEGRAM_CHAT_ID=.*#TELEGRAM_CHAT_ID=${tg_chat}#" "$ENV_FILE"
    [[ -n "$sched"    ]] && sed -i '' "s#^SCHEDULE_HOURS=.*#SCHEDULE_HOURS=${sched}#" "$ENV_FILE"
    info ".env geschrieben: $ENV_FILE"
  else
    warn "Kein Terminal - bitte ${ENV_FILE} manuell ausfuellen."
    exit 0
  fi
else
  info ".env bereits vorhanden."
fi

if grep -q '^TELEGRAM_TOKEN=$\|^TELEGRAM_TOKEN=123456:ABC-DEF' "$ENV_FILE"; then
  warn "TELEGRAM_TOKEN in .env sieht leer/Platzhalter aus."
fi

# ---- 6. Start ---------------------------------------------------------------
step "6/6  Start"
if [[ $DO_START -eq 0 ]]; then
  info "Setup fertig. Start wurde via --no-start uebersprungen."
  echo ""
  echo "Zum spaeteren Starten:"
  echo "  cd ${APP_DIR}"
  echo "  source .venv/bin/activate"
  echo "  python main.py"
  exit 0
fi

info "Starte Preis-Monitor ..."
cd "$APP_DIR"
exec python main.py "${PASSTHROUGH_ARGS[@]}"
