#!/bin/zsh
set -e

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_ROOT"

VENV_DIR="${REGISTRAS_VENV:-$HOME/.venvs/registras}"

PYTHON_CANDIDATES=(
  "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"
  "/opt/homebrew/bin/python3.13"
  "/usr/local/bin/python3.13"
  "/opt/homebrew/bin/python3"
  "/usr/local/bin/python3"
)

if command -v python3 >/dev/null 2>&1; then
  PYTHON_CANDIDATES+=("$(command -v python3)")
fi

PYTHON_BIN=""

for p in "${PYTHON_CANDIDATES[@]}"; do
  if [ -x "$p" ]; then
    if "$p" - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
    then
      PYTHON_BIN="$p"
      break
    fi
  fi
done

if [ -z "$PYTHON_BIN" ]; then
  echo "KLAIDA: neradau tinkamo Python 3.11+."
  echo "Rekomenduojama: Python 3.13 iš python.org."
  exit 1
fi

echo "== REGISTRAS =="
echo "Projektas: $PROJECT_ROOT"
echo "Venv: $VENV_DIR"
echo "Bazinis Python: $PYTHON_BIN"
"$PYTHON_BIN" -V

if [ -d "$PROJECT_ROOT/.venv" ]; then
  echo "KLAIDA: projekte vis dar yra .venv katalogas."
  echo "Pagal pasirinktą tvarką venv turi būti: $VENV_DIR"
  echo "Ištrink projekto .venv: rm -rf .venv"
  exit 1
fi

if [ ! -x "$VENV_DIR/bin/python" ]; then
  echo "Kuriu lokalią virtualią aplinką šiame Mac'e..."
  mkdir -p "$HOME/.venvs"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

if ! "$VENV_DIR/bin/python" - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
then
  BROKEN_VENV="${VENV_DIR}.broken.$(date +%Y%m%d_%H%M%S)"
  echo "Venv netinkamas arba senas. Pervadinu į:"
  echo "$BROKEN_VENV"
  mv "$VENV_DIR" "$BROKEN_VENV"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

echo "Aktyvus VIRTUAL_ENV=$VIRTUAL_ENV"
echo "Aktyvus Python: $(which python)"
python -V

python -m pip install --upgrade pip

REQ_HASH="$(shasum -a 256 requirements.txt | awk '{print $1}')"
REQ_STAMP="$VENV_DIR/.requirements.sha256"

if [ ! -f "$REQ_STAMP" ] || [ "$(cat "$REQ_STAMP")" != "$REQ_HASH" ]; then
  echo "Diegiu / atnaujinu requirements.txt..."
  pip install -r requirements.txt
  echo "$REQ_HASH" > "$REQ_STAMP"
else
  echo "requirements.txt nepasikeitęs — pip install praleidžiam."
fi

python manage.py check

echo
echo "Paleidžiu serverį:"
echo "http://127.0.0.1:8000/"
echo

python manage.py runserver 127.0.0.1:8000
