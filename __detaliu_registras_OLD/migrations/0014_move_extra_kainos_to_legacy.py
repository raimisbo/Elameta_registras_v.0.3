from django.db import migrations

def move_extras_to_legacy(apps, schema_editor):
    Kaina = apps.get_model("detaliu_registras", "Kaina")
    LegacyKaina = apps.get_model("detaliu_registras", "LegacyKaina")

    from collections import defaultdict
    groups = defaultdict(list)
    for k in Kaina.objects.all().order_by("id"):
        groups[k.uzklausa_id].append(k)

    for uzk_id, items in groups.items():
        if len(items) <= 1:
            continue

        aktualios = [k for k in items if getattr(k, "busena", None) == "aktuali"]
        canonical = max(aktualios or items, key=lambda x: x.pk)

        for k in items:
            if k.pk == canonical.pk:
                continue
            LegacyKaina.objects.create(
                uzklausa_id=k.uzklausa_id,
                suma=k.suma,
                valiuta=k.valiuta,
                busena=getattr(k, "busena", "sena") or "sena",
                yra_fiksuota=getattr(k, "yra_fiksuota", False),
                kiekis_nuo=getattr(k, "kiekis_nuo", None),
                kiekis_iki=getattr(k, "kiekis_iki", None),
                fiksuotas_kiekis=getattr(k, "fiksuotas_kiekis", None),
                kainos_matas=getattr(k, "kainos_matas", None),
                created=getattr(k, "created", None),
                updated=getattr(k, "updated", None),
            )
            k.delete()

    for k in Kaina.objects.all():
        if getattr(k, "busena", None) != "aktuali":
            k.busena = "aktuali"
            k.save(update_fields=["busena"])

class Migration(migrations.Migration):

    dependencies = [
        ("detaliu_registras", "0013_create_legacy_kaina"),
    ]

    operations = [
        migrations.RunPython(move_extras_to_legacy, migrations.RunPython.noop),
    ]
