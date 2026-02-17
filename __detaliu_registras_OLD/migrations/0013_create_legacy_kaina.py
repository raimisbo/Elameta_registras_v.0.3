from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    # ⬇️ Pakeiskite 'XXXX_last' į paskutinės jūsų app'o migracijos pavadinimą
    dependencies = [
        ("detaliu_registras", "0012_historicaldetale_historicaldetalespecifikacija_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="LegacyKaina",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created", models.DateTimeField(blank=True, null=True, auto_now_add=True)),
                ("updated", models.DateTimeField(blank=True, null=True, auto_now=True)),
                ("suma", models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)),
                ("valiuta", models.CharField(max_length=10, default="EUR")),
                ("busena", models.CharField(max_length=10, choices=[("aktuali", "Aktuali"), ("sena", "Sena")], default="sena")),
                ("yra_fiksuota", models.BooleanField(default=False)),
                ("kiekis_nuo", models.PositiveIntegerField(null=True, blank=True)),
                ("kiekis_iki", models.PositiveIntegerField(null=True, blank=True)),
                ("fiksuotas_kiekis", models.PositiveIntegerField(null=True, blank=True)),
                ("kainos_matas", models.CharField(max_length=10, null=True, blank=True, choices=[("vnt","Vnt"),("m2","m²"),("kg","kg"),("val","val.")])),
                ("uzklausa", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="legacy_kainos", to="detaliu_registras.uzklausa")),
            ],
            options={"ordering": ["-id"]},
        ),
    ]
