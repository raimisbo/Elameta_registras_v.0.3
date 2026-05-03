#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

VENV_DIR="${REGISTRAS_VENV:-$HOME/.venvs/registras}"

echo "== REGISTRAS FULL CHECK =="
echo "Project root: $PROJECT_ROOT"
echo "Expected venv: $VENV_DIR"

if [[ -d "$PROJECT_ROOT/.venv" ]]; then
  echo "KLAIDA: projekte rastas .venv katalogas."
  echo "Pagal dabartinę tvarką venv turi būti lokalus Mac'e:"
  echo "$VENV_DIR"
  echo
  echo "Jei tai senas likutis, pašalink:"
  echo "rm -rf .venv"
  exit 1
fi

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "KLAIDA: neradau veikiančio venv:"
  echo "$VENV_DIR"
  echo
  echo "Pirma paleisk:"
  echo "./start_registras.sh"
  exit 1
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo
echo "== Python =="
echo "VIRTUAL_ENV=$VIRTUAL_ENV"
which python
python -V

echo
echo "== Django check =="
python manage.py check

echo
echo "== Migration check dry-run =="
python manage.py makemigrations --check --dry-run

echo
echo "== Migrate =="
python manage.py migrate

echo
echo "== Reverse audit =="
python scripts/reverse_audit.py

echo
echo "== Smoke test =="
python scripts/smoke_test.py

echo
echo "== Ajax contract test =="
python scripts/ajax_contract_test.py

echo
echo "== Filter regression test =="
python scripts/filter_regression_test.py

echo
echo "== Upload flow test =="
python scripts/upload_flow_test.py

echo
echo "== OK: all checks passed =="
