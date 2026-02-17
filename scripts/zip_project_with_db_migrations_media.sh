#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(pwd)"
PROJECT_NAME="$(basename "$PROJECT_ROOT")"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT_ZIP="./${PROJECT_NAME}-with-db-migrations-media-${STAMP}.zip"

if [[ ! -f "manage.py" ]]; then
  echo "KLAIDA: manage.py nerastas. Paleisk skriptą iš Django projekto šaknies."
  exit 1
fi

echo "Kuriamas archyvas projekto šaknyje: $OUT_ZIP"

zip -r "$OUT_ZIP" . \
  -x "*.git*" \
  -x ".DS_Store" \
  -x "*/__pycache__/*" \
  -x "*.pyc" \
  -x "*.pyo" \
  -x "*.pyd" \
  -x ".pytest_cache/*" \
  -x ".mypy_cache/*" \
  -x ".ruff_cache/*" \
  -x ".idea/*" \
  -x ".vscode/*" \
  -x ".venv/*" \
  -x "venv/*" \
  -x "node_modules/*" \
  -x "staticfiles/*" \
  -x "*.zip"

echo "OK: suzipinta -> $OUT_ZIP"
echo "Archyve: projektas + DB + migracijos + media."
