#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

VENV_DIR="${REGISTRAS_VENV:-$HOME/.venvs/registras}"

echo "== Project root: $PROJECT_ROOT"
echo "== Expected venv: $VENV_DIR"

if [[ -d "$PROJECT_ROOT/.venv" ]]; then
  echo "KLAIDA: projekte rastas .venv katalogas."
  echo "Pagal dabartinę tvarką venv turi būti lokalus Mac'e: $VENV_DIR"
  exit 1
fi

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "KLAIDA: neradau veikiančio venv: $VENV_DIR"
  echo "Pirma paleisk: ./start_registras.sh"
  exit 1
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo "== VIRTUAL_ENV=$VIRTUAL_ENV"
echo "== Python:"
which python
python -V

echo "== Django system check:"
python manage.py check

echo "== Migration check:"
python manage.py makemigrations --check --dry-run

echo "== Migrate:"
python manage.py migrate

echo "== Smoke test:"
python scripts/smoke_test.py

echo "== OK: healthcheck finished"
