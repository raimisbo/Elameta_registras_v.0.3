import sys
from django.core.management.base import BaseCommand, CommandError
from detaliu_registras.importers import iter_rows

class Command(BaseCommand):
    help = "Patikrina CSV antraštes ir kelias pirmas eilutes (neimportuoja duomenų)."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", help="Kelias iki CSV failo")
        parser.add_argument("--encoding", default="utf-8")
        parser.add_argument("--delimiter", default="", help="Priverstinis skirtukas (pagal nutylėjimą aptinka automatiškai)")

    def handle(self, *args, **opts):
        path = opts["csv_path"]
        encoding = opts["encoding"]
        delimiter = opts["delimiter"] or None

        try:
            f = open(path, "rb")
        except OSError as e:
            raise CommandError(f"Nepavyko atidaryti failo: {e}")

        rows = iter_rows(f, encoding=encoding, delimiter=delimiter)
        header_idx, header_info = next(rows)
        actual_delim = header_info.get("_delimiter") or "?"
        missing = header_info.get("_missing_required", [])

        self.stdout.write(self.style.NOTICE(f"Skirtukas: “{actual_delim}”"))
        if missing:
            self.stdout.write(self.style.ERROR(f"Trūksta privalomų stulpelių: {', '.join(missing)}"))
        else:
            self.stdout.write(self.style.SUCCESS("Visi privalomi stulpeliai rasti."))

        # parodyti pirmas 5 eilutes
        for idx, row in rows:
            if idx > 6:  # header (1) + 5 rows max
                break
            self.stdout.write(f"Eil. {idx}: {row}")

        f.close()
