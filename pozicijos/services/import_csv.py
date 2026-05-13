# pozicijos/services/import_csv.py
from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass, field
from io import TextIOWrapper
from typing import List

from django.core.exceptions import ValidationError
from django.db import models

from ..models import Pozicija
from ..schemas.columns import COLUMNS



LEGACY_HEADER_ALIASES = {
    # Senas / legacy CSV formatas
    "klientas_pavadinimas": "klientas",
    "projektas_pavadinimas": "projektas",

    # Svarbu: legacy faile šitas laukas tampa pagrindiniu importo raktu
    "detale_brezinio_nr": "poz_kodas",

    "detale_pavadinimas": "poz_pavad",
    "detale_plotas": "plotas",
    "detale_svoris": "svoris",
    "detale_kiekis_metinis": "metinis_kiekis_nuo",
    "detale_kiekis_partijai": "partiju_dydziai",
    "detale_danga": "padengimas",
    "detale_standartas": "padengimo_standartas",
    "detale_kabinimo_tipas": "ktl_kabinimo_budas",
    "detale_kabinimas_xyz": "ktl_kabinimas_reme_txt",
    "detale_kiekis_reme": "ktl_detaliu_kiekis_reme",
    "detale_faktinis_kiekis_reme": "ktl_faktinis_kiekis_reme",
    "detale_pakavimas": "pakavimo_tipas",
}


@dataclass
class ImportErrorRow:
    row_number: int
    message: str


@dataclass
class ImportResult:
    total: int = 0
    created: int = 0
    updated: int = 0
    errors: List[ImportErrorRow] = field(default_factory=list)


def _build_header_map(fieldnames: list[str]) -> dict[str, str]:
    """
    Susieja CSV stulpelius su Pozicija modelio laukais:

      - jeigu header = 'poz_kodas' → 'poz_kodas'
      - jeigu header = 'Klientas' → žiūrim COLUMNS, randam key 'klientas'
      - jeigu header = 'Detalės kodas' → 'poz_kodas'
      - visi nepažįstami headeriai ignoruojami
    """
    label_to_key = {c["label"]: c["key"] for c in COLUMNS}
    label_to_key.update({
        "Kodas": "poz_kodas",
        "Detalės kodas": "poz_kodas",
        "Pozicijos kodas": "poz_kodas",
    })

    label_to_key.update(LEGACY_HEADER_ALIASES)

    key_set = {c["key"] for c in COLUMNS}

    model_fields = {
        f.name: f
        for f in Pozicija._meta.get_fields()
        if getattr(f, "attname", None)
    }

    mapping: dict[str, str] = {}
    for col in fieldnames or []:
        field_name = None
        if col in key_set:
            field_name = col
        elif col in label_to_key:
            field_name = label_to_key[col]
        if not field_name:
            continue
        if field_name in model_fields:
            mapping[col] = field_name
    return mapping


def _empty_value_for_field(field):
    """
    Teisinga tuščio CSV langelio reikšmė pagal Django lauko tipą.

    - null=True laukai -> None
    - CharField/TextField tipo laukai -> ""
    - laukai su default -> field.get_default()
    - kiti laukai -> None, kad full_clean() pagautų netinkamus atvejus
    """
    if getattr(field, "null", False):
        return None

    if isinstance(field, (models.CharField, models.TextField)):
        return ""

    if field.has_default():
        return field.get_default()

    if getattr(field, "empty_strings_allowed", False):
        return ""

    return None


def _norm_text(value: str) -> str:
    """
    Normalizuotas tekstas palyginimams:
    - mažosios raidės
    - be lietuviškų diakritikų
    - be perteklinių tarpų
    """
    value = (value or "").casefold().strip()
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"\s+", " ", value)
    return value


def _choice_value_from_label(field, raw: str):
    """
    CSV eksportas rašo vartotojui matomus choice labelius:
      Palaidas, Standartinis, Nėra, Yra

    DB laukui reikia realių reikšmių:
      palaidas, standartinis, nera, yra
    """
    choices = getattr(field, "choices", None) or []
    if not choices:
        return None

    needle = _norm_text(raw)
    if not needle:
        return None

    for value, label in choices:
        if needle == _norm_text(str(value)) or needle == _norm_text(str(label)):
            return value

    return None


def _normalize_raw_for_field(field, raw: str) -> str:
    """
    Leidžia importuoti ir žmogui patogų mūsų eksporto formatą.
    """
    value = (raw or "").strip()

    if isinstance(field, models.IntegerField):
        # pvz. "1 d.d." -> "1"
        m = re.search(r"[+-]?\d+", value)
        if m:
            return m.group(0)

    if isinstance(field, models.DecimalField):
        # pvz. "24,0" -> "24.0"
        return value.replace(",", ".")

    return value


def _to_python_import_value(field, raw: str):
    choice_value = _choice_value_from_label(field, raw)
    if choice_value is not None:
        return choice_value

    normalized = _normalize_raw_for_field(field, raw)
    return field.to_python(normalized)


def import_pozicijos_from_csv(uploaded_file, *, dry_run: bool = False) -> ImportResult:
    """
    Vienkartinis migracijos importas.

    CSV header'iai turi būti **arba** modelio field'ai (poz_kodas, klientas, ...),
    **arba** COLUMNS label'ai (Klientas, Projektas, ...).

    'poz_kodas' / 'Kodas' naudojamas kaip unikalus raktas:
      - jei tokia pozicija yra -> atnaujinam laukus,
      - jei nėra -> sukuriam naują.

    Tušti langeliai nustatomi pagal lauko tipą:
      - null=True laukams -> None
      - CharField/TextField laukams -> ""
      - laukams su default -> default reikšmė
    """
    result = ImportResult()

    # failą paverčiam tekstu (UTF-8, leidžiam BOM)
    wrapper = TextIOWrapper(uploaded_file.file, encoding="utf-8-sig", newline="")

    sample = wrapper.read(4096)
    wrapper.seek(0)
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,")
        reader = csv.DictReader(wrapper, dialect=dialect)
    except csv.Error:
        # jei nepavyksta atspėti – laikom, kad skyriklis ';'
        reader = csv.DictReader(wrapper, delimiter=";")

    header_map = _build_header_map(reader.fieldnames or [])

    model_fields = {
        f.name: f
        for f in Pozicija._meta.get_fields()
        if getattr(f, "attname", None)
    }

    for row_idx, row in enumerate(reader, start=2):  # 1 eil. = header
        result.total += 1

        # Kodas yra unikalus raktas.
        # Svarbu: mūsų eksportas dažniausiai rašo vartotojui matomą headerį
        # „Detalės kodas“, todėl kodą imam per header_map, o ne tik per raw
        # row.get("poz_kodas").
        code_col = next(
            (col_name for col_name, field_name in header_map.items() if field_name == "poz_kodas"),
            None,
        )
        code = (row.get(code_col) if code_col else None) or row.get("poz_kodas") or row.get("Kodas") or ""
        code = str(code).strip()

        if not code:
            result.errors.append(
                ImportErrorRow(row_idx, "Trūksta 'poz_kodas' / 'Kodas' / 'Detalės kodas' / 'detale_brezinio_nr' reikšmės.")
            )
            continue

        obj, created = Pozicija.objects.get_or_create(poz_kodas=code, defaults={})

        # Legacy CSV: detale_brezinio_nr naudojam kaip poz_kodas,
        # bet kartu išsaugom ir kaip brėžinio numerį.
        legacy_brezinio_nr = str(row.get("detale_brezinio_nr") or "").strip()
        if legacy_brezinio_nr:
            obj.brezinio_nr = legacy_brezinio_nr

        # Legacy CSV: detale_danga dažnai būna KTL arba ZnPH+KTL.
        legacy_danga = str(row.get("detale_danga") or "").strip().casefold()
        if "ktl" in legacy_danga:
            obj.paslauga_ktl = True
        if "milt" in legacy_danga:
            obj.paslauga_miltai = True

        for col_name, field_name in header_map.items():
            if field_name == "poz_kodas":
                # kodą paliekam tokį, kokį naudojom get_or_create
                continue

            raw = (row.get(col_name) or "").strip()
            field = model_fields.get(field_name)
            if field is None:
                continue

            if raw == "":
                # Tuščias langelis negali būti aklai verčiamas į None:
                # CharField/TextField be null=True turi gauti "", ne NULL.
                setattr(obj, field_name, _empty_value_for_field(field))
                continue

            try:
                # modelio field'o konversija į tinkamą tipą.
                # Papildomai palaikom mūsų CSV eksporto žmogui rodomas reikšmes:
                # "1 d.d.", "24,0", "Palaidas", "Nėra" ir pan.
                value = _to_python_import_value(field, raw)
            except Exception as e:
                result.errors.append(
                    ImportErrorRow(
                        row_idx,
                        f"Laukas '{field_name}': neteisinga reikšmė '{raw}': {e}",
                    )
                )
                # lauko nesetinam, einam prie kitų
                continue

            if field_name == "padengimas" and "ktl" in str(value or "").strip().casefold():
                value = "BASF CG 570 RAL 9005"

            setattr(obj, field_name, value)

        try:
            if not dry_run:
                obj.full_clean()
                obj.save()
            if created:
                result.created += 1
            else:
                result.updated += 1
        except ValidationError as e:
            result.errors.append(
                ImportErrorRow(row_idx, f"Validacijos klaida: {e}")
            )
            continue

    wrapper.close()
    return result
