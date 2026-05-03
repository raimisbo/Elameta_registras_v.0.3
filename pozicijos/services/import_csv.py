# pozicijos/services/import_csv.py
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from io import TextIOWrapper
from typing import List

from django.core.exceptions import ValidationError
from django.db import models

from ..models import Pozicija
from ..schemas.columns import COLUMNS


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
      - visi nepažįstami headeriai ignoruojami
    """
    label_to_key = {c["label"]: c["key"] for c in COLUMNS}
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

        # kodas – bandome keliuos pavadinimuose
        code = (row.get("poz_kodas") or row.get("Kodas") or "").strip()
        if not code:
            result.errors.append(
                ImportErrorRow(row_idx, "Trūksta 'poz_kodas' / 'Kodas' reikšmės.")
            )
            continue

        obj, created = Pozicija.objects.get_or_create(poz_kodas=code, defaults={})

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
                # modelio field'o konversija į tinkamą tipą (Decimal, Date, int, ...)
                value = field.to_python(raw)
            except Exception as e:
                result.errors.append(
                    ImportErrorRow(
                        row_idx,
                        f"Laukas '{field_name}': neteisinga reikšmė '{raw}': {e}",
                    )
                )
                # lauko nesetinam, einam prie kitų
                continue

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
