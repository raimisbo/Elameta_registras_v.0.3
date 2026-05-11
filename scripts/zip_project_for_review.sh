#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_NAME="$(basename "$PROJECT_ROOT")"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT_ZIP="${PROJECT_ROOT}/../${PROJECT_NAME}-review-${STAMP}.zip"

cd "$PROJECT_ROOT"

if [[ ! -f "manage.py" ]]; then
  echo "KLAIDA: manage.py nerastas."
  exit 1
fi

echo "Kuriamas švarus review ZIP:"
echo "$OUT_ZIP"

COPYFILE_DISABLE=1 zip -r "$OUT_ZIP" . \
  -x ".git/*" \
  -x "./.git/*" \
  -x ".idea/*" \
  -x "./.idea/*" \
  -x ".vscode/*" \
  -x "./.vscode/*" \
  -x ".venv/*" \
  -x "./.venv/*" \
  -x ".venvs/*" \
  -x "./.venvs/*" \
  -x "venv/*" \
  -x "./venv/*" \
  -x "env/*" \
  -x "./env/*" \
  -x "staticfiles/*" \
  -x "./staticfiles/*" \
  -x "logs" \
  -x "./logs" \
  -x "logs/" \
  -x "./logs/" \
  -x "logs/*" \
  -x "./logs/*" \
  -x "backups" \
  -x "./backups" \
  -x "backups/" \
  -x "./backups/" \
  -x "backups/*" \
  -x "./backups/*" \
  -x "media" \
  -x "./media" \
  -x "media/" \
  -x "./media/" \
  -x "media/*" \
  -x "./media/*" \
  -x "__pycache__/*" \
  -x "*/__pycache__/*" \
  -x "*.pyc" \
  -x "*.pyo" \
  -x "*.pyd" \
  -x ".DS_Store" \
  -x "*/.DS_Store" \
  -x "._*" \
  -x "*/._*" \
  -x "__MACOSX/*" \
  -x "*.zip" \
  -x "db.sqlite3" \
  -x "*.sqlite3-journal" \
  -x "*.sqlite3-wal" \
  -x "*.sqlite3-shm"

echo
echo "OK: $OUT_ZIP"
echo "Šitas ZIP skirtas kodo peržiūrai. DB ir media į jį sąmoningai neįtraukti."
