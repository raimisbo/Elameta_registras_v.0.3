#!/usr/bin/env bash

#chmod +x scripts/run_all_checks.sh
# ./scripts/run_all_checks.sh
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# aktyvuojam venv, jei yra
if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source ".venv/bin/activate"
fi

echo "== Python =="; python -V
echo "== Django check =="; python manage.py check
echo "== Migration check (dry) =="; python manage.py makemigrations --check --dry-run
echo "== Migrate =="; python manage.py migrate

echo "== reverse audit =="; python scripts/reverse_audit.py
echo "== smoke test =="; python scripts/smoke_test.py

echo "== ajax contract test =="; python scripts/ajax_contract_test.py
echo "== upload flow test =="; python scripts/upload_flow_test.py


echo "== OK: all checks passed =="
