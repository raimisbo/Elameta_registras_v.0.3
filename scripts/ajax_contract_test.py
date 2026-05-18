#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "registras.settings")


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""


def _print(res: CheckResult) -> None:
    status = "OK" if res.ok else "FAIL"
    line = f"[{status}] {res.name}"
    if res.detail:
        line += f" — {res.detail}"
    print(line)


def main() -> int:
    import django  # noqa
    django.setup()

    from django.conf import settings
    if "testserver" not in settings.ALLOWED_HOSTS:
        settings.ALLOWED_HOSTS.append("testserver")

    from django.contrib.auth import get_user_model
    from django.test import Client
    from django.urls import reverse

    User = get_user_model()
    user, created = User.objects.get_or_create(
        username="ajax-contract-test",
        defaults={"is_active": True},
    )
    if created:
        user.set_unusable_password()
        user.save(update_fields=["password"])
    elif not user.is_active:
        user.is_active = True
        user.save(update_fields=["is_active"])

    c = Client()
    c.force_login(user)

    results: list[CheckResult] = []

    # 1) tbody: turi grąžinti HTML (bent minimaliai su <tr arba data-pk)
    try:
        url = reverse("pozicijos:tbody")
        r = c.get(url)
        body = (r.content or b"").decode("utf-8", errors="replace")
        if r.status_code == 200:
            ok = ("<tr" in body) or ("data-pk" in body) or ("<tbody" in body)
            results.append(CheckResult("AJAX tbody HTML contract", ok, f"{r.status_code} {url} len={len(body)}"))
        else:
            results.append(CheckResult("AJAX tbody HTML contract", False, f"{r.status_code} {url}"))
    except Exception as e:
        results.append(CheckResult("AJAX tbody HTML contract", False, repr(e)))

    # 2) stats: turi grąžinti JSON su labels/values/total
    try:
        url = reverse("pozicijos:stats")
        r = c.get(url)
        if r.status_code == 200:
            try:
                data = r.json()
                ok = all(k in data for k in ("labels", "values", "total"))
                results.append(CheckResult("Stats JSON contract", ok, f"{r.status_code} {url} keys={list(data.keys())}"))
            except Exception as je:
                results.append(CheckResult("Stats JSON contract", False, f"{r.status_code} {url} json_error={repr(je)}"))
        else:
            results.append(CheckResult("Stats JSON contract", False, f"{r.status_code} {url}"))
    except Exception as e:
        results.append(CheckResult("Stats JSON contract", False, repr(e)))

    print("\n== AJAX contract test results ==")
    for r in results:
        _print(r)

    failed = [r for r in results if not r.ok]
    print("\n== Summary ==")
    print(f"Total: {len(results)} | Failed: {len(failed)}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
