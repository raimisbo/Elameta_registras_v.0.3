from __future__ import annotations

from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from .models import Pozicija, KainosEilute
from .forms_kainos import KainaFormSet, KainaFormSetNoDelete
from .services.kainos import set_aktuali
from .services.sync import sync_pozicija_kaina_eur


def _sync_pozicija_kaina_eur(pozicija: Pozicija) -> None:
    """Suderinamumo wrapperis; vienas tiesos šaltinis – services.sync."""
    sync_pozicija_kaina_eur(pozicija)


def _get_filters(request: HttpRequest) -> tuple[str, str]:
    """
    Filtrai gali ateiti:
      - per GET (įprastas filtravimas),
      - per POST hidden laukus (_busena, _matas), kad po išsaugojimo grįžtume į tą patį filtrą.
    """
    if request.method == "POST":
        busena = (request.POST.get("_busena") or "").strip()
        matas = (request.POST.get("_matas") or "").strip()
        return busena, matas

    busena = (request.GET.get("busena") or "").strip()
    matas = (request.GET.get("matas") or "").strip()
    return busena, matas


def _redirect_with_filters(pozicija_id: int, busena: str, matas: str) -> HttpResponse:
    base = reverse("pozicijos:kainos_list", kwargs={"pk": pozicija_id})
    params: dict[str, str] = {}
    if busena:
        params["busena"] = busena
    if matas:
        params["matas"] = matas

    if params:
        return redirect(base + "?" + urlencode(params))
    return redirect(base)


def _can_delete_kainos(request: HttpRequest) -> bool:
    # Trinimas tik tikram administratoriui.
    u = getattr(request, "user", None)
    return bool(getattr(u, "is_authenticated", False) and getattr(u, "is_superuser", False))


def _can_manage_kainos(request: HttpRequest) -> bool:
    u = getattr(request, "user", None)
    return bool(
        getattr(u, "is_authenticated", False)
        and (
            u.has_perm("pozicijos.add_kainoseilute")
            or u.has_perm("pozicijos.change_kainoseilute")
        )
    )


def _require_manage_kainos(request: HttpRequest) -> None:
    if not _can_manage_kainos(request):
        raise PermissionDenied("Kainų valdymas leidžiamas tik darbuotojui arba administratoriui.")


def _normalize_kiekis_iki_ranges(pozicija: Pozicija) -> None:
    """
    Sutvarko aktyvių kainų kiekio intervalus.

    Jei yra kelios aktyvios eilutės tam pačiam matui:
      80..+ ir 135..+ tampa 80..134 ir 135..+

    Paskutinė eilutė lieka atvira: kiekis_iki = None, UI rodoma kaip „+“.
    """
    matas_values = (
        KainosEilute.objects
        .filter(
            pozicija=pozicija,
            busena="aktuali",
            yra_fiksuota=False,
            kiekis_nuo__isnull=False,
        )
        .values_list("matas", flat=True)
        .distinct()
    )

    for matas_value in matas_values:
        rows = list(
            KainosEilute.objects
            .filter(
                pozicija=pozicija,
                busena="aktuali",
                yra_fiksuota=False,
                matas=matas_value,
                kiekis_nuo__isnull=False,
            )
            .order_by("kiekis_nuo", "prioritetas", "pk")
        )

        for index, row in enumerate(rows):
            next_row = rows[index + 1] if index + 1 < len(rows) else None

            if next_row is None:
                new_iki = None
            else:
                new_iki = next_row.kiekis_nuo - 1

                # Jeigu du intervalai prasideda tuo pačiu ar nelogišku kiekiu,
                # nedarome automatinio neigiamo / atvirkščio intervalo.
                if row.kiekis_nuo is not None and new_iki < row.kiekis_nuo:
                    continue

            if row.kiekis_iki != new_iki:
                row.kiekis_iki = new_iki
                row.save(update_fields=["kiekis_iki"])


@require_http_methods(["GET", "POST"])
def kainos_list(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Vieno lango kainų redagavimas (formset ant Pozicija).

    - busena filtras: DB reikšmės yra "aktuali" / "sena"
    - matas filtras: "Vnt." / "kg" / "komplektas"
    """
    _require_manage_kainos(request)

    pozicija = get_object_or_404(Pozicija, pk=pk)

    busena, matas = _get_filters(request)

    base_qs = KainosEilute.objects.filter(pozicija=pozicija)

    # Filtrai (tik DB reikšmės)
    if busena:
        base_qs = base_qs.filter(busena=busena)
    if matas:
        base_qs = base_qs.filter(matas=matas)

    qs = base_qs.order_by(
        "matas",
        "yra_fiksuota",
        "kiekis_nuo",
        "fiksuotas_kiekis",
        "prioritetas",
        "-created",
    )

    # Naudojam vienodą prefix, kaip kitur (pozicija_create/edit) – mažiau painiavos
    prefix = "kainos"

    can_delete = _can_delete_kainos(request)
    FormSetClass = KainaFormSet if can_delete else KainaFormSetNoDelete

    if request.method == "POST":
        # Priminiui: fiksuojam, ar buvo keista busena_ui (tik tom eilutėm, kurios šitam filtruotam qs)
        old_busena = {k.pk: (k.busena or "") for k in qs}

        formset = FormSetClass(request.POST, instance=pozicija, queryset=qs, prefix=prefix)
        if formset.is_valid():
            # Jei formset nepateikė realių pakeitimų (pvz. mygtukas nesubindino formos / TOTAL_FORMS nepadidėjo),
            # nesakom „išsaugota“, kad neliktų klaidinančių success žinučių.
            if (not formset.has_changed()) and (not getattr(formset, "deleted_forms", [])):
                messages.info(request, "Nėra pakeitimų – nieko neišsaugota.")
                return _redirect_with_filters(pozicija.pk, busena, matas)

            busena_changed = False
            for f in formset.forms:
                if not hasattr(f, "cleaned_data"):
                    continue
                if f.cleaned_data.get("DELETE"):
                    continue
                if "busena_ui" in getattr(f, "changed_data", []):
                    busena_changed = True
                    break
                # atsarginis palyginimas (jei kada nors keisis formos laukai)
                pk0 = getattr(f.instance, "pk", None)
                if pk0 and pk0 in old_busena:
                    new_db_busena = f.cleaned_data.get("busena") or ""
                    if new_db_busena and new_db_busena != old_busena[pk0]:
                        busena_changed = True
                        break

            with transaction.atomic():
                # Trinimai – tik admin
                if can_delete:
                    for form in getattr(formset, "deleted_forms", []):
                        if form.instance.pk:
                            form.instance.delete()

                # Save / create
                instances = formset.save(commit=False)
                for inst in instances:
                    inst.pozicija = pozicija
                    inst.save()

                # Konfliktų tvarkymas „aktuali“ logikai
                for inst in instances:
                    if inst.busena == "aktuali":
                        # set_aktuali tvarko senas ir atnaujina pozicija.kaina_eur
                        set_aktuali(inst)

                # Sutvarkom kiekio intervalus: ankstesnės eilutės „Iki“ = sekančios „Nuo“ - 1
                _normalize_kiekis_iki_ranges(pozicija)

                # Visada perskaičiuojam pozicija.kaina_eur pagal aktualią eilutę
                _sync_pozicija_kaina_eur(pozicija)

            if busena_changed:
                messages.warning(
                    request,
                    "Pakeitei kainos būseną (-as). Primename sutikrinti būsenas, kad neliktų netyčinių neatitikimų."
                )

            messages.success(request, "Kainos išsaugotos.")
            return _redirect_with_filters(pozicija.pk, busena, matas)

        messages.error(request, "Patikrinkite formos klaidas.")
    else:
        formset = FormSetClass(instance=pozicija, queryset=qs, prefix=prefix)

    context = {
        "pozicija": pozicija,
        "formset": formset,
        "busena": busena,
        "matas": matas,
        "kainos_can_delete": can_delete,
    }
    return render(request, "pozicijos/kainos_list.html", context)


def kaina_create(request: HttpRequest, pk: int) -> HttpResponse:
    _require_manage_kainos(request)
    return redirect("pozicijos:kainos_list", pk=pk)


def kaina_update(request: HttpRequest, id: int) -> HttpResponse:
    _require_manage_kainos(request)
    k = get_object_or_404(KainosEilute, pk=id)
    return redirect("pozicijos:kainos_list", pk=k.pozicija_id)


@require_POST
def kaina_set_aktuali(request: HttpRequest, id: int) -> HttpResponse:
    _require_manage_kainos(request)
    k = get_object_or_404(KainosEilute, pk=id)
    set_aktuali(k)
    _normalize_kiekis_iki_ranges(k.pozicija)
    _sync_pozicija_kaina_eur(k.pozicija)
    messages.success(request, "Kaina pažymėta kaip aktuali.")
    return redirect("pozicijos:kainos_list", pk=k.pozicija_id)


@require_POST
def kaina_delete(request: HttpRequest, id: int) -> HttpResponse:
    _require_manage_kainos(request)
    k = get_object_or_404(KainosEilute, pk=id)
    poz_id = k.pozicija_id

    if not _can_delete_kainos(request):
        messages.error(request, "Kainų eilučių trynimas leidžiamas tik administratoriui.")
        return redirect("pozicijos:kainos_list", pk=poz_id)

    k.delete()

    pozicija = Pozicija.objects.get(pk=poz_id)
    _normalize_kiekis_iki_ranges(pozicija)

    # Po trynimo privalom perskaičiuoti pozicija.kaina_eur, kad sąrašas nerodytų pasenusios reikšmės.
    sync_pozicija_kaina_eur(pozicija)
    messages.success(request, "Kainos eilutė ištrinta.")
    return redirect("pozicijos:kainos_list", pk=poz_id)


def kaina_history(request: HttpRequest, id: int) -> HttpResponse:
    _require_manage_kainos(request)
    kaina = get_object_or_404(KainosEilute, pk=id)
    history_qs = kaina.history.all().order_by("-history_date")

    context = {
        "pozicija": kaina.pozicija,
        "kaina": kaina,
        "history": history_qs,
    }
    return render(request, "pozicijos/kaina_history.html", context)
