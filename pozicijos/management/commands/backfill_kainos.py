from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "LEGACY: ši komanda nebenaudojama. "
        "Senas DB laukas Pozicija.kaina_eur buvo pakeistas į @property, "
        "o kainos dabar saugomos per KainosEilute."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Palikta tik suderinamumui; komanda vis tiek nevykdoma.",
        )

    def handle(self, *args, **options):
        raise CommandError(
            "backfill_kainos yra legacy komanda ir dabartinėje schemoje nebegali būti vykdoma. "
            "Pozicija.kaina_eur nebėra DB laukas. Kainas kurk/redaguok per KainosEilute."
        )
