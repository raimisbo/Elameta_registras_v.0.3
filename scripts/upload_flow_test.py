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


def _cleanup_stale_test_uploads(Pozicija, PozicijosBrezinys) -> int:
    """
    Išvalo ankstesnių blogos versijos upload_flow_test paliktus artefaktus.
    Ribojam pagal pavadinimą ir failo vardą, kad neliestų normalių naudotojo brėžinių.
    """
    removed = 0

    stale_breziniai = PozicijosBrezinys.objects.filter(
        pavadinimas="SMOKE",
        failas__icontains="smoke_upload",
    )

    for b in stale_breziniai:
        b.delete()
        removed += 1

    stale_pozicijos = Pozicija.objects.filter(
        klientas="UPLOAD_TEST",
        projektas="UPLOAD_TEST",
    )

    for p in stale_pozicijos:
        p.delete()
        removed += 1

    return removed


def main() -> int:
    import django
    django.setup()

    from django.conf import settings
    if "testserver" not in settings.ALLOWED_HOSTS:
        settings.ALLOWED_HOSTS.append("testserver")

    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Permission
    from django.core.files.uploadedfile import SimpleUploadedFile
    from django.test import Client
    from django.urls import reverse

    from pozicijos.models import Pozicija, PozicijosBrezinys

    results: list[CheckResult] = []

    removed_stale = _cleanup_stale_test_uploads(Pozicija, PozicijosBrezinys)
    results.append(CheckResult("cleanup stale test uploads", True, f"removed={removed_stale}"))

    poz = None

    try:
        # Testui kuriam atskirą laikiną poziciją, kad neprikabintume SMOKE failų prie realių įrašų.
        poz = Pozicija.objects.create(
            klientas="UPLOAD_TEST",
            projektas="UPLOAD_TEST",
            poz_kodas="UPLOAD_TEST",
            poz_pavad="UPLOAD_TEST",
        )
        results.append(CheckResult("create temporary Pozicija", True, f"id={poz.id}"))

        try:
            url = reverse("pozicijos:brezinys_upload", kwargs={"pk": poz.id})
            results.append(CheckResult("reverse upload endpoint", True, url))
        except Exception as e:
            results.append(CheckResult("reverse upload endpoint", False, repr(e)))
            raise

        User = get_user_model()
        user, _ = User.objects.get_or_create(username="upload-flow-test")
        user.is_active = True
        user.is_staff = False
        user.is_superuser = False
        user.set_unusable_password()
        user.save(update_fields=["is_active", "is_staff", "is_superuser", "password"])

        upload_perm = Permission.objects.get(
            content_type__app_label="pozicijos",
            codename="add_pozicijosbrezinys",
        )
        user.user_permissions.set([upload_perm])
        user.groups.clear()

        c = Client()
        c.force_login(user)

        before = PozicijosBrezinys.objects.filter(pozicija=poz).count()

        upload = SimpleUploadedFile(
            "smoke_upload.txt",
            b"SMOKE UPLOAD CONTENT",
            content_type="text/plain",
        )

        try:
            r = c.post(
                url,
                data={
                    "pavadinimas": "SMOKE",
                    "failas": upload,
                },
                follow=False,
            )
            ok_status = r.status_code in (200, 302)
            results.append(CheckResult("POST upload (status)", ok_status, f"{r.status_code} {url}"))
        except Exception as e:
            results.append(CheckResult("POST upload (request)", False, repr(e)))

        after = PozicijosBrezinys.objects.filter(pozicija=poz).count()
        results.append(CheckResult("DB insert check", after == before + 1, f"before={before}, after={after}"))

        total_for_temp = PozicijosBrezinys.objects.filter(pozicija=poz).count()
        results.append(CheckResult("temporary PozicijosBrezinys count", total_for_temp == 1, f"count={total_for_temp}"))

    finally:
        # Svarbiausia šito pataisymo dalis:
        # testas privalo išvalyti viską, ką pats sukūrė.
        if poz is not None:
            try:
                PozicijosBrezinys.objects.filter(pozicija=poz).delete()
                poz.delete()
                results.append(CheckResult("cleanup temporary upload data", True, f"pozicija_id={poz.id}"))
            except Exception as e:
                results.append(CheckResult("cleanup temporary upload data", False, repr(e)))

    print("\n== Upload flow test results ==")
    for r in results:
        _print(r)

    failed = [r for r in results if not r.ok]

    print("\n== Summary ==")
    print(f"Total: {len(results)} | Failed: {len(failed)}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
