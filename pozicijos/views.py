# pozicijos/views.py
from __future__ import annotations

from django.contrib import messages
from django.db import transaction
from django.db.models import Count, IntegerField, Value, Q, Min, Max
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render, redirect
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

def _get_form_suggestions() -> dict[str, list[str]]:
    suggestions: dict[str, list[str]] = {}
    qs = Pozicija.objects.all().prefetch_related('metalo_storio_eilutes')
    for field in FORM_SUGGEST_FIELDS:
        values = qs.order_by(field).values_list(field, flat=True).distinct()
        suggestions[field] = [v for v in values if v]
    return suggestions

def _safe_int(value, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default

def _base_list_qs():
    """
    Centralizuojam: sąrašui anotacijos (brez_count + kainų min/max).
    Dok_count kol kas neturim modelio – paliekam 0, kad stulpelis nelūžtų.
    """
    return (
        Pozicija.objects.all()
        .annotate(brez_count=Count("breziniai", distinct=True))
        .annotate(dok_count=Value(0, output_field=IntegerField()))
        .annotate(
            kaina_min=Min("kainos_eilutes__kaina", filter=Q(kainos_eilutes__busena="aktuali")),
            kaina_max=Max("kainos_eilutes__kaina", filter=Q(kainos_eilutes__busena="aktuali")),
        )
    )

def pozicijos_list(request):
    visible_cols = visible_cols_from_request(request)
    q = request.GET.get("q", "").strip()
    page_size = _safe_int(request.GET.get("page_size", 25), 25)

    current_sort = request.GET.get("sort", "")
    current_dir = request.GET.get("dir", "asc")

    qs = _base_list_qs()
    qs = apply_filters(qs, request)
    qs = apply_sorting(qs, request)[:page_size]

    context = {
        "columns_schema": COLUMNS,
        "visible_cols": visible_cols,
        "items": qs,
        "q": q,
        "page_size": page_size,
        "f": request.GET,
        "current_sort": current_sort,
        "current_dir": current_dir,
    }
    return render(request, "pozicijos/list.html", context)

def pozicijos_tbody(request):
    visible_cols = visible_cols_from_request(request)
    page_size = _safe_int(request.GET.get("page_size", 25), 25)

    current_sort = request.GET.get("sort", "")
    current_dir = request.GET.get("dir", "asc")

    qs = _base_list_qs()
    qs = apply_filters(qs, request)
    qs = apply_sorting(qs, request)[:page_size]

    return render(
        request,
        "pozicijos/_tbody.html",
        {
            "columns_schema": COLUMNS,
            "visible_cols": visible_cols,
            "items": qs,
            "current_sort": current_sort,
            "current_dir": current_dir,
        },
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

def pozicija_detail(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(Pozicija, pk=pk)

    mask_ktl = obj.maskavimo_eilutes.filter(paslauga="ktl").order_by("id")
    mask_milt = obj.maskavimo_eilutes.filter(paslauga="miltai").order_by("id")
    breziniai = obj.breziniai.all().order_by("-uploaded_at") if hasattr(obj, "breziniai") else []
    kainos_akt = obj.kainos_eilutes.filter(busena="aktuali").order_by("kiekis_nuo", "kiekis_iki", "id") if hasattr(obj, "kainos_eilutes") else []

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
        MetaloStorisEilute.objects
        .filter(pozicija=pozicija, storis_mm__isnull=False)
        .order_by("id")
        .first()
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
        MetaloStorisEilute.objects.bulk_create(
            [MetaloStorisEilute(pozicija=pozicija, storis_mm=d) for d in parsed]
        )

    # legacy fallback
    first = parsed[0] if parsed else None
    if pozicija.metalo_storis != first:
        pozicija.metalo_storis = first
        pozicija.save(update_fields=["metalo_storis", "updated"])


def pozicija_create(request):
    pozicija = None

    if request.method == "POST":
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

        if (
            form.is_valid()
            and formset.is_valid()
            and mask_ktl_formset.is_valid()
            and mask_miltai_formset.is_valid()
        ):
            with transaction.atomic():
                pozicija = form.save()

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

            messages.success(request, "Pozicija sukurta.")
            return redirect("pozicijos:detail", pk=pozicija.pk)
        else:
            messages.error(request, "Patikrinkite formos klaidas.")
    else:
        form = PozicijaForm()
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

    }
    return render(request, "pozicijos/form.html", context)

def pozicija_edit(request, pk):
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

        if (
            form.is_valid()
            and formset.is_valid()
            and mask_ktl_formset.is_valid()
            and mask_miltai_formset.is_valid()
        ):
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

            messages.success(request, "Pozicija atnaujinta.")
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
    poz = get_object_or_404(Pozicija, pk=pk)
    br = get_object_or_404(PozicijosBrezinys, pk=bid, pozicija=poz)
    br.delete()
    return redirect("pozicijos:detail", pk=pk)

@xframe_options_sameorigin
def brezinys_3d(request, pk, bid):
    poz = get_object_or_404(Pozicija, pk=pk)
    br = get_object_or_404(PozicijosBrezinys, pk=bid, pozicija=poz)
    return render(request, "pozicijos/brezinys_3d.html", {"pozicija": poz, "brezinys": br})

def pozicijos_import_csv(request):
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
