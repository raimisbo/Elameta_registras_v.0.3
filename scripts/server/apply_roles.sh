#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.." || exit 1

if [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
elif [ -x "$HOME/.venvs/registras/bin/python" ]; then
  PY="$HOME/.venvs/registras/bin/python"
else
  PY="python"
fi

echo "== Registras roles setup =="
echo "PROJECT=$(pwd)"
echo "PY=$PY"
echo

echo "== Django migrate =="
"$PY" manage.py migrate --noinput

echo
echo "== setup_roles =="
"$PY" manage.py setup_roles

echo
echo "== Grupės ir vartotojai =="
"$PY" manage.py shell <<'PY'
from django.contrib.auth.models import Group, User

print("GRUPĖS:")
for g in Group.objects.order_by("name"):
    print(f"- {g.name}")

print()
print("VARTOTOJAI:")
for u in User.objects.order_by("username"):
    groups = ", ".join(u.groups.values_list("name", flat=True)) or "-"
    print(f"- {u.username}: superuser={u.is_superuser}, groups={groups}")
PY

echo
echo "OK: roles setup baigtas."
