from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pozicijos", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="pozicija",
            name="brezinio_nr",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Brėžinio Nr."),
        ),
        migrations.AddField(
            model_name="pozicija",
            name="ieinantis_kodas",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Įeinantis kodas"),
        ),
        migrations.AddField(
            model_name="pozicija",
            name="iseinantis_kodas",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Išeinantis kodas"),
        ),
    ]
