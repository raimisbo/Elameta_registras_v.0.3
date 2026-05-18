from __future__ import annotations

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from pozicijos.models import (
    KainosEilute,
    MaskavimoEilute,
    MetaloStorisEilute,
    Pozicija,
    PozicijosBrezinys,
)


ROLE_DARBUOTOJAS = "Darbuotojas"
ROLE_PERZIURA = "Peržiūra"

ROLE_MODELS = [
    Pozicija,
    PozicijosBrezinys,
    KainosEilute,
    MaskavimoEilute,
    MetaloStorisEilute,
]


class Command(BaseCommand):
    help = "Sukuria bazines Registras roles per Django Groups."

    def handle(self, *args, **options):
        darbuotojas, _ = Group.objects.get_or_create(name=ROLE_DARBUOTOJAS)
        perziura, _ = Group.objects.get_or_create(name=ROLE_PERZIURA)

        darbuotojas.permissions.clear()
        perziura.permissions.clear()

        darbuotojas_perms = []
        perziura_perms = []

        for model in ROLE_MODELS:
            ct = ContentType.objects.get_for_model(model)

            for action in ("view", "add", "change"):
                perm = Permission.objects.get(
                    content_type=ct,
                    codename=f"{action}_{model._meta.model_name}",
                )
                darbuotojas_perms.append(perm)

            view_perm = Permission.objects.get(
                content_type=ct,
                codename=f"view_{model._meta.model_name}",
            )
            perziura_perms.append(view_perm)

        darbuotojas.permissions.set(darbuotojas_perms)
        perziura.permissions.set(perziura_perms)

        self.stdout.write(self.style.SUCCESS("Rolės sutvarkytos:"))
        self.stdout.write(f"  - {ROLE_DARBUOTOJAS}: view/add/change, be delete")
        self.stdout.write(f"  - {ROLE_PERZIURA}: tik view")
        self.stdout.write("  - Admin: superuser")
