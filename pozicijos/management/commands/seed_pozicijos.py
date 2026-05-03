from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from pozicijos.models import KainosEilute, Pozicija


SAMPLE = [
    {
        "pozicija": {
            "klientas": "UAB Klientas A",
            "projektas": "Projektas A",
            "poz_kodas": "DA-0001",
            "poz_pavad": "Laikiklis A",
            "metalas": "Plienas",
            "plotas": "1.25 m2",
            "svoris": "3.4 kg",
            "ktl_kabinimo_budas": "Kablys",
            "ktl_kabinimas_reme_txt": "3-4-2",
            "ktl_detaliu_kiekis_reme": 24,
            "ktl_faktinis_kiekis_reme": 22,
            "paslauga_ktl": True,
            "paslauga_miltai": True,
            "paslauga_paruosimas": True,
            "paruosimas": "Smėliavimas SA2.5",
            "padengimas": "KTL + miltelinis",
            "padengimo_standartas": "ISO 12944 C3",
            "spalva": "RAL9005",
            "maskavimas": "Sriegiai užmaskuoti",
            "testai_kokybe": "Adhezijos testas OK",
            "pakavimo_tipas": "standartinis",
            "pakavimas": "Dėžės",
            "instrukcija": "Sutvirtinti kampuose",
            "pastabos": "Pirmas bandymas",
        },
        "kaina": Decimal("12.50"),
    },
    {
        "pozicija": {
            "klientas": "UAB Klientas B",
            "projektas": "Projektas B",
            "poz_kodas": "DA-0002",
            "poz_pavad": "Dangtelis B",
            "metalas": "Aliuminis",
            "plotas": "0.95 m2",
            "svoris": "2.1 kg",
            "ktl_kabinimo_budas": "Vielutė",
            "ktl_kabinimas_reme_txt": "2-3-2",
            "ktl_detaliu_kiekis_reme": 18,
            "ktl_faktinis_kiekis_reme": 18,
            "paslauga_miltai": True,
            "paruosimas": "Fosfatavimas",
            "padengimas": "Miltelinis",
            "padengimo_standartas": "Qualicoat",
            "spalva": "RAL9010",
            "testai_kokybe": "Druskos rūko testas 240h",
            "pakavimo_tipas": "standartinis",
            "pakavimas": "Euro padėklas",
        },
        "kaina": Decimal("9.80"),
    },
    {
        "pozicija": {
            "klientas": "UAB Klientas A",
            "projektas": "Projektas C",
            "poz_kodas": "DA-0003",
            "poz_pavad": "Rėmelis C",
            "metalas": "Nerūdijantis plienas",
            "plotas": "1.80 m2",
            "svoris": "4.2 kg",
            "ktl_kabinimo_budas": "Kablys",
            "ktl_kabinimas_reme_txt": "4-4-3",
            "ktl_detaliu_kiekis_reme": 30,
            "ktl_faktinis_kiekis_reme": 28,
            "paslauga_ktl": True,
            "paruosimas": "Smėliavimas",
            "padengimas": "KTL",
            "padengimo_standartas": "ISO 12944 C4",
            "spalva": "RAL7016",
            "maskavimas": "Kraštai",
            "pakavimo_tipas": "standartinis",
            "pakavimas": "Dėžės",
            "instrukcija": "Dvigubas sluoksnis kampuose",
            "pastabos": "Skubus",
        },
        "kaina": Decimal("15.30"),
    },
]


class Command(BaseCommand):
    help = "Sukuria kelis pavyzdinius Pozicija įrašus pagal dabartinę modelio schemą."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Nieko neišsaugoti, tik parodyti, kas būtų sukurta.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        created_pozicijos = 0
        existing_pozicijos = 0
        created_kainos = 0
        existing_kainos = 0

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY-RUN: duomenys nebus išsaugoti."))

        for item in SAMPLE:
            row = item["pozicija"]
            kaina = item["kaina"]
            poz_kodas = row["poz_kodas"]

            existing = Pozicija.objects.filter(poz_kodas=poz_kodas).first()

            if existing:
                obj = existing
                existing_pozicijos += 1
                self.stdout.write(f"[EXISTS] Pozicija {poz_kodas}")
            else:
                created_pozicijos += 1
                self.stdout.write(f"[CREATE] Pozicija {poz_kodas}")

                if not dry_run:
                    obj = Pozicija.objects.create(**row)
                else:
                    obj = None

            if dry_run:
                self.stdout.write(f"[DRY-RUN] KainosEilute {poz_kodas}: {kaina} EUR")
                continue

            price_exists = obj.kainos_eilutes.filter(busena="aktuali").exists()
            if price_exists:
                existing_kainos += 1
                self.stdout.write(f"[EXISTS] Aktualios kainos eilutė {poz_kodas}")
            else:
                KainosEilute.objects.create(
                    pozicija=obj,
                    kaina=kaina,
                    matas="vnt.",
                    yra_fiksuota=False,
                    busena="aktuali",
                    prioritetas=100,
                    pastaba="Sugeneruota per seed_pozicijos komandą",
                )
                created_kainos += 1
                self.stdout.write(f"[CREATE] KainosEilute {poz_kodas}: {kaina} EUR")

        if dry_run:
            transaction.set_rollback(True)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Santrauka:"))
        self.stdout.write(f"  Pozicijos sukurtos: {created_pozicijos}")
        self.stdout.write(f"  Pozicijos jau buvo: {existing_pozicijos}")
        self.stdout.write(f"  Kainos sukurtos: {created_kainos}")
        self.stdout.write(f"  Kainos jau buvo: {existing_kainos}")
