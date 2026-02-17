# detaliu_registras/views.py
from urllib.parse import unquote as urlunquote
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db.models import Q, Count, Value
from django.db.models.functions import Coalesce
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, FormView

from .models import Uzklausa, Kaina, Brezinys
from .forms import (
    UzklausaFilterForm,
    UzklausaCreateOrSelectForm,  # jei nenaudoji – galima pašalinti importą
    UzklausaEditForm,
    ImportUzklausosCSVForm,
    KainaForm,
    UzklausaCreateFullForm,
)

# CSV importo helperis (nebūtinas)
try:
    from .importers import import_uzklausos_csv
except Exception:
    import_uzklausos_csv = None


# === Pagalbinė brėžinių kūrimo funkcija (kelis failus + URL) ===
def _create_drawings_from_form(request, uzklausa, cleaned_data):
    """
    Sukuria Brezinys įrašus pagal formos laukus:
      - 'drawing_files' (gali būti keli)
      - 'drawing_url' (vienas)
      - 'drawing_name', 'drawing_version', 'drawing_type' (pasirenkama)
    """
    if not uzklausa or not uzklausa.detale:
        return

    files = request.FILES.getlist("drawing_files")
    base_name = (cleaned_data.get("drawing_name") or "").strip()
    base_ver = (cleaned_data.get("drawing_version") or "").strip()
    opt_type = (cleaned_data.get("drawing_type") or "").strip()
    url = (cleaned_data.get("drawing_url") or "").strip()

    # Failai (galima keli)
    for i, f in enumerate(files, start=1):
        Brezinys.objects.create(
            detale=uzklausa.detale,
            pavadinimas=f"{base_name} ({i})" if base_name and len(files) > 1 else (base_name or getattr(f, "name", "")),
            versija=base_ver or "",
            tipas=opt_type or Brezinys.detect_type_by_ext(getattr(f, "name", "")),
            failas=f,
            uploaded_by=request.user if request.user.is_authenticated else None,
        )

    # Išorinis URL (neprivalomas)
    if url:
        Brezinys.objects.create(
            detale=uzklausa.detale,
            pavadinimas=base_name or "Brėžinys (URL)",
            versija=base_ver or "",
            tipas=opt_type or Brezinys.detect_type_by_ext(url),
            isorinis_url=url,
            uploaded_by=request.user if request.user.is_authenticated else None,
        )


# === Sąrašas su filtrais ir donut ===
class UzklausaListView(ListView):
    model = Uzklausa
    template_name = "detaliu_registras/perziureti_uzklausas.html"
    context_object_name = "uzklausos"
    paginate_by = 25

    def get_base_queryset(self):
        return (
            Uzklausa.objects
            .select_related(
                "klientas", "projektas", "detale",
                "detale__specifikacija", "detale__pavirsiu_dangos",
            )
            .order_by("-id")
        )

    def build_filters(self):
        qs = self.get_base_queryset()
        form = UzklausaFilterForm(self.request.GET or None)

        if form.is_valid():
            q = form.cleaned_data.get("q")
            klientas = form.cleaned_data.get("klientas")
            projektas = form.cleaned_data.get("projektas")
            detale = form.cleaned_data.get("detale")
            brezinio_nr = form.cleaned_data.get("brezinio_nr")
            metalas = form.cleaned_data.get("metalas")
            padengimas = form.cleaned_data.get("padengimas")

            # Bendras filtras (apima visus rodymo stulpelius): tekstas + skaičiai + data
            if q:
                qq = q.strip()

                # Skaitinių reikšmių paruošimas
                num_int = None
                num_dec = None
                try:
                    num_int = int(qq)
                except (TypeError, ValueError):
                    pass
                try:
                    num_dec = Decimal(qq)
                except (InvalidOperation, TypeError, ValueError):
                    pass

                text_Q = (
                    Q(detale__pavadinimas__icontains=qq) |
                    Q(detale__brezinio_nr__icontains=qq) |
                    Q(klientas__vardas__icontains=qq) |
                    Q(projektas__pavadinimas__icontains=qq) |
                    Q(projektas__aprasymas__icontains=qq) |
                    Q(pastabos__icontains=qq) |
                    # Specifikacija
                    Q(detale__specifikacija__metalas__icontains=qq) |
                    Q(detale__specifikacija__medziagos_kodas__icontains=qq) |
                    # Dangos
                    Q(detale__pavirsiu_dangos__ktl_ec_name__icontains=qq) |
                    Q(detale__pavirsiu_dangos__miltelinis_name__icontains=qq) |
                    Q(detale__pavirsiu_dangos__spalva_ral__icontains=qq) |
                    Q(detale__pavirsiu_dangos__blizgumas__icontains=qq) |
                    # Pakuotė / kita
                    Q(detale__pakuotes_tipas__icontains=qq) |
                    Q(detale__pakuotes_pastabos__icontains=qq) |
                    Q(detale__testas_adhezija__icontains=qq) |
                    Q(detale__testai_kita__icontains=qq) |
                    Q(detale__ppap_dokumentai__icontains=qq) |
                    Q(detale__priedai_info__icontains=qq)
                )

                number_Q = Q()
                if num_int is not None or num_dec is not None:
                    number_Q = (
                        Q(id=num_int) |
                        # kiekiai
                        Q(detale__kiekis_metinis=num_int) |
                        Q(detale__kiekis_menesis=num_int) |
                        Q(detale__kiekis_partijai=num_int) |
                        Q(detale__kiekis_per_val=num_int) |
                        # matmenys
                        Q(detale__ilgis_mm=num_dec) |
                        Q(detale__plotis_mm=num_dec) |
                        Q(detale__aukstis_mm=num_dec) |
                        Q(detale__skersmuo_mm=num_dec) |
                        Q(detale__storis_mm=num_dec) |
                        # kabinimas/pakuotė/testai
                        Q(detale__kabliuku_kiekis=num_int) |
                        Q(detale__kabinimo_anga_mm=num_dec) |
                        Q(detale__vienetai_dezeje=num_int) |
                        Q(detale__vienetai_paleje=num_int) |
                        Q(detale__testai_druskos_rukas_val=num_int) |
                        Q(detale__testas_storis_mikronai=num_int) |
                        # specifikacija skaičiai
                        Q(detale__specifikacija__plotas_m2=num_dec) |
                        Q(detale__specifikacija__svoris_kg=num_dec)
                    )

                date_Q = Q()
                if len(qq) == 10 and qq[4] == "-" and qq[7] == "-":  # YYYY-MM-DD
                    date_Q = Q(data=qq)

                qs = qs.filter(text_Q | number_Q | date_Q).distinct()

            if klientas:
                qs = qs.filter(klientas=klientas)
            if projektas:
                qs = qs.filter(projektas=projektas)
            if detale:
                qs = qs.filter(detale=detale)
            if brezinio_nr:
                qs = qs.filter(detale__brezinio_nr__icontains=brezinio_nr)
            if metalas:
                qs = qs.filter(detale__specifikacija__metalas__icontains=metalas)
            if padengimas:
                qs = qs.filter(
                    Q(detale__pavirsiu_dangos__ktl_ec_name__icontains=padengimas) |
                    Q(detale__pavirsiu_dangos__miltelinis_name__icontains=padengimas)
                )

        return form, qs

    def get_queryset(self):
        form, qs = self.build_filters()

        # papildomas donut filtras ?seg=client:<vardas> / ?seg=others
        seg = self.request.GET.get("seg")
        if seg:
            # TOP5 vardų sąrašas iš jau filtruoto QS
            top_names = list(
                qs.annotate(label=Coalesce("klientas__vardas", Value("Be kliento")))
                  .values("label")
                  .annotate(c=Count("id"))
                  .order_by("-c")
                  .values_list("label", flat=True)[:5]
            )
            if seg == "others":
                qs = qs.exclude(klientas__vardas__in=top_names)
            elif seg.startswith("client:"):
                name = urlunquote(seg.split("client:", 1)[1])
                if name == "Be kliento":
                    qs = qs.filter(klientas__isnull=True)
                else:
                    qs = qs.filter(klientas__vardas=name)

        self._filter_form = form
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["filter_form"] = getattr(self, "_filter_form", UzklausaFilterForm())

        # Naudojame jau sugeneruotą self.object_list (nebekviečiam get_queryset())
        qs_all = self.object_list.select_related("klientas")
        total = qs_all.count()
        top_rows = (
            qs_all.annotate(label=Coalesce("klientas__vardas", Value("Be kliento")))
                  .values("label")
                  .annotate(value=Count("id"))
                  .order_by("-value")[:5]
        )
        segments = [{"label": r["label"], "value": r["value"], "slug": f"client:{r['label']}"} for r in top_rows]
        sum_top = sum(r["value"] for r in top_rows)
        others = max(0, total - sum_top)
        if others > 0:
            segments.append({"label": "Kiti", "value": others, "slug": "others"})

        ctx["chart_total"] = total
        ctx["chart_segments"] = segments
        ctx["active_seg"] = self.request.GET.get("seg", "")
        return ctx


# === Peržiūra ===
class UzklausaDetailView(DetailView):
    model = Uzklausa
    template_name = "detaliu_registras/perziureti_uzklausa.html"
    context_object_name = "uzklausa"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        uzk = self.object
        # Paliekame suderinamumui
        kainos = uzk.kainos.all().order_by("-id")
        current = kainos.filter(busena="aktuali").first()
        ctx["kaina_aktuali"] = current
        ctx["kainos"] = kainos
        return ctx


# === Nauja užklausa ===
class UzklausaCreateView(CreateView):
    template_name = "detaliu_registras/ivesti_uzklausa.html"
    form_class = UzklausaCreateFullForm

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.request.method == "POST":
            ctx["kaina_form"] = KainaForm(self.request.POST)
        else:
            ctx["kaina_form"] = KainaForm()
        return ctx

    def form_valid(self, form):
        uzklausa = form.save()

        # Kainos kūrimas (jei paduota)
        kaina_form = KainaForm(self.request.POST)
        if kaina_form.is_valid() and kaina_form.cleaned_data.get("suma") is not None:
            k = kaina_form.save(commit=False)
            k.uzklausa = uzklausa
            k.busena = k.busena or "aktuali"
            k.save()
            messages.success(self.request, "Užklausa sukurta su kaina.")
        else:
            messages.success(self.request, "Užklausa sukurta (be kainos).")

        # Brėžiniai (kelis failus + URL)
        _create_drawings_from_form(self.request, uzklausa, form.cleaned_data)

        return redirect(reverse("detaliu_registras:perziureti_uzklausa", args=[uzklausa.pk]))


# === Redagavimas ===
class UzklausaUpdateView(UpdateView):
    model = Uzklausa
    template_name = "detaliu_registras/redaguoti_uzklausa.html"
    form_class = UzklausaEditForm

    def form_valid(self, form):
        uzklausa = form.save()

        # Brėžiniai (kelis failus + URL)
        _create_drawings_from_form(self.request, uzklausa, form.cleaned_data)

        messages.success(self.request, "Užklausa atnaujinta.")
        return redirect(reverse("detaliu_registras:perziureti_uzklausa", args=[uzklausa.pk]))


# === KAINOS: redagavimas per formą ===
class KainosRedagavimasView(FormView):
    template_name = "detaliu_registras/redaguoti_kaina.html"
    form_class = KainaForm

    def dispatch(self, request, *args, **kwargs):
        self.uzklausa = (
            Uzklausa.objects
            .select_related("detale", "projektas")
            .get(pk=kwargs["pk"])
        )
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        instance = Kaina.objects.filter(uzklausa=self.uzklausa).first()
        kwargs["instance"] = instance
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["uzklausa"] = self.uzklausa
        k = Kaina.objects.filter(uzklausa=self.uzklausa).first()
        ctx["kaina"] = k
        ctx["kainos_history"] = (k.history.order_by("-history_date")[:5] if k else [])
        return ctx

    def form_valid(self, form):
        kaina = form.save(commit=False)
        kaina.uzklausa = self.uzklausa
        if not kaina.busena:
            kaina.busena = "aktuali"
        kaina.save()
        messages.success(self.request, "Kaina išsaugota.")
        return redirect(reverse("detaliu_registras:perziureti_uzklausa", args=[self.uzklausa.pk]))


# === CSV importas (stub) ===
class ImportUzklausosCSVView(FormView):
    template_name = "detaliu_registras/import_uzklausos.html"
    form_class = ImportUzklausosCSVForm
    success_url = reverse_lazy("detaliu_registras:import_uzklausos")

    def form_valid(self, form):
        if import_uzklausos_csv is None:
            messages.error(self.request, "Importavimo modulis nerastas: detaliu_registras/importers.py")
            return super().form_valid(form)

        stats = import_uzklausos_csv(self.request.FILES["file"])
        if stats.get("errors"):
            for row, err in stats["errors"][:10]:
                messages.error(self.request, f"Eilutė {row}: {err}")
        messages.success(self.request, f"Sukurta: {stats.get('created',0)}, atnaujinta: {stats.get('updated',0)}, praleista: {stats.get('skipped',0)}")
        return super().form_valid(form)
