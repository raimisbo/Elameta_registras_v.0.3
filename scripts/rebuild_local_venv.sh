#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="/Volumes/Extreme SSD/Projektai/Elameta/registras"
VENV_DIR="$HOME/.venvs/registras"
PYTHON_BIN="/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13"

cd "$PROJECT_DIR" || exit 1

echo "===== Python patikra ====="
if [ ! -x "$PYTHON_BIN" ]; then
  echo "NERASTAS Python: $PYTHON_BIN"
  echo "Perinstaliuok Python 3.13 iš python.org"
  exit 1
fi

"$PYTHON_BIN" -V
"$PYTHON_BIN" -m venv /tmp/registras-venv-test
/tmp/registras-venv-test/bin/python -V
rm -rf /tmp/registras-venv-test

echo
echo "===== Perkuriam venv ====="
deactivate 2>/dev/null || true
rm -rf "$VENV_DIR"
mkdir -p "$HOME/.venvs"

"$PYTHON_BIN" -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

echo "VIRTUAL_ENV=$VIRTUAL_ENV"
which python
python -V

echo
echo "===== Paketai ====="
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt

echo
echo "===== Django check ====="
python -c "import django; print('Django', django.get_version())"
python manage.py check

echo
echo "OK: lokalus venv atkurtas:"
echo "$VENV_DIR"
