#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

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


def main() -> int:
    import django  # noqa
    django.setup()

    from django.conf import settings
    if "testserver" not in settings.ALLOWED_HOSTS:
        settings.ALLOWED_HOSTS.append("testserver")

    from django.test import Client
    from django.urls import reverse
    from pozicijos.models import Pozicija

    results: list[CheckResult] = []

    # Smoke testas neturi palikti senų testinių Pozicija įrašų DB.
    # Triname tik labai siaurus markerinius įrašus, kad nepaliestume realių duomenų.
    for marker in ("SMOKE", "SMOKE_TEST_TEMP"):
        deleted_count, _ = Pozicija.objects.filter(
            klientas=marker,
            projektas=marker,
            poz_kodas=marker,
            poz_pavad=marker,
        ).delete()
        if deleted_count:
            results.append(
                CheckResult(
                    "cleanup stale smoke Pozicija",
                    True,
                    f"marker={marker}, deleted={deleted_count}",
                )
            )

    resolved: dict[str, str] = {}

    poz: Optional[Pozicija] = None
    created_here = False
    temp_poz_id: Optional[int] = None

    try:
        # Reverse baziniams
        for name in (
            "pozicijos:list",
            "pozicijos:tbody",
            "pozicijos:stats",
            "pozicijos:create",
            "pozicijos:import_csv",
        ):
            try:
                resolved[name] = reverse(name)
                results.append(CheckResult(f"reverse({name})", True, resolved[name]))
            except Exception as e:
                results.append(CheckResult(f"reverse({name})", False, repr(e)))

        poz = Pozicija.objects.order_by("id").first()
        if poz is None:
            poz = Pozicija.objects.create(
                klientas="SMOKE_TEST_TEMP",
                projektas="SMOKE_TEST_TEMP",
                poz_kodas="SMOKE_TEST_TEMP",
                poz_pavad="SMOKE_TEST_TEMP",
            )
            created_here = True
            temp_poz_id = poz.id
            results.append(CheckResult("create temporary Pozicija", True, f"id={poz.id}"))

        # Reverse su pk
        for name, kwargs in (
            ("pozicijos:detail", {"pk": poz.id}),
            ("pozicijos:edit", {"pk": poz.id}),
            ("pozicijos:brezinys_upload", {"pk": poz.id}),
            ("pozicijos:brezinys_3d", {"pk": poz.id, "bid": 1}),  # bid gali neegzistuoti
            ("pozicijos:proposal_prepare", {"pk": poz.id}),
            ("pozicijos:pdf", {"pk": poz.id}),
            ("pozicijos:kainos_list", {"pk": poz.id}),
        ):
            try:
                resolved[name] = reverse(name, kwargs=kwargs)
                results.append(CheckResult(f"reverse({name})", True, resolved[name]))
            except Exception as e:
                results.append(CheckResult(f"reverse({name})", False, repr(e)))

        c = Client()

        def get_ok(name: str, url: str) -> None:
            """
            200/302 – gyva.
            404 leidžiam tik ten, kur 404 reiškia “nėra duomenų”,
            pvz., brezinys_3d su dummy bid.
            """
            try:
                r = c.get(url)
                if r.status_code in (200, 302):
                    results.append(CheckResult(f"GET {name}", True, f"{r.status_code} {url}"))
                    return

                if name == "pozicijos:brezinys_3d" and r.status_code == 404:
                    results.append(CheckResult(f"GET {name}", True, f"404 (no drawing in DB) {url}"))
                    return

                results.append(CheckResult(f"GET {name}", False, f"{r.status_code} {url}"))
            except Exception as e:
                results.append(CheckResult(f"GET {name}", False, repr(e)))

        # GET baziniai
        for key in ("pozicijos:list", "pozicijos:tbody", "pozicijos:stats", "pozicijos:import_csv"):
            if key in resolved:
                get_ok(key, resolved[key])

        # GET su pk
        for key in (
            "pozicijos:detail",
            "pozicijos:edit",
            "pozicijos:proposal_prepare",
            "pozicijos:pdf",
            "pozicijos:kainos_list",
            "pozicijos:brezinys_3d",
        ):
            if key in resolved:
                get_ok(key, resolved[key])

    finally:
        # Smoke testas negali palikti testinės Pozicija DB įrašo.
        if created_here and temp_poz_id is not None:
            try:
                deleted_count, _ = Pozicija.objects.filter(id=temp_poz_id).delete()
                results.append(
                    CheckResult(
                        "cleanup temporary Pozicija",
                        deleted_count > 0,
                        f"id={temp_poz_id}, deleted={deleted_count}",
                    )
                )
            except Exception as e:
                results.append(CheckResult("cleanup temporary Pozicija", False, repr(e)))

    print("\n== Smoke test results ==")
    for r in results:
        _print(r)

    failed = [r for r in results if not r.ok]
    print("\n== Summary ==")
    print(f"Total: {len(results)} | Failed: {len(failed)}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
