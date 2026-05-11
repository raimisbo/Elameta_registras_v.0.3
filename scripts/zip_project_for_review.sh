#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_NAME="$(basename "$ROOT")"
PARENT_DIR="$(dirname "$ROOT")"
TS="$(date +%Y%m%d-%H%M%S)"
ZIP_PATH="${PARENT_DIR}/${PROJECT_NAME}-review-${TS}.zip"

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/${PROJECT_NAME}-review.XXXXXX")"
cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

echo "===== REVIEW ZIP ====="
echo "Project: $ROOT"
echo "Output:  $ZIP_PATH"
echo

mkdir -p "$TMP_DIR/$PROJECT_NAME"

rsync -a "$ROOT/" "$TMP_DIR/$PROJECT_NAME/" \
  --exclude ".git/" \
  --exclude ".idea/" \
  --exclude ".vscode/" \
  --exclude ".venv/" \
  --exclude ".venvs/" \
  --exclude "venv/" \
  --exclude "__pycache__/" \
  --exclude "*.pyc" \
  --exclude ".DS_Store" \
  --exclude "node_modules/" \
  --exclude "staticfiles/" \
  --exclude "media/" \
  --exclude "logs/" \
  --exclude "backups/" \
  --exclude "db.sqlite3" \
  --exclude "*.sqlite3-journal"

cd "$TMP_DIR"
zip -qr "$ZIP_PATH" "$PROJECT_NAME"

echo "===== CREATED ====="
ls -lh "$ZIP_PATH"

echo
echo "===== CLEAN CHECK ====="
if unzip -Z1 "$ZIP_PATH" | grep -E '(^|/)(logs|backups|media|db\.sqlite3|\.git|\.idea|\.venv|\.venvs|__pycache__|node_modules|staticfiles)(/|$)' ; then
  echo
  echo "KLAIDA: ZIP nėra švarus – rasti nereikalingi failai/katalogai."
  exit 1
else
  echo "OK: švarus review ZIP"
fi
