import sys
from django.core.management.base import BaseCommand, CommandError
from detaliu_registras.importers import import_uzklausos_csv

class Command(BaseCommand):
    help = "Importuoja užklausas iš CSV (žr. dokumentaciją šablonui)."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", help="Kelias iki CSV failo")
        parser.add_argument("--encoding", default="utf-8")
        parser.add_argument("--delimiter", default="")
        parser.add_argument("--decimal-comma", action="store_true")
        parser.add_argument("--no-create-missing", action="store_true", help="Nekurti trūkstamų klientų/projektų/detalių")
        parser.add_argument("--apply", action="store_true", help="Pagal nutylėjimą daro DRY-RUN; su --apply įrašys į DB")

    def handle(self, *args, **opts):
        path = opts["csv_path"]
        try:
            f = open(path, "rb")
        except OSError as e:
            raise CommandError(f"Nepavyko atidaryti failo: {e}")

        stats = import_uzklausos_csv(
            f,
            dry_run=not opts["apply"],
            encoding=opts["encoding"],
            delimiter=opts["delimiter"] or None,
            decimal_comma=opts["decimal_comma"],
            create_missing=not opts["no_create_missing"],
        )
        f.close()

        self.stdout.write(self.style.NOTICE(f"Delimiter: {stats.get('delimiter',';')}"))
        for row, err in stats["errors"]:
            self.stdout.write(self.style.ERROR(f"Eil. {row}: {err}"))

        self.stdout.write(self.style.SUCCESS(
            f"Sukurta: {stats['created']}, atnaujinta: {stats['updated']}, praleista: {stats['skipped']}{' (DRY-RUN)' if not opts['apply'] else ''}"
        ))

        if stats["errors"] and opts["apply"]:
            self.stdout.write(self.style.WARNING("Buvo klaidų — peržiūrėk aukščiau."))
