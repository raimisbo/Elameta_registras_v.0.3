# detaliu_registras/importers.py
import csv
from io import TextIOWrapper
from datetime import datetime
from decimal import Decimal, InvalidOperation
from django.db import transaction
from django.utils import timezone
from .models import Klientas, Projektas, Detale, Uzklausa

DATE_INPUTS = ("%Y-%m-%d", "%Y/%m/%d", "%d.%m.%Y")

def _parse_decimal(val, decimal_comma=False):
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    if decimal_comma:
        s = s.replace(".", "").replace(",", ".") if s.count(",") == 1 else s.replace(",", ".")
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None

def _parse_date(val):
    if not val:
        return None
    s = str(val).strip()
    if not s:
        return None
    for fmt in DATE_INPUTS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None

def iter_rows(file, encoding="utf-8", delimiter=None):
    """Grąžina (row_idx, dict) su normalizuotais raktų pavadinimais."""
    wrap = TextIOWrapper(file, encoding=encoding, newline="")
    sample = wrap.read(2048)
    wrap.seek(0)
    if delimiter is None:
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=";,")
            delimiter = dialect.delimiter
        except Exception:
            delimiter = ";"
    reader = csv.DictReader(wrap, delimiter=delimiter)
    # normalizuojam antraštes
    field_map = {name.strip().lower(): name for name in reader.fieldnames or []}
    wanted = ["klientas","projektas","detales_pavadinimas","brezinio_nr","metalas","svoris_kg","plotas_m2","data"]
    missing = [k for k in ("klientas","projektas","detales_pavadinimas","brezinio_nr") if k not in field_map]
    # detales_pavadinimas ir brezinio_nr – bent vienas turi būti
    yield -1, {"_delimiter": delimiter, "_missing_required": missing}
    for idx, row in enumerate(reader, start=2):  # 1 = header
        norm = {k: row.get(field_map.get(k, k)) for k in field_map}
        yield idx, {k: (norm.get(k) or "").strip() for k in wanted}

# detaliu_registras/importers.py (tęsinys)
def import_uzklausos_csv(uploaded_file, *, dry_run=True, encoding="utf-8", delimiter=None, decimal_comma=False, create_missing=True):
    """
    Grąžina dict: {
      "created": int, "updated": int, "skipped": int,
      "errors": [ (row_idx, "klaidos tekstas"), ... ],
      "delimiter": ";"
    }
    """
    stats = dict(created=0, updated=0, skipped=0, errors=[], delimiter=None)
    rows = iter_rows(uploaded_file, encoding=encoding, delimiter=delimiter)
    header_idx, header_info = next(rows)
    stats["delimiter"] = header_info.get("_delimiter")
    if header_info.get("_missing_required"):
        stats["errors"].append((1, f"Trūksta stulpelių: {', '.join(header_info['_missing_required'])}"))
        return stats

    @transaction.atomic
    def _do_import():
        for row_idx, data in rows:
            if not data:
                stats["skipped"] += 1
                continue
            klientas_v = data.get("klientas")
            projektas_v = data.get("projektas")
            det_pav = data.get("detales_pavadinimas") or ""
            brezinys = data.get("brezinio_nr") or ""
            metalas = data.get("metalas") or ""
            svoris = _parse_decimal(data.get("svoris_kg"), decimal_comma=decimal_comma)
            plotas = _parse_decimal(data.get("plotas_m2"), decimal_comma=decimal_comma)
            data_dt = _parse_date(data.get("data")) or timezone.now()

            if not klientas_v or not projektas_v:
                stats["errors"].append((row_idx, "Privalomi: klientas, projektas"))
                stats["skipped"] += 1
                continue

            # 1) Klientas
            kl = Klientas.objects.filter(vardas__iexact=klientas_v).first()
            if not kl:
                if create_missing:
                    kl = Klientas.objects.create(vardas=klientas_v)
                else:
                    stats["errors"].append((row_idx, f"Nerastas klientas: {klientas_v}"))
                    stats["skipped"] += 1
                    continue

            # 2) Projektas
            pr = Projektas.objects.filter(klientas=kl, pavadinimas__iexact=projektas_v).first()
            if not pr:
                if create_missing:
                    pr = Projektas.objects.create(klientas=kl, pavadinimas=projektas_v)
                else:
                    stats["errors"].append((row_idx, f"Nerastas projektas: {projektas_v} (klientas: {klientas_v})"))
                    stats["skipped"] += 1
                    continue

            # 3) Detalė
            det = None
            if brezinys:
                det = Detale.objects.filter(projektas=pr, brezinio_nr__iexact=brezinys).first()
            if not det and det_pav:
                det = Detale.objects.filter(projektas=pr, pavadinimas__iexact=det_pav).first()
            if not det:
                if create_missing:
                    det = Detale.objects.create(projektas=pr, pavadinimas=det_pav or brezinys, brezinio_nr=brezinys or None)
                else:
                    stats["errors"].append((row_idx, f"Nerasta detalė (pavadinimas: '{det_pav}', brėžinys: '{brezinys}')"))
                    stats["skipped"] += 1
                    continue

            # 3.1) Specifikacija (jei yra modelis ir reikšmės)
            # Saugu bandyti, jei to modelio neturite – tiesiog praleis
            try:
                spec = getattr(det, "specifikacija", None)
                if (metalas or svoris is not None or plotas is not None):
                    if not spec:
                        from .models import DetalesSpecifikacija
                        spec = DetalesSpecifikacija.objects.create(detale=det)
                    if metalas: spec.metalas = metalas
                    if svoris is not None: spec.svoris_kg = svoris
                    if plotas is not None: spec.plotas_m2 = plotas
                    spec.save()
            except Exception:
                pass  # jei nėra modelio, ignoruojam

            # 4) Užklausa — ieškom, ar tokia jau yra (pagal detale + data dienos tikslumu)
            uzk = (
                Uzklausa.objects
                .filter(detale=det)
                .order_by("-id")
                .first()
            )

            if uzk:
                # atnaujinam tik datą, jei ateina senesnė/tuščia — nieko
                changed = False
                if uzk.data is None and data_dt:
                    uzk.data = data_dt
                    changed = True
                if changed:
                    uzk.save(update_fields=["data"])
                    stats["updated"] += 1
                else:
                    stats["skipped"] += 1
            else:
                Uzklausa.objects.create(klientas=kl, projektas=pr, detale=det, data=data_dt)
                stats["created"] += 1

        if dry_run:
            raise transaction.TransactionManagementError("DRY_RUN")  # rollback

    try:
        _do_import()
    except transaction.TransactionManagementError as e:
        if str(e) != "DRY_RUN":
            stats["errors"].append((0, f"Sisteminė klaida: {e}"))

    return stats
