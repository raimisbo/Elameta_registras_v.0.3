#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${REGISTRAS_PROJECT_DIR:-/Volumes/Extreme SSD/Projektai/Elameta/registras}"
VENV_DIR="${REGISTRAS_VENV_DIR:-$HOME/.venvs/registras}"
HOST="${REGISTRAS_HOST:-127.0.0.1}"
PORT="${REGISTRAS_PORT:-8000}"
START_PATH="${REGISTRAS_START_PATH:-/pozicijos/}"

RUN_FULL_CHECKS=0
SKIP_INSTALL=0
NO_BROWSER=0

for arg in "$@"; do
  case "$arg" in
    --full-checks) RUN_FULL_CHECKS=1 ;;
    --skip-install) SKIP_INSTALL=1 ;;
    --no-browser) NO_BROWSER=1 ;;
    -h|--help)
      cat <<'HELP'
Naudojimas:
  ./demo_registras.sh

Papildomai:
  ./demo_registras.sh --full-checks   # paleidžia ir ./run_all_checks.sh
  ./demo_registras.sh --skip-install  # nepraleidžia laiko pip install tikrinimui
  ./demo_registras.sh --no-browser    # neatidaro naršyklės automatiškai

Aplinkos kintamieji:
  REGISTRAS_PROJECT_DIR="/Volumes/Extreme SSD/Projektai/Elameta/registras"
  REGISTRAS_VENV_DIR="$HOME/.venvs/registras"
  REGISTRAS_PORT=8000
HELP
      exit 0
      ;;
    *)
      echo "Nežinomas argumentas: $arg"
      exit 2
      ;;
  esac
done

log() {
  printf '\n\033[1;36m== %s ==\033[0m\n' "$*"
}

warn() {
  printf '\033[1;33m[WARN]\033[0m %s\n' "$*"
}

die() {
  printf '\033[1;31m[FAIL]\033[0m %s\n' "$*" >&2
  exit 1
}

find_python() {
  local candidates=(
    "/opt/homebrew/bin/python3.13"
    "/usr/local/bin/python3.13"
    "python3.13"
    "python3"
  )

  for c in "${candidates[@]}"; do
    if command -v "$c" >/dev/null 2>&1; then
      local py
      py="$(command -v "$c")"
      if "$py" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
      then
        echo "$py"
        return 0
      fi
    fi
  done

  return 1
}

is_port_busy() {
  lsof -tiTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

pick_port() {
  local p="$PORT"
  while is_port_busy "$p"; do
    warn "Portas $p užimtas, bandau kitą."
    p=$((p + 1))
    if [ "$p" -gt 8010 ]; then
      die "Portai 8000-8010 užimti. Uždaryk seną serverį arba nurodyk REGISTRAS_PORT."
    fi
  done
  echo "$p"
}

log "Projektas"
[ -d "$PROJECT_DIR" ] || die "Nerandu projekto katalogo: $PROJECT_DIR"
cd "$PROJECT_DIR"
[ -f "manage.py" ] || die "Šiame kataloge nėra manage.py: $PROJECT_DIR"

echo "PROJECT_DIR=$PROJECT_DIR"
echo "VENV_DIR=$VENV_DIR"

mkdir -p logs
LOG_FILE="logs/demo_start_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$LOG_FILE") 2>&1

log "Aplinka"
echo "macOS: $(sw_vers -productVersion 2>/dev/null || echo unknown)"
echo "PWD:   $(pwd)"
echo "LOG:   $LOG_FILE"

PY_BIN="$(find_python)" || die "Neradau tinkamo Python. Reikia python3.11+; geriausia python3.13."
echo "Python pasirinktas: $PY_BIN"
"$PY_BIN" -V

log "Venv"
if [ ! -x "$VENV_DIR/bin/python" ]; then
  warn "Venv nerastas. Kuriu: $VENV_DIR"
  "$PY_BIN" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

echo "VIRTUAL_ENV=$VIRTUAL_ENV"
echo "python=$(which python)"
python -V

log "Priklausomybės"
if [ "$SKIP_INSTALL" -eq 1 ]; then
  echo "Praleidžiu pip install (--skip-install)."
else
  if [ -f requirements.txt ]; then
    REQ_HASH="$(shasum -a 256 requirements.txt | awk '{print $1}')"
    STAMP_FILE="$VENV_DIR/.registras_requirements_sha256"
    OLD_HASH=""
    [ -f "$STAMP_FILE" ] && OLD_HASH="$(cat "$STAMP_FILE" || true)"

    if [ "$REQ_HASH" != "$OLD_HASH" ]; then
      echo "requirements.txt pasikeitė arba venv naujas. Diegiu paketus..."
      python -m pip install --upgrade pip setuptools wheel
      python -m pip install -r requirements.txt
      echo "$REQ_HASH" > "$STAMP_FILE"
    else
      echo "requirements.txt nepasikeitė. pip install praleidžiam."
    fi
  else
    warn "requirements.txt nerastas. Tikrinu tik Django importą."
  fi
fi

python - <<'PY'
import django
print("Django:", django.get_version())
PY

log "Git būsena"
if command -v git >/dev/null 2>&1 && [ -d .git ]; then
  git status --short
else
  warn "Git nerastas arba čia ne git working tree."
fi

log "DB"
if [ -f db.sqlite3 ]; then
  mkdir -p backups
  DB_BACKUP="backups/demo_db_$(date +%Y%m%d_%H%M%S).sqlite3"
  cp -p db.sqlite3 "$DB_BACKUP"
  echo "DB backup: $DB_BACKUP"
else
  warn "db.sqlite3 nerastas. Serveris veiks, bet demo duomenų gali nebūti."
fi

log "Django greitos patikros"
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --noinput

if [ "$RUN_FULL_CHECKS" -eq 1 ]; then
  log "Pilnos patikros"
  if [ -x ./run_all_checks.sh ]; then
    ./run_all_checks.sh
  else
    die "./run_all_checks.sh nerastas arba nepaleidžiamas"
  fi
else
  echo "Pilnos patikros praleistos. Jei reikia: ./demo_registras.sh --full-checks"
fi

PORT="$(pick_port)"
URL="http://${HOST}:${PORT}${START_PATH}"

log "Paleidimas"
echo "URL: $URL"
echo "Sustabdymas: Ctrl+C"

if [ "$NO_BROWSER" -eq 0 ]; then
  if command -v open >/dev/null 2>&1; then
    (sleep 2; open "$URL") &
  fi
fi

python manage.py runserver "${HOST}:${PORT}"
