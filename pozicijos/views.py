# pozicijos/views.py
from __future__ import annotations

import json
import csv
import textwrap
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.files.base import File
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, IntegerField, Value, Q, Min, Max, CharField
from django.db.models.functions import Cast, Coalesce
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.template.loader import render_to_string
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST

from .forms import PozicijaForm, MaskavimoFormSet
from .forms_kainos import KainaFormSet
from .models import Pozicija, PozicijosBrezinys, KainosEilute, MaskavimoEilute, MetaloStorisEilute
from .schemas.columns import COLUMNS
from .services.import_csv import import_pozicijos_from_csv
from .services.listing import (
    visible_cols_from_request,
    apply_filters,
    apply_sorting,
)
from .services.previews import regenerate_missing_preview
from .services.sync import sync_pozicija_kaina_eur

LIST_COLUMNS = [c for c in COLUMNS if not c.get("list_hidden")]




def _is_admin_user(request) -> bool:
    u = getattr(request, "user", None)
    return bool(getattr(u, "is_authenticated", False) and getattr(u, "is_superuser", False))


def _require_admin_user(request) -> None:
    if not _is_admin_user(request):
        raise PermissionDenied("Šis veiksmas leidžiamas tik administratoriui.")


def _has_user_perm(request, perm: str) -> bool:
    u = getattr(request, "user", None)
    return bool(getattr(u, "is_authenticated", False) and u.has_perm(perm))


def _require_user_perm(request, perm: str, message: str) -> None:
    if not _has_user_perm(request, perm):
        raise PermissionDenied(message)


FORM_SUGGEST_FIELDS = [
    "klientas",
    "projektas",
    "metalas",
    "paruosimas",
    "padengimas",
    "padengimo_standartas",
    "spalva",
    "maskavimas",
    "testai_kokybe",
    "pakavimas",
    "instrukcija",
]



def _copy_initial_from_pozicija(pozicija: Pozicija) -> dict:
    """
    Paruošia initial duomenis naujai detalei pagal esamą detalę.

    Sąmoningai kopijuojame tik PozicijaForm laukus.
    Nekopijuojame:
    - kainų eilučių;
    - brėžinių;
    - susijusių objektų;
    - sisteminių laukų.
    """
    initial = {}

    skip_on_copy = {"klientas", "projektas"}

    for name in PozicijaForm.Meta.fields:
        if name in skip_on_copy:
            continue

        value = getattr(pozicija, name, None)

        if value is None:
            continue

        if hasattr(value, "isoformat"):
            value = value.isoformat()
        elif not isinstance(value, (str, int, float, bool)):
            value = str(value)

        initial[name] = value

    return initial


def _copy_breziniai_to_pozicija(source: Pozicija, target: Pozicija) -> int:
    """
    Fiziškai nukopijuoja brėžinių / paveiksliukų failus į naują detalę.

    Sąmoningai nekopijuojame kainų.
    Brėžiniai nekabinami prie to paties failo – sukuriami nauji failai per FileField.save().
    """
    copied = 0

    for source_brez in source.breziniai.all().order_by("eiliskumas", "id"):
        if not source_brez.failas:
            continue

        filename = source_brez.filename or "brezinys"

        try:
            with source_brez.failas.storage.open(source_brez.failas.name, "rb") as fh:
                new_brez = PozicijosBrezinys(
                    pozicija=target,
                    pavadinimas=source_brez.pavadinimas,
                    eiliskumas=source_brez.eiliskumas,
                )
                new_brez.failas.save(filename, File(fh), save=True)
                copied += 1
        except Exception:
            # Vieno blogo failo klaida neturi sugadinti visos kopijos.
            continue

    return copied

def _get_form_suggestions() -> dict[str, list[str]]:
    suggestions: dict[str, list[str]] = {}
    qs = Pozicija.objects.all().prefetch_related("metalo_storio_eilutes")
    for field in FORM_SUGGEST_FIELDS:
        values = qs.order_by(field).values_list(field, flat=True).distinct()
        suggestions[field] = [v for v in values if v]
    return suggestions


def _safe_int(value, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _filter_values_from_request(request) -> dict[str, str]:
    """
    Template filtrų laukeliams paruošia paprastą žodyną.

    GET parametrai ateina kaip:
      f[klientas]=ABC
      f[metalas]=Plienas

    O template naudoja:
      f|dict_get:c.key

    Todėl čia paverčiame į:
      {"klientas": "ABC", "metalas": "Plienas"}
    """
    result: dict[str, str] = {}

    for key, value in request.GET.items():
        if not key.startswith("f[") or not key.endswith("]"):
            continue

        raw_key = key[2:-1].strip()
        value = (value or "").strip()

        if raw_key and value:
            result[raw_key] = value

    return result


def _base_list_qs():
    """
    Centralizuojam: sąrašui anotacijos (brez_count + kainų min/max).
    Dok_count kol kas neturim modelio – paliekam 0, kad stulpelis nelūžtų.
    """
    return (
        Pozicija.objects.all()
        .prefetch_related("breziniai")
        .annotate(brez_count=Count("breziniai", distinct=True))
        .annotate(dok_count=Value(0, output_field=IntegerField()))
        .annotate(
            kaina_min=Min("kainos_eilutes__kaina", filter=Q(kainos_eilutes__busena="aktuali")),
            kaina_max=Max("kainos_eilutes__kaina", filter=Q(kainos_eilutes__busena="aktuali")),
        )
        .annotate(
            # fallback, jei nėra susietų eilučių
            metalo_storiai_display=Coalesce(
                Cast("metalo_storis", CharField()),
                Value("", output_field=CharField()),
            ),
        )
    )


def _fmt_mm(v) -> str:
    if v is None:
        return ""
    if isinstance(v, Decimal):
        s = format(v, "f")
    else:
        s = str(v)
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def _attach_metalo_storiai_display(items):
    """
    Užpildo obj.metalo_storiai_display VISOMIS storio reikšmėmis:
    pvz. '1, 1.5, 2'
    """
    items = list(items)
    if not items:
        return items

    pks = [o.pk for o in items]
    rows = (
        MetaloStorisEilute.objects.filter(pozicija_id__in=pks, storis_mm__isnull=False)
        .order_by("id")
        .values_list("pozicija_id", "storis_mm")
    )

    by_pk: dict[int, list[str]] = {}
    for poz_id, storis in rows:
        by_pk.setdefault(poz_id, []).append(_fmt_mm(storis))

    for o in items:
        vals = by_pk.get(o.pk, [])
        if vals:
            o.metalo_storiai_display = ", ".join(vals)
        else:
            legacy = _fmt_mm(getattr(o, "metalo_storis", None))
            o.metalo_storiai_display = legacy if legacy else ""

    return items


def _page_size_from_request(request) -> int:
    allowed = {10, 25, 50, 100}
    page_size = _safe_int(request.GET.get("page_size", 25), 25)
    return page_size if page_size in allowed else 25


def _page_number_from_request(request) -> int:
    page = _safe_int(request.GET.get("page", 1), 1)
    return max(page, 1)


def _paginate_list_qs(qs, request):
    page_size = _page_size_from_request(request)
    paginator = Paginator(qs, page_size)
    page_obj = paginator.get_page(_page_number_from_request(request))
    items = _attach_metalo_storiai_display(page_obj.object_list)
    page_range = list(
        paginator.get_elided_page_range(
            number=page_obj.number,
            on_each_side=2,
            on_ends=1,
        )
    )
    return page_size, paginator, page_obj, page_range, items


def pozicijos_list(request):
    visible_cols = visible_cols_from_request(request)
    q = request.GET.get("q", "").strip()

    current_sort = request.GET.get("sort", "")
    current_dir = request.GET.get("dir", "asc")

    qs = _base_list_qs()
    qs = apply_filters(qs, request)
    qs = apply_sorting(qs, request)

    page_size, paginator, page_obj, page_range, items = _paginate_list_qs(qs, request)

    context = {
        "columns_schema": LIST_COLUMNS,
        "visible_cols": visible_cols,
        "items": items,
        "q": q,
        "page_size": page_size,
        "page_obj": page_obj,
        "paginator": paginator,
        "page_range": page_range,
        "f": _filter_values_from_request(request),
        "current_sort": current_sort,
        "current_dir": current_dir,
    }
    return render(request, "pozicijos/list.html", context)


def pozicijos_tbody(request):
    visible_cols = visible_cols_from_request(request)

    current_sort = request.GET.get("sort", "")
    current_dir = request.GET.get("dir", "asc")

    qs = _base_list_qs()
    qs = apply_filters(qs, request)
    qs = apply_sorting(qs, request)

    page_size, paginator, page_obj, page_range, items = _paginate_list_qs(qs, request)

    context = {
        "columns_schema": LIST_COLUMNS,
        "visible_cols": visible_cols,
        "items": items,
        "page_size": page_size,
        "page_obj": page_obj,
        "paginator": paginator,
        "page_range": page_range,
        "current_sort": current_sort,
        "current_dir": current_dir,
    }

    return JsonResponse(
        {
            "tbody": render_to_string("pozicijos/_tbody.html", context, request=request),
            "pagination": render_to_string("pozicijos/_pagination.html", context, request=request),
            "page": page_obj.number,
            "pages": paginator.num_pages,
            "count": paginator.count,
        }
    )


def pozicijos_stats(request):
    qs = Pozicija.objects.all()
    qs = apply_filters(qs, request)

    data = qs.values("klientas").annotate(cnt=Count("id")).order_by("-cnt")

    labels: list[str] = []
    values: list[int] = []
    total = 0
    for row in data:
        name = row["klientas"] or "Nepriskirta"
        labels.append(name)
        values.append(row["cnt"])
        total += row["cnt"]

    return JsonResponse({"labels": labels, "values": values, "total": total})



def _csv_decimal(value, places: int = 4) -> str:
    if value is None:
        return ""
    try:
        value = Decimal(value)
        s = f"{value:.{places}f}"
    except Exception:
        s = str(value)
    return s.replace(".", ",")


def _csv_wrap_text(value, width: int = 90) -> str:
    """
    CSV neturi tikro Excel word-wrap formatavimo.
    Todėl ilgesniam tekstui, pvz. Pastaboms, įterpiame realius eilutės lūžius.
    csv.writer tokį lauką saugiai pacituoja kaip vieną CSV langelį.
    """
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ""

    out: list[str] = []
    for paragraph in text.split("\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            out.append("")
            continue

        wrapped = textwrap.wrap(
            paragraph,
            width=width,
            break_long_words=False,
            break_on_hyphens=False,
        )
        out.extend(wrapped or [paragraph])

    return "\n".join(out)


def _csv_value(obj: Pozicija, key: str) -> str:
    if key == "maskavimo_tipas":
        return obj.get_maskavimo_tipas_display() or ""

    if key == "pakavimo_tipas":
        return obj.get_pakavimo_tipas_display() or ""

    if key == "atlikimo_terminas":
        value = getattr(obj, "atlikimo_terminas", None)
        return f"{value} d.d." if value is not None else ""

    if key == "brez_count":
        return str(getattr(obj, "brez_count", 0) or 0)

    if key == "dok_count":
        return str(getattr(obj, "dok_count", 0) or 0)

    if key == "matmenys_xyz":
        return str(getattr(obj, "matmenys_xyz", "") or "")

    if key == "ktl_dangos_storis_display":
        return str(getattr(obj, "ktl_dangos_storis_display", "") or "")

    if key == "miltai_dangos_storis_display":
        return str(getattr(obj, "miltai_dangos_storis_display", "") or "")

    if key == "metalo_storiai_display":
        return str(getattr(obj, "metalo_storiai_display", "") or "")

    if key in ("remo_plotas", "remo_svoris"):
        value = getattr(obj, key, None)
        return _csv_decimal(value, places=3) if value is not None else ""

    if key == "kaina_eur":
        k_min = getattr(obj, "kaina_min", None)
        k_max = getattr(obj, "kaina_max", None)
        if k_min is not None and k_max is not None:
            if k_min == k_max:
                return _csv_decimal(k_min)
            return f"{_csv_decimal(k_min)}–{_csv_decimal(k_max)}"

        value = getattr(obj, "kaina_eur", None)
        return _csv_decimal(value) if value is not None else ""

    if key == "pastabos":
        return _csv_wrap_text(getattr(obj, "pastabos", ""), width=90)

    value = getattr(obj, key, None)
    if value is None:
        return ""

    get_display = getattr(obj, f"get_{key}_display", None)
    if callable(get_display):
        try:
            display_value = get_display()
            if display_value not in (None, ""):
                return str(display_value)
        except Exception:
            pass

    if isinstance(value, Decimal):
        return str(value).replace(".", ",")

    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")

    return str(value)


def pozicijos_export_csv(request):
    visible_cols = visible_cols_from_request(request)
    visible_cols_set = set(visible_cols)

    export_columns = [
        c for c in LIST_COLUMNS
        if c.get("key") in visible_cols_set
    ]

    qs = _base_list_qs()
    qs = apply_filters(qs, request)
    qs = apply_sorting(qs, request)

    items = _attach_metalo_storiai_display(qs)

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="pozicijos_export.csv"'

    # UTF-8 BOM, kad Excel teisingai atidarytų lietuviškas raides.
    response.write("\ufeff")

    writer = csv.writer(response, delimiter=";")
    writer.writerow([c.get("label", c.get("key", "")) for c in export_columns])

    for obj in items:
        writer.writerow([
            _csv_value(obj, c.get("key", ""))
            for c in export_columns
        ])

    return response


def pozicija_detail(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(Pozicija, pk=pk)

    mask_ktl = obj.maskavimo_eilutes.filter(paslauga="ktl").order_by("id")
    mask_milt = obj.maskavimo_eilutes.filter(paslauga="miltai").order_by("id")
    breziniai = obj.breziniai.all().order_by("eiliskumas", "id") if hasattr(obj, "breziniai") else []
    kainos_akt = (
        obj.kainos_eilutes.filter(busena="aktuali").order_by("kiekis_nuo", "kiekis_iki", "id")
        if hasattr(obj, "kainos_eilutes")
        else []
    )

    return render(
        request,
        "pozicijos/detail.html",
        {
            "obj": obj,
            "pozicija": obj,
            "mask_ktl": mask_ktl,
            "mask_miltai": mask_milt,
            "breziniai": breziniai,
            "kainos_akt": kainos_akt,
            "metalo_storiai": obj.metalo_storio_eilutes.filter(storis_mm__isnull=False).order_by("id"),
        },
    )


def _sync_kaina_eur_from_lines(poz: Pozicija) -> None:
    sync_pozicija_kaina_eur(poz)


def _sync_maskavimo_tipas_from_lines(poz: Pozicija) -> None:
    qs = MaskavimoEilute.objects.filter(pozicija=poz)
    has_any = qs.filter(Q(maskuote__gt="") | Q(vietu_kiekis__isnull=False) | Q(aprasymas__gt="")).exists()

    new_tipas = "yra" if has_any else "nera"
    update_fields: list[str] = []

    if (poz.maskavimo_tipas or "").lower() != new_tipas:
        poz.maskavimo_tipas = new_tipas
        update_fields.append("maskavimo_tipas")

    if new_tipas == "nera" and (poz.maskavimas or "") != "":
        poz.maskavimas = ""
        update_fields.append("maskavimas")

    if update_fields:
        update_fields.append("updated")
        poz.save(update_fields=update_fields)


def _save_mask_formset(mask_formset, pozicija: Pozicija, paslauga: str) -> None:
    instances = mask_formset.save(commit=False)

    for inst in instances:
        inst.pozicija = pozicija
        inst.paslauga = paslauga

        txt = (getattr(inst, "maskuote", "") or "").strip()
        qty = getattr(inst, "vietu_kiekis", None)
        desc = (getattr(inst, "aprasymas", "") or "").strip()

        if not txt and qty is None and not desc:
            if getattr(inst, "pk", None):
                inst.delete()
            continue

        inst.save()

    for f in mask_formset.deleted_forms:
        if f.instance.pk:
            f.instance.delete()


def _save_metalo_storis_formset(ms_formset, pozicija: Pozicija) -> None:
    instances = ms_formset.save(commit=False)

    for inst in instances:
        inst.pozicija = pozicija
        if inst.storis_mm is None:
            if inst.pk:
                inst.delete()
            continue
        inst.save()

    for f in ms_formset.deleted_forms:
        if f.instance.pk:
            f.instance.delete()

    first = (
        MetaloStorisEilute.objects.filter(pozicija=pozicija, storis_mm__isnull=False).order_by("id").first()
    )
    pozicija.metalo_storis = first.storis_mm if first else None
    pozicija.save(update_fields=["metalo_storis", "updated"])


def _save_metalo_storis_values(pozicija: Pozicija, post_data) -> None:
    from decimal import Decimal, InvalidOperation

    raw_values = []
    raw_values.append(post_data.get("metalo_storis", ""))  # pagrindinis laukas

    # dinaminės eilutės: metalo_storis_values arba metalo_storis_values[]
    for key, vals in post_data.lists():
        if key.startswith("metalo_storis_values"):
            raw_values.extend(vals)

    parsed = []
    for raw in raw_values:
        t = (raw or "").strip().replace(",", ".")
        if not t:
            continue
        try:
            d = Decimal(t)
        except InvalidOperation:
            continue
        if d < 0:
            continue
        parsed.append(d)

    # pilnas replace
    MetaloStorisEilute.objects.filter(pozicija=pozicija).delete()
    if parsed:
        MetaloStorisEilute.objects.bulk_create([MetaloStorisEilute(pozicija=pozicija, storis_mm=d) for d in parsed])

    # legacy fallback
    first = parsed[0] if parsed else None
    if pozicija.metalo_storis != first:
        pozicija.metalo_storis = first
        pozicija.save(update_fields=["metalo_storis", "updated"])



def pozicija_copy(request, pk: int):
    _require_user_perm(
        request,
        "pozicijos.add_pozicija",
        "Kopijuoti detalę leidžiama tik darbuotojui arba administratoriui.",
    )

    original = get_object_or_404(Pozicija, pk=pk)

    request.session["pozicija_copy_initial"] = _copy_initial_from_pozicija(original)
    request.session["pozicija_copy_source_id"] = original.pk

    messages.warning(
        request,
        "Kuriama nauja detalė pagal pasirinktą įrašą. "
        "Kainos nekopijuojamos. Brėžiniai / paveiksliukai kopijuojami. "
        "Prieš išsaugodami pakeiskite detalės kodą, pavadinimą ar kitus skirtumus, jei reikia.",
    )

    return redirect("pozicijos:create")

def pozicija_create(request):
    _require_user_perm(
        request,
        "pozicijos.add_pozicija",
        "Kurti detales leidžiama tik darbuotojui arba administratoriui.",
    )

    pozicija = None
    copy_source_id = ""

    if request.method == "POST":
        copy_source_id = (request.POST.get("copy_source_id") or "").strip()
        form = PozicijaForm(request.POST, request.FILES)
        formset = KainaFormSet(request.POST, prefix="kainos", queryset=KainosEilute.objects.none())

        mask_ktl_formset = MaskavimoFormSet(
            request.POST,
            prefix="maskavimas_ktl",
            queryset=MaskavimoEilute.objects.none(),
        )
        mask_miltai_formset = MaskavimoFormSet(
            request.POST,
            prefix="maskavimas_miltai",
            queryset=MaskavimoEilute.objects.none(),
        )

        if form.is_valid() and formset.is_valid() and mask_ktl_formset.is_valid() and mask_miltai_formset.is_valid():
            with transaction.atomic():
                pozicija = form.save()

                copied_breziniai_count = 0
                if copy_source_id.isdigit():
                    source_pozicija = Pozicija.objects.filter(pk=int(copy_source_id)).first()
                    if source_pozicija and source_pozicija.pk != pozicija.pk:
                        copied_breziniai_count = _copy_breziniai_to_pozicija(source_pozicija, pozicija)

                formset.instance = pozicija
                instances = formset.save(commit=False)
                for inst in instances:
                    inst.pozicija = pozicija
                    inst.save()
                for f in formset.deleted_forms:
                    if f.instance.pk:
                        f.instance.delete()

                _save_mask_formset(mask_ktl_formset, pozicija, "ktl")
                _save_mask_formset(mask_miltai_formset, pozicija, "miltai")
                _save_metalo_storis_values(pozicija, request.POST)

                _sync_maskavimo_tipas_from_lines(pozicija)
                _sync_kaina_eur_from_lines(pozicija)

            messages.success(request, "Detalė sukurta.")
            if locals().get("copied_breziniai_count"):
                messages.info(request, f"Nukopijuota brėžinių / paveiksliukų: {copied_breziniai_count}.")
            return redirect("pozicijos:detail", pk=pozicija.pk)
        else:
            messages.error(request, "Patikrinkite formos klaidas.")
    else:
        copy_initial = request.session.pop("pozicija_copy_initial", None)
        copy_source_id = str(request.session.pop("pozicija_copy_source_id", "") or "")
        form = PozicijaForm(initial=copy_initial) if copy_initial else PozicijaForm()
        formset = KainaFormSet(prefix="kainos", queryset=KainosEilute.objects.none())
        mask_ktl_formset = MaskavimoFormSet(prefix="maskavimas_ktl", queryset=MaskavimoEilute.objects.none())
        mask_miltai_formset = MaskavimoFormSet(prefix="maskavimas_miltai", queryset=MaskavimoEilute.objects.none())

    context = {
        "form": form,
        "pozicija": pozicija,
        "suggestions": _get_form_suggestions(),
        "kainos_formset": formset,
        "maskavimo_ktl_formset": mask_ktl_formset,
        "maskavimo_miltai_formset": mask_miltai_formset,
        "copy_source_id": copy_source_id,
    }
    return render(request, "pozicijos/form.html", context)


def pozicija_edit(request, pk):
    _require_user_perm(
        request,
        "pozicijos.change_pozicija",
        "Redaguoti detales leidžiama tik darbuotojui arba administratoriui.",
    )

    pozicija = get_object_or_404(Pozicija, pk=pk)

    qs = KainosEilute.objects.filter(pozicija=pozicija).order_by(
        "matas",
        "yra_fiksuota",
        "kiekis_nuo",
        "fiksuotas_kiekis",
        "prioritetas",
        "-created",
    )

    m_ktl_qs = MaskavimoEilute.objects.filter(pozicija=pozicija, paslauga="ktl").order_by("id")
    m_milt_qs = MaskavimoEilute.objects.filter(pozicija=pozicija, paslauga="miltai").order_by("id")
    ms_qs = MetaloStorisEilute.objects.filter(pozicija=pozicija).order_by("id")

    if request.method == "POST":
        form = PozicijaForm(request.POST, request.FILES, instance=pozicija)
        formset = KainaFormSet(request.POST, prefix="kainos", instance=pozicija, queryset=qs)

        mask_ktl_formset = MaskavimoFormSet(request.POST, prefix="maskavimas_ktl", queryset=m_ktl_qs)
        mask_miltai_formset = MaskavimoFormSet(request.POST, prefix="maskavimas_miltai", queryset=m_milt_qs)

        if form.is_valid() and formset.is_valid() and mask_ktl_formset.is_valid() and mask_miltai_formset.is_valid():
            with transaction.atomic():
                form.save()

                instances = formset.save(commit=False)
                for inst in instances:
                    inst.pozicija = pozicija
                    inst.save()
                for f in formset.deleted_forms:
                    if f.instance.pk:
                        f.instance.delete()

                _save_mask_formset(mask_ktl_formset, pozicija, "ktl")
                _save_mask_formset(mask_miltai_formset, pozicija, "miltai")
                _save_metalo_storis_values(pozicija, request.POST)

                _sync_maskavimo_tipas_from_lines(pozicija)
                _sync_kaina_eur_from_lines(pozicija)

            messages.success(request, "Detalė atnaujinta.")
            return redirect("pozicijos:detail", pk=pozicija.pk)
        else:
            messages.error(request, "Patikrinkite formos klaidas.")
    else:
        form = PozicijaForm(instance=pozicija)
        formset = KainaFormSet(prefix="kainos", instance=pozicija, queryset=qs)
        mask_ktl_formset = MaskavimoFormSet(prefix="maskavimas_ktl", queryset=m_ktl_qs)
        mask_miltai_formset = MaskavimoFormSet(prefix="maskavimas_miltai", queryset=m_milt_qs)

    context = {
        "form": form,
        "pozicija": pozicija,
        "suggestions": _get_form_suggestions(),
        "kainos_formset": formset,
        "maskavimo_ktl_formset": mask_ktl_formset,
        "maskavimo_miltai_formset": mask_miltai_formset,
    }
    return render(request, "pozicijos/form.html", context)


@require_POST
def brezinys_upload(request, pk):
    _require_user_perm(
        request,
        "pozicijos.add_pozicijosbrezinys",
        "Įkelti brėžinius leidžiama tik darbuotojui arba administratoriui.",
    )

    poz = get_object_or_404(Pozicija, pk=pk)

    if request.FILES.get("failas"):
        f = request.FILES["failas"]
        title = request.POST.get("pavadinimas", "").strip()
        br = PozicijosBrezinys.objects.create(
            pozicija=poz,
            failas=f,
            pavadinimas=title,
        )

        if not br.is_step:
            res = regenerate_missing_preview(br)
            if res.ok:
                messages.success(request, "Įkelta. Miniatiūra paruošta.")
            else:
                messages.info(request, f"Įkelta. Miniatiūros sugeneruoti nepavyko: {res.message}")
        else:
            messages.success(request, "Įkelta. STEP/STP miniatiūra nenaudojama (rodoma 3D ikona).")
    else:
        messages.error(request, "Nepasirinktas failas.")

    return redirect("pozicijos:detail", pk=poz.pk)


@require_POST
def brezinys_delete(request, pk, bid):
    _require_admin_user(request)

    poz = get_object_or_404(Pozicija, pk=pk)
    br = get_object_or_404(PozicijosBrezinys, pk=bid, pozicija=poz)
    br.delete()
    return redirect("pozicijos:detail", pk=pk)


@xframe_options_sameorigin
@require_POST
def brezinys_reorder(request, pk):
    _require_user_perm(
        request,
        "pozicijos.change_pozicijosbrezinys",
        "Keisti brėžinių tvarką leidžiama tik darbuotojui arba administratoriui.",
    )

    poz = get_object_or_404(Pozicija, pk=pk)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Blogas JSON."}, status=400)

    raw_ids = payload.get("ids") or []
    try:
        ids = [int(x) for x in raw_ids]
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Blogi brėžinių ID."}, status=400)

    if not ids:
        return JsonResponse({"ok": False, "error": "Tuščias brėžinių sąrašas."}, status=400)

    existing_ids = set(
        poz.breziniai.filter(id__in=ids).values_list("id", flat=True)
    )

    if existing_ids != set(ids):
        return JsonResponse(
            {"ok": False, "error": "Kai kurie brėžiniai nepriklauso šiai detalei."},
            status=400,
        )

    for idx, bid in enumerate(ids, start=1):
        # 10,20,30... paliekam tarpelius ateičiai.
        poz.breziniai.filter(id=bid).update(eiliskumas=idx * 10)

    return JsonResponse({"ok": True})


def brezinys_3d(request, pk, bid):
    poz = get_object_or_404(Pozicija, pk=pk)
    br = get_object_or_404(PozicijosBrezinys, pk=bid, pozicija=poz)
    return render(request, "pozicijos/brezinys_3d.html", {"pozicija": poz, "brezinys": br})


def pozicijos_import_csv(request):
    _require_admin_user(request)

    result = None
    dry_run = False

    if request.method == "POST":
        dry_run = bool(request.POST.get("dry_run"))
        uploaded = request.FILES.get("file")
        if not uploaded:
            messages.error(request, "Pasirink CSV failą.")
        else:
            result = import_pozicijos_from_csv(uploaded, dry_run=dry_run)

    return render(request, "pozicijos/import_csv.html", {"result": result, "dry_run": dry_run})
