# pozicijos/services/listing.py
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional

from django.db.models import Q, QuerySet

from ..schemas.columns import COLUMNS

# ============================================================================
# Virtual / UI key -> real ORM laukas
# ============================================================================
FIELD_KEY_MAP: Dict[str, str] = {
    "kaina_eur": "kainos_eilutes__kaina",
    "ktl_dangos_storis_display": "ktl_dangos_storis_txt",
    "miltai_dangos_storis_display": "miltai_dangos_storis_txt",
}

TEXT_FILTER_FIELDS = {
    "klientas",
    "projektas",
    "poz_kodas",
    "poz_pavad",
    "metalas",
    "padengimas",
    "padengimo_standartas",
    "spalva",
    "partiju_dydziai",
    "pakavimas",
    "maskavimas",
    "testai_kokybe",
    "ktl_dangos_storis_txt",
    "miltai_dangos_storis_txt",
}

DECIMAL_RANGE_FIELDS = {
    "plotas",
    "svoris",
    "kainos_eilutes__kaina",  # mapintas iš kaina_eur
}

INT_RANGE_FIELDS = {
    "atlikimo_terminas",
}


def _model_field_names(model) -> set[str]:
    """
    SVARBU: čia turi būti ir reverse relation vardai (pvz. 'kainos_eilutes'),
    todėl nenaudojam tik concrete=True.
    """
    names: set[str] = set()
    for f in model._meta.get_fields():
        n = getattr(f, "name", None)
        if n:
            names.add(n)
    return names


def resolve_field_key(raw_key: str, model_field_names: set[str]) -> Optional[str]:
    if not raw_key:
        return None

    mapped = FIELD_KEY_MAP.get(raw_key, raw_key)
    base = mapped.split("__", 1)[0]

    if base not in model_field_names:
        return None

    return mapped


def build_numeric_range_q(field_name: str, expr: str) -> Optional[Q]:
    """
    Decimal filtro interpretacija:
      10..20, >5, >=5, <12.5, <=12.5, 15, =15
    Jei formatas blogas -> None
    """
    raw = (expr or "").strip()
    if not raw:
        return None

    raw = raw.replace(",", ".")

    min_val = None
    max_val = None

    try:
        if ".." in raw:
            left, right = raw.split("..", 1)
            left = left.strip()
            right = right.strip()
            if left:
                min_val = Decimal(left)
            if right:
                max_val = Decimal(right)

        elif raw.startswith(">="):
            min_val = Decimal(raw[2:].strip())

        elif raw.startswith("<="):
            max_val = Decimal(raw[2:].strip())

        elif raw.startswith("="):
            v = Decimal(raw[1:].strip())
            min_val = v
            max_val = v

        elif raw[0] in (">", "<"):
            op = raw[0]
            val_str = raw[1:].strip()
            if not val_str:
                return None
            v = Decimal(val_str)
            if op == ">":
                min_val = v
            else:
                max_val = v

        else:
            v = Decimal(raw)
            min_val = v
            max_val = v

    except (InvalidOperation, ValueError, IndexError):
        return None

    q = Q()
    if min_val is not None:
        q &= Q(**{f"{field_name}__gte": min_val})
    if max_val is not None:
        q &= Q(**{f"{field_name}__lte": max_val})
    return q


def build_int_range_q(field_name: str, expr: str) -> Optional[Q]:
    """
    Integer filtro interpretacija:
      10..20, >5, >=5, <12, <=12, 15, =15
    Jei formatas blogas -> None
    """
    raw = (expr or "").strip()
    if not raw:
        return None

    min_val = None
    max_val = None

    try:
        if ".." in raw:
            left, right = raw.split("..", 1)
            left = left.strip()
            right = right.strip()
            if left:
                min_val = int(left)
            if right:
                max_val = int(right)

        elif raw.startswith(">="):
            min_val = int(raw[2:].strip())

        elif raw.startswith("<="):
            max_val = int(raw[2:].strip())

        elif raw.startswith("="):
            v = int(raw[1:].strip())
            min_val = v
            max_val = v

        elif raw[0] in (">", "<"):
            op = raw[0]
            val_str = raw[1:].strip()
            if not val_str:
                return None
            v = int(val_str)
            if op == ">":
                min_val = v
            else:
                max_val = v

        else:
            v = int(raw)
            min_val = v
            max_val = v

    except (ValueError, IndexError):
        return None

    q = Q()
    if min_val is not None:
        q &= Q(**{f"{field_name}__gte": min_val})
    if max_val is not None:
        q &= Q(**{f"{field_name}__lte": max_val})
    return q


# ============================================================================
# Matomi stulpeliai
# ============================================================================

def visible_cols_from_request(request) -> List[str]:
    known_keys = [c["key"] for c in COLUMNS]
    known_set = set(known_keys)
    default_keys = [c["key"] for c in COLUMNS if c.get("default")]

    if "cols" not in request.GET:
        return default_keys

    cols_param = request.GET.get("cols", "")
    raw_list = [c for c in (cols_param or "").split(",") if c]

    seen = set()
    cols: List[str] = []
    for k in raw_list:
        if k in known_set and k not in seen:
            cols.append(k)
            seen.add(k)

    return cols


# ============================================================================
# Filtrai
# ============================================================================

def apply_filters(qs: QuerySet, request) -> QuerySet:
    q_global = request.GET.get("q", "").strip()
    if q_global:
        qs = qs.filter(
            Q(klientas__icontains=q_global)
            | Q(projektas__icontains=q_global)
            | Q(poz_kodas__icontains=q_global)
            | Q(poz_pavad__icontains=q_global)
        )

    model_fields = _model_field_names(qs.model)

    for key, value in request.GET.items():
        if not key.startswith("f[") or not key.endswith("]"):
            continue

        raw_key = key[2:-1]
        value = (value or "").strip()
        if not raw_key or not value:
            continue

        field = resolve_field_key(raw_key, model_fields)
        if not field:
            # Nežinomas key -> ignoruojam
            continue

        # Tekstiniai laukai
        if field in TEXT_FILTER_FIELDS:
            qs = qs.filter(**{f"{field}__icontains": value})
            continue

        # Decimal range (įskaitant kainą)
        if field in DECIMAL_RANGE_FIELDS:
            q_num = build_numeric_range_q(field, value)
            if q_num is None:
                # Blogas numeric formatas => 0 rezultatų
                return qs.none()
            qs = qs.filter(q_num)
            if field.startswith("kainos_eilutes__"):
                qs = qs.distinct()
            continue

        # Integer range
        if field in INT_RANGE_FIELDS:
            q_int = build_int_range_q(field, value)
            if q_int is None:
                return qs.none()
            qs = qs.filter(q_int)
            continue

        # fallback exact
        qs = qs.filter(**{field: value})

    return qs


# ============================================================================
# Rikiavimas
# ============================================================================

def _sortable_fields(model_field_names: set[str]) -> Dict[str, str]:
    result: Dict[str, str] = {}

    for c in COLUMNS:
        if c.get("type") == "virtual":
            continue
        raw_key = c["key"]
        candidate = c.get("order_field", raw_key)

        resolved = resolve_field_key(candidate, model_field_names)
        if resolved:
            result[raw_key] = resolved

    # papildomi virtualūs key, kuriuos leidžiam rikiuoti
    for raw_key in ["kaina_eur", "ktl_dangos_storis_display", "miltai_dangos_storis_display"]:
        resolved = resolve_field_key(raw_key, model_field_names)
        if resolved:
            result[raw_key] = resolved

    return result


def apply_sorting(qs: QuerySet, request) -> QuerySet:
    sort = request.GET.get("sort")
    direction = request.GET.get("dir", "asc")

    if not sort:
        return qs.order_by("-created", "-id")

    model_fields = _model_field_names(qs.model)
    sortable = _sortable_fields(model_fields)

    field = sortable.get(sort)
    if not field:
        return qs.order_by("-created", "-id")

    order_expr = field if direction == "asc" else f"-{field}"
    qs = qs.order_by(order_expr, "-id")

    if field.startswith("kainos_eilutes__"):
        qs = qs.distinct()

    return qs
