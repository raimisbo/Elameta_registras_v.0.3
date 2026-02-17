from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ("detaliu_registras", "0014_move_extra_kainos_to_legacy"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="kaina",
            constraint=models.UniqueConstraint(
                fields=["uzklausa"], name="unique_kaina_per_uzklausa"
            ),
        ),
    ]
