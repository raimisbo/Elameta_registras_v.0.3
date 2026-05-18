#!/usr/bin/env python3
from __future__ import annotations

import html
import os
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
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


def _value_is_preserved(body: str, value: str) -> bool:
    escaped = html.escape(value, quote=True)
    return (
        f'value="{value}"' in body
        or f"value='{value}'" in body
        or f'value="{escaped}"' in body
        or f"value='{escaped}'" in body
    )


def main() -> int:
    import django
    django.setup()

    from django.conf import settings
    if "testserver" not in settings.ALLOWED_HOSTS:
        settings.ALLOWED_HOSTS.append("testserver")

    from django.contrib.auth import get_user_model
    from django.test import Client
    from django.urls import reverse

    User = get_user_model()
    user, created = User.objects.get_or_create(
        username="filter-regression-test",
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

    list_url = reverse("pozicijos:list")
    tbody_url = reverse("pozicijos:tbody")
    stats_url = reverse("pozicijos:stats")

    list_cases = [
        ("int range hyphen", {"f[ktl_detaliu_kiekis_reme]": "1-10"}),
        ("int range dots", {"f[miltai_detaliu_kiekis_reme]": "1..10"}),
        ("decimal cmp", {"f[miltai_kiekis_per_valanda]": ">=1"}),
        ("price decimal comma", {"f[kaina_eur]": "1,5"}),
        ("metal thickness exact", {"f[metalo_storiai_display]": "1"}),
        ("metal thickness range", {"f[metalo_storiai_display]": "1..3"}),
        ("created date exact", {"f[created]": "2026-05-03"}),
        ("created date range", {"f[created]": "2026-05-01..2026-05-31"}),
        ("updated date cmp", {"f[updated]": ">=2026-05-01"}),
        ("bad int format", {"f[ktl_detaliu_kiekis_reme]": "abc"}),
        ("bad date format", {"f[created]": "abc"}),
        ("unknown filter ignored", {"f[unknown_filter_key]": "abc"}),
    ]

    for name, params in list_cases:
        try:
            r = c.get(list_url, params)
            ok = r.status_code == 200
            results.append(CheckResult(f"list filter: {name}", ok, f"{r.status_code} {params}"))
        except Exception as e:
            results.append(CheckResult(f"list filter: {name}", False, repr(e)))

    preserve_cases = [
        ("preserve klientas", {"f[klientas]": "TEST_KLIENTAS"}, "TEST_KLIENTAS"),
        ("preserve created exact", {"f[created]": "2026-05-03"}, "2026-05-03"),
        ("preserve created range", {"f[created]": "2026-05-01..2026-05-31"}, "2026-05-01..2026-05-31"),
        ("preserve updated cmp", {"f[updated]": ">=2026-05-01"}, ">=2026-05-01"),
    ]

    for name, params, value in preserve_cases:
        try:
            r = c.get(list_url, params)
            body = r.content.decode("utf-8", errors="replace")
            ok = r.status_code == 200 and _value_is_preserved(body, value)
            results.append(CheckResult(name, ok, f"{r.status_code} value={value!r}"))
        except Exception as e:
            results.append(CheckResult(name, False, repr(e)))

    tbody_cases = [
        ("tbody int range", {"f[ktl_detaliu_kiekis_reme]": "1-10"}),
        ("tbody metal range", {"f[metalo_storiai_display]": "1..3"}),
        ("tbody date range", {"f[created]": "2026-05-01..2026-05-31"}),
        ("tbody bad int", {"f[ktl_detaliu_kiekis_reme]": "abc"}),
    ]

    for name, params in tbody_cases:
        try:
            r = c.get(tbody_url, params)
            ok = r.status_code == 200
            results.append(CheckResult(name, ok, f"{r.status_code} {params}"))
        except Exception as e:
            results.append(CheckResult(name, False, repr(e)))

    stats_cases = [
        ("stats int range", {"f[ktl_detaliu_kiekis_reme]": "1-10"}),
        ("stats metal range", {"f[metalo_storiai_display]": "1..3"}),
        ("stats date range", {"f[created]": "2026-05-01..2026-05-31"}),
        ("stats bad date", {"f[created]": "abc"}),
    ]

    for name, params in stats_cases:
        try:
            r = c.get(stats_url, params)
            if r.status_code != 200:
                results.append(CheckResult(name, False, f"{r.status_code} {params}"))
                continue

            data = r.json()
            ok = all(k in data for k in ("labels", "values", "total"))
            results.append(CheckResult(name, ok, f"{r.status_code} keys={list(data.keys())}"))
        except Exception as e:
            results.append(CheckResult(name, False, repr(e)))

    print("\n== Filter regression test results ==")
    for r in results:
        _print(r)

    failed = [r for r in results if not r.ok]

    print("\n== Summary ==")
    print(f"Total: {len(results)} | Failed: {len(failed)}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
