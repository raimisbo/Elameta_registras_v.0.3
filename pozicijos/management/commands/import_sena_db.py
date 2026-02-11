import sqlite3
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from pozicijos.models import Pozicija, KainosEilute


class Command(BaseCommand):
    help = "Importuoja seną detalių registro DB (SQLite) į naują pozicijų struktūrą."

    def add_arguments(self, parser):
        parser.add_argument("--db", dest="db_path", required=True, help="Kelias iki seno db.sqlite3 failo")

    @staticmethod
    def _cols(cur, table_name):
        cur.execute(f"PRAGMA table_info({table_name})")
        return {row[1] for row in cur.fetchall()}  # row[1] = column name

    @staticmethod
    def _pick(row_dict, *names, default=None):
        for n in names:
            if n in row_dict and row_dict[n] not in (None, ""):
                return row_dict[n]
        return default

    def handle(self, *args, **options):
        db_file = Path(options["db_path"])
        if not db_file.exists():
            raise CommandError(f"Failas nerastas: {db_file}")

        self.stdout.write(self.style.NOTICE(f"Jungiuosi prie {db_file} ..."))
        conn = sqlite3.connect(str(db_file))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        try:
            # Patikrinam ar reikalingos lentelės egzistuoja
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {r[0] for r in cur.fetchall()}
            required = {"detaliu_registras_detale", "detaliu_registras_projektas", "detaliu_registras_klientas"}
            missing = required - tables
            if missing:
                raise CommandError(f"Trūksta lentelių senoje DB: {', '.join(sorted(missing))}")

            det_cols = self._cols(cur, "detaliu_registras_detale")
            proj_cols = self._cols(cur, "detaliu_registras_projektas")
            kli_cols = self._cols(cur, "detaliu_registras_klientas")

            # Klientai
            kli_id = "id"
            kli_name = "vardas" if "vardas" in kli_cols else ("pavadinimas" if "pavadinimas" in kli_cols else None)
            if kli_name is None:
                raise CommandError("detaliu_registras_klientas neturi nei 'vardas', nei 'pavadinimas' stulpelio")
            cur.execute(f"SELECT {kli_id}, {kli_name} FROM detaliu_registras_klientas")
            klientai = {row[0]: row[1] for row in cur.fetchall()}

            # Projektai
            proj_name = "pavadinimas" if "pavadinimas" in proj_cols else ("vardas" if "vardas" in proj_cols else None)
            proj_client_fk = "klientas_id" if "klientas_id" in proj_cols else None
            if proj_name is None:
                raise CommandError("detaliu_registras_projektas neturi pavadinimo stulpelio")
            if proj_client_fk is None:
                raise CommandError("detaliu_registras_projektas neturi 'klientas_id' stulpelio")

            cur.execute(f"SELECT id, {proj_name}, {proj_client_fk} FROM detaliu_registras_projektas")
            projektai = {}
            for row in cur.fetchall():
                projektai[row[0]] = {"pavadinimas": row[1], "klientas": klientai.get(row[2], "")}

            # Detalės: renkam tik egzistuojančius stulpelius
            wanted = [
                "id", "pavadinimas", "brezinio_nr", "projektas_id",
                "plotas", "svoris", "pakavimas", "pastabos",
                "aprasymas", "komentaras", "kodas"
            ]
            present = [c for c in wanted if c in det_cols]
            if "id" not in present:
                raise CommandError("detaliu_registras_detale neturi 'id' stulpelio")

            cur.execute(f"SELECT {', '.join(present)} FROM detaliu_registras_detale")
            detales = cur.fetchall()

            # Kainų lentelė optional
            has_kaina_table = "detaliu_registras_kaina" in tables
            k_cols = self._cols(cur, "detaliu_registras_kaina") if has_kaina_table else set()

            imported = 0
            prices_created = 0

            with transaction.atomic():
                for r in detales:
                    d = dict(r)

                    d_id = d.get("id")
                    pavadinimas = self._pick(d, "pavadinimas", "aprasymas", default="")
                    brezinio_nr = self._pick(d, "brezinio_nr", "kodas", default=None)
                    projektas_id = d.get("projektas_id")

                    plotas = d.get("plotas", "")
                    svoris = d.get("svoris", "")
                    pakavimas = d.get("pakavimas", "")
                    pastabos = self._pick(d, "pastabos", "komentaras", default="")

                    proj = projektai.get(projektas_id, {})
                    projektas_pav = proj.get("pavadinimas", "") or ""
                    klientas_pav = proj.get("klientas", "") or ""

                    poz_kodas = (brezinio_nr or f"DET-{d_id}").strip()

                    poz, created = Pozicija.objects.get_or_create(
                        poz_kodas=poz_kodas,
                        defaults={
                            "klientas": klientas_pav,
                            "projektas": projektas_pav,
                            "poz_pavad": (pavadinimas or "").strip(),
                            "plotas": str(plotas) if plotas not in (None, "") else "",
                            "svoris": str(svoris) if svoris not in (None, "") else "",
                            "pakavimas": (pakavimas or "").strip(),
                            "pastabos": (pastabos or "").strip(),
                        },
                    )
                    if created:
                        imported += 1

                    if has_kaina_table:
                        # nustatom ryšio FK stulpelį (gali būti su ė)
                        fk_col = None
                        for candidate in ['detalė_id', 'detale_id', 'detales_id', 'detalės_id']:
                            if candidate in k_cols:
                                fk_col = candidate
                                break

                        if fk_col:
                            busena_col = "busena" if "busena" in k_cols else None
                            suma_col = "suma" if "suma" in k_cols else ("kaina" if "kaina" in k_cols else None)
                            fiks_col = "yra_fiksuota" if "yra_fiksuota" in k_cols else None
                            nuo_col = "kiekis_nuo" if "kiekis_nuo" in k_cols else None
                            iki_col = "kiekis_iki" if "kiekis_iki" in k_cols else None
                            fkiek_col = "fiksuotas_kiekis" if "fiksuotas_kiekis" in k_cols else None
                            mat_col = "kainos_matas" if "kainos_matas" in k_cols else ("matas" if "matas" in k_cols else None)

                            select_cols = ["id"]
                            for c in [busena_col, suma_col, fiks_col, nuo_col, iki_col, fkiek_col, mat_col]:
                                if c and c not in select_cols:
                                    select_cols.append(c)

                            q = f'SELECT {", ".join(select_cols)} FROM detaliu_registras_kaina WHERE "{fk_col}" = ?'
                            cur.execute(q, (d_id,))
                            for krow in cur.fetchall():
                                kd = dict(krow)
                                suma = kd.get(suma_col) if suma_col else None
                                if suma in (None, ""):
                                    continue

                                KainosEilute.objects.create(
                                    pozicija=poz,
                                    kaina=suma,
                                    busena=(kd.get(busena_col) or "aktuali") if busena_col else "aktuali",
                                    yra_fiksuota=bool(kd.get(fiks_col)) if fiks_col else False,
                                    kiekis_nuo=kd.get(nuo_col) if nuo_col else None,
                                    kiekis_iki=kd.get(iki_col) if iki_col else None,
                                    fiksuotas_kiekis=kd.get(fkiek_col) if fkiek_col else None,
                                    matas=(kd.get(mat_col) or "vnt.") if mat_col else "vnt.",
                                )
                                prices_created += 1

            self.stdout.write(self.style.SUCCESS(f"Importuota pozicijų: {imported}, kainų eilučių: {prices_created}"))

        except sqlite3.Error as e:
            raise CommandError(f"SQLite klaida: {e}") from e
        finally:
            conn.close()
