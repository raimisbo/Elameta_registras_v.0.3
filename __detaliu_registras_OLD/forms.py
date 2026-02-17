# detaliu_registras/forms.py
from django import forms
from django.core.exceptions import ValidationError

from .models import (
    Uzklausa, Klientas, Projektas, Detale,
    DetaleSpecifikacija, PavirsiuDangos, Kaina
)

# ---------- Brėžinių įkėlimas (multiple) ----------
class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True

class DrawingMixin(forms.Form):
    drawing_files = forms.FileField(
        required=False,
        label="Brėžiniai (galima keli)",
        widget=MultipleFileInput(attrs={
            "multiple": True,
            "accept": "image/*,application/pdf,.dxf,.dwg,.svg",
        }),
    )
    drawing_name = forms.CharField(required=False, max_length=255, label="Pavadinimas")
    drawing_version = forms.CharField(required=False, max_length=64, label="Versija")
    drawing_type = forms.ChoiceField(
        required=False,
        choices=[("img", "Vaizdas"), ("pdf", "PDF"), ("cad", "CAD")],
        label="Tipas",
    )
    drawing_url = forms.URLField(required=False, label="Išorinis URL")

# ---------- Pagalbiniai 1–1 gavėjai ----------
def _get_or_create_spec(detale: Detale) -> DetaleSpecifikacija:
    if getattr(detale, "specifikacija_id", None):
        return detale.specifikacija
    return DetaleSpecifikacija.objects.create(detale=detale)

def _get_or_create_dangos(detale: Detale) -> PavirsiuDangos:
    if getattr(detale, "pavirsiu_dangos_id", None):
        return detale.pavirsiu_dangos
    return PavirsiuDangos.objects.create(detale=detale)

# ---------- Filtrų forma (naudojama sąraše) ----------
class UzklausaFilterForm(forms.Form):
    q = forms.CharField(required=False, label="Paieška", widget=forms.TextInput(attrs={
        "placeholder": "ieškoti pagal detalę, brėžinį, klientą, projektą…"
    }))
    klientas = forms.ModelChoiceField(
        required=False, queryset=Klientas.objects.all(), label="Klientas"
    )
    projektas = forms.ModelChoiceField(
        required=False, queryset=Projektas.objects.all(), label="Projektas"
    )
    detale = forms.ModelChoiceField(
        required=False, queryset=Detale.objects.all(), label="Detalė"
    )
    brezinio_nr = forms.CharField(required=False, label="Brėžinio nr.")
    metalas = forms.CharField(required=False, label="Metalas")
    padengimas = forms.CharField(required=False, label="Padengimas")

# ---------- CSV importo forma (views.ImportUzklausosCSVView) ----------
class ImportUzklausosCSVForm(forms.Form):
    file = forms.FileField(label="CSV failas")

# ---------- Kainos forma (naudojama kūrimo puslapyje) ----------
class KainaForm(forms.ModelForm):
    class Meta:
        model = Kaina
        fields = (
            "suma", "valiuta", "busena",
            "yra_fiksuota", "kiekis_nuo", "kiekis_iki",
            "fiksuotas_kiekis", "kainos_matas",
        )
        widgets = {
            "busena": forms.Select(choices=[("aktuali", "Aktuali"), ("sena", "Sena")]),
        }

# ---------- (legacy) Select/Create forma, kad importas nesulužtų ----------
class UzklausaCreateOrSelectForm(forms.ModelForm):
    """
    Minimalus „adapteris“, jei kur nors projekte dar referencijuojama ši klasė.
    Realų kūrimą daro UzklausaCreateFullForm.
    """
    class Meta:
        model = Uzklausa
        fields = ["klientas", "projektas", "detale", "pastabos"]

# ---------- Pilna kūrimo forma (su blokais) ----------
class UzklausaCreateFullForm(DrawingMixin, forms.ModelForm):
    # Detalė – bazė
    detale_pavadinimas = forms.CharField(required=False, max_length=255, label="Detalės pavadinimas")
    detale_brezinio_nr = forms.CharField(required=False, max_length=255, label="Brėžinio nr.")
    # Kiekiai
    kiekis_metinis = forms.IntegerField(required=False, label="Metinis kiekis")
    kiekis_menesis = forms.IntegerField(required=False, label="Mėnesio kiekis")
    kiekis_partijai = forms.IntegerField(required=False, label="Kiekis partijai")
    kiekis_per_val = forms.IntegerField(required=False, label="Kiekis per val.")
    # Matmenys
    ilgis_mm = forms.DecimalField(required=False, max_digits=12, decimal_places=2, label="Ilgis (mm)")
    plotis_mm = forms.DecimalField(required=False, max_digits=12, decimal_places=2, label="Plotis (mm)")
    aukstis_mm = forms.DecimalField(required=False, max_digits=12, decimal_places=2, label="Aukštis (mm)")
    skersmuo_mm = forms.DecimalField(required=False, max_digits=12, decimal_places=2, label="Skersmuo (mm)")
    storis_mm = forms.DecimalField(required=False, max_digits=12, decimal_places=2, label="Storis (mm)")
    # Kabinimas
    kabinimo_budas = forms.CharField(required=False, max_length=255, label="Kabinimo būdas")
    kabliuku_kiekis = forms.IntegerField(required=False, label="Kabliukų kiekis")
    kabinimo_anga_mm = forms.DecimalField(required=False, max_digits=12, decimal_places=2, label="Kabinimo anga (mm)")
    kabinti_per = forms.CharField(required=False, max_length=255, label="Kabinti per")
    # Pakuotė
    pakuotes_tipas = forms.CharField(required=False, max_length=255, label="Pakuotės tipas")
    vienetai_dezeje = forms.IntegerField(required=False, label="Vnt. dėžėje")
    vienetai_paleje = forms.IntegerField(required=False, label="Vnt. palėje")
    pakuotes_pastabos = forms.CharField(required=False, max_length=255, label="Pakuotės pastabos")
    # Testai
    testai_druskos_rukas_val = forms.IntegerField(required=False, label="Druskos rūkas (val.)")
    testas_adhezija = forms.CharField(required=False, max_length=255, label="Adhezija")
    testas_storis_mikronai = forms.IntegerField(required=False, label="Storis (µm)")
    testai_kita = forms.CharField(required=False, max_length=255, label="Kiti testai")
    # Doc/pastabos
    ppap_dokumentai = forms.CharField(required=False, max_length=255, label="PPAP dokumentai")
    priedai_info = forms.CharField(required=False, max_length=255, label="Priedai/info")
    # Spec
    spec_metalas = forms.CharField(required=False, max_length=255, label="Metalas")
    spec_plotas_m2 = forms.DecimalField(required=False, max_digits=12, decimal_places=4, label="Plotas (m²)")
    spec_svoris_kg = forms.DecimalField(required=False, max_digits=12, decimal_places=4, label="Svoris (kg)")
    spec_medziagos_kodas = forms.CharField(required=False, max_length=255, label="Medžiagos kodas")
    # Dangos
    dang_ktl_ec_name = forms.CharField(required=False, max_length=255, label="KTL / e-coating")
    dang_miltelinis_name = forms.CharField(required=False, max_length=255, label="Miltelinis")
    dang_spalva_ral = forms.CharField(required=False, max_length=64, label="RAL / spalva")
    dang_blizgumas = forms.CharField(required=False, max_length=128, label="Blizgumas / tekstūra")

    class Meta:
        model = Uzklausa
        fields = ["klientas", "projektas", "detale", "pastabos"]

    def clean(self):
        cd = super().clean()
        if not cd.get("detale"):
            # jei nepasirinkta esama detalė – privaloma bent pavadinimas arba bent failas
            if not cd.get("detale_pavadinimas") and not self.files.getlist("drawing_files"):
                raise ValidationError("Jei nepasirenkama esama detalė, nurodykite detalės pavadinimą arba įkelkite brėžinį.")
        return cd

    def save(self, commit=True):
        uzk = super().save(commit=False)
        detale = self.cleaned_data.get("detale")
        if detale is None:
            detale = Detale.objects.create(
                pavadinimas=self.cleaned_data.get("detale_pavadinimas") or "Detalė",
                brezinio_nr=self.cleaned_data.get("detale_brezinio_nr") or None,
                # kiekiai
                kiekis_metinis=self.cleaned_data.get("kiekis_metinis"),
                kiekis_menesis=self.cleaned_data.get("kiekis_menesis"),
                kiekis_partijai=self.cleaned_data.get("kiekis_partijai"),
                kiekis_per_val=self.cleaned_data.get("kiekis_per_val"),
                # matmenys
                ilgis_mm=self.cleaned_data.get("ilgis_mm"),
                plotis_mm=self.cleaned_data.get("plotis_mm"),
                aukstis_mm=self.cleaned_data.get("aukstis_mm"),
                skersmuo_mm=self.cleaned_data.get("skersmuo_mm"),
                storis_mm=self.cleaned_data.get("storis_mm"),
                # kabinimas
                kabinimo_budas=self.cleaned_data.get("kabinimo_budas"),
                kabliuku_kiekis=self.cleaned_data.get("kabliuku_kiekis"),
                kabinimo_anga_mm=self.cleaned_data.get("kabinimo_anga_mm"),
                kabinti_per=self.cleaned_data.get("kabinti_per"),
                # pakuotė
                pakuotes_tipas=self.cleaned_data.get("pakuotes_tipas"),
                vienetai_dezeje=self.cleaned_data.get("vienetai_dezeje"),
                vienetai_paleje=self.cleaned_data.get("vienetai_paleje"),
                pakuotes_pastabos=self.cleaned_data.get("pakuotes_pastabos"),
                # testai
                testai_druskos_rukas_val=self.cleaned_data.get("testai_druskos_rukas_val"),
                testas_adhezija=self.cleaned_data.get("testas_adhezija"),
                testas_storis_mikronai=self.cleaned_data.get("testas_storis_mikronai"),
                testai_kita=self.cleaned_data.get("testai_kita"),
                # dok
                ppap_dokumentai=self.cleaned_data.get("ppap_dokumentai"),
                priedai_info=self.cleaned_data.get("priedai_info"),
            )
        else:
            # jeigu paduoti laukai – atnaujinti
            mapping = {
                "pavadinimas": "detale_pavadinimas",
                "brezinio_nr": "detale_brezinio_nr",
                "kiekis_metinis": "kiekis_metinis",
                "kiekis_menesis": "kiekis_menesis",
                "kiekis_partijai": "kiekis_partijai",
                "kiekis_per_val": "kiekis_per_val",
                "ilgis_mm": "ilgis_mm",
                "plotis_mm": "plotis_mm",
                "aukstis_mm": "aukstis_mm",
                "skersmuo_mm": "skersmuo_mm",
                "storis_mm": "storis_mm",
                "kabinimo_budas": "kabinimo_budas",
                "kabliuku_kiekis": "kabliuku_kiekis",
                "kabinimo_anga_mm": "kabinimo_anga_mm",
                "kabinti_per": "kabinti_per",
                "pakuotes_tipas": "pakuotes_tipas",
                "vienetai_dezeje": "vienetai_dezeje",
                "vienetai_paleje": "vienetai_paleje",
                "pakuotes_pastabos": "pakuotes_pastabos",
                "testai_druskos_rukas_val": "testai_druskos_rukas_val",
                "testas_adhezija": "testas_adhezija",
                "testas_storis_mikronai": "testas_storis_mikronai",
                "testai_kita": "testai_kita",
                "ppap_dokumentai": "ppap_dokumentai",
                "priedai_info": "priedai_info",
            }
            for model_field, form_field in mapping.items():
                val = self.cleaned_data.get(form_field)
                if val not in (None, ""):
                    setattr(detale, model_field, val)
            detale.save()

        uzk.detale = detale
        if commit:
            uzk.save()

        # Specifikacija
        if any(self.cleaned_data.get(k) not in (None, "") for k in
               ["spec_metalas", "spec_plotas_m2", "spec_svoris_kg", "spec_medziagos_kodas"]):
            s = _get_or_create_spec(detale)
            if self.cleaned_data.get("spec_metalas"): s.metalas = self.cleaned_data["spec_metalas"]
            if self.cleaned_data.get("spec_plotas_m2") not in (None, ""): s.plotas_m2 = self.cleaned_data["spec_plotas_m2"]
            if self.cleaned_data.get("spec_svoris_kg") not in (None, ""): s.svoris_kg = self.cleaned_data["spec_svoris_kg"]
            if self.cleaned_data.get("spec_medziagos_kodas"): s.medziagos_kodas = self.cleaned_data["spec_medziagos_kodas"]
            s.save()

        # Dangos
        if any(self.cleaned_data.get(k) not in (None, "") for k in
               ["dang_ktl_ec_name", "dang_miltelinis_name", "dang_spalva_ral", "dang_blizgumas"]):
            g = _get_or_create_dangos(detale)
            if self.cleaned_data.get("dang_ktl_ec_name"): g.ktl_ec_name = self.cleaned_data["dang_ktl_ec_name"]
            if self.cleaned_data.get("dang_miltelinis_name"): g.miltelinis_name = self.cleaned_data["dang_miltelinis_name"]
            if self.cleaned_data.get("dang_spalva_ral"): g.spalva_ral = self.cleaned_data["dang_spalva_ral"]
            if self.cleaned_data.get("dang_blizgumas"): g.blizgumas = self.cleaned_data["dang_blizgumas"]
            g.save()

        return uzk

# ---------- Redagavimo forma (tie patys laukai) ----------
class UzklausaEditForm(DrawingMixin, forms.ModelForm):
    # tie patys, kad šablonai rodyti gali
    detale_pavadinimas = forms.CharField(required=False, max_length=255, label="Detalės pavadinimas")
    detale_brezinio_nr = forms.CharField(required=False, max_length=255, label="Brėžinio nr.")
    kiekis_metinis = forms.IntegerField(required=False, label="Metinis kiekis")
    kiekis_menesis = forms.IntegerField(required=False, label="Mėnesio kiekis")
    kiekis_partijai = forms.IntegerField(required=False, label="Kiekis partijai")
    kiekis_per_val = forms.IntegerField(required=False, label="Kiekis per val.")
    ilgis_mm = forms.DecimalField(required=False, max_digits=12, decimal_places=2, label="Ilgis (mm)")
    plotis_mm = forms.DecimalField(required=False, max_digits=12, decimal_places=2, label="Plotis (mm)")
    aukstis_mm = forms.DecimalField(required=False, max_digits=12, decimal_places=2, label="Aukštis (mm)")
    skersmuo_mm = forms.DecimalField(required=False, max_digits=12, decimal_places=2, label="Skersmuo (mm)")
    storis_mm = forms.DecimalField(required=False, max_digits=12, decimal_places=2, label="Storis (mm)")
    kabinimo_budas = forms.CharField(required=False, max_length=255, label="Kabinimo būdas")
    kabliuku_kiekis = forms.IntegerField(required=False, label="Kabliukų kiekis")
    kabinimo_anga_mm = forms.DecimalField(required=False, max_digits=12, decimal_places=2, label="Kabinimo anga (mm)")
    kabinti_per = forms.CharField(required=False, max_length=255, label="Kabinti per")
    pakuotes_tipas = forms.CharField(required=False, max_length=255, label="Pakuotės tipas")
    vienetai_dezeje = forms.IntegerField(required=False, label="Vnt. dėžėje")
    vienetai_paleje = forms.IntegerField(required=False, label="Vnt. palėje")
    pakuotes_pastabos = forms.CharField(required=False, max_length=255, label="Pakuotės pastabos")
    testai_druskos_rukas_val = forms.IntegerField(required=False, label="Druskos rūkas (val.)")
    testas_adhezija = forms.CharField(required=False, max_length=255, label="Adhezija")
    testas_storis_mikronai = forms.IntegerField(required=False, label="Storis (µm)")
    testai_kita = forms.CharField(required=False, max_length=255, label="Kiti testai")
    ppap_dokumentai = forms.CharField(required=False, max_length=255, label="PPAP dokumentai")
    priedai_info = forms.CharField(required=False, max_length=255, label="Priedai/info")

    spec_metalas = forms.CharField(required=False, max_length=255, label="Metalas")
    spec_plotas_m2 = forms.DecimalField(required=False, max_digits=12, decimal_places=4, label="Plotas (m²)")
    spec_svoris_kg = forms.DecimalField(required=False, max_digits=12, decimal_places=4, label="Svoris (kg)")
    spec_medziagos_kodas = forms.CharField(required=False, max_length=255, label="Medžiagos kodas")

    dang_ktl_ec_name = forms.CharField(required=False, max_length=255, label="KTL / e-coating")
    dang_miltelinis_name = forms.CharField(required=False, max_length=255, label="Miltelinis")
    dang_spalva_ral = forms.CharField(required=False, max_length=64, label="RAL / spalva")
    dang_blizgumas = forms.CharField(required=False, max_length=128, label="Blizgumas / tekstūra")

    class Meta:
        model = Uzklausa
        fields = ["klientas", "projektas", "detale", "pastabos"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        d = getattr(self.instance, "detale", None)
        if d:
            self.fields["detale_pavadinimas"].initial = d.pavadinimas
            self.fields["detale_brezinio_nr"].initial = d.brezinio_nr
            for f in [
                "kiekis_metinis","kiekis_menesis","kiekis_partijai","kiekis_per_val",
                "ilgis_mm","plotis_mm","aukstis_mm","skersmuo_mm","storis_mm",
                "kabinimo_budas","kabliuku_kiekis","kabinimo_anga_mm","kabinti_per",
                "pakuotes_tipas","vienetai_dezeje","vienetai_paleje","pakuotes_pastabos",
                "testai_druskos_rukas_val","testas_adhezija","testas_storis_mikronai","testai_kita",
                "ppap_dokumentai","priedai_info",
            ]:
                self.fields[f].initial = getattr(d, f)
            if getattr(d, "specifikacija_id", None):
                s = d.specifikacija
                self.fields["spec_metalas"].initial = s.metalas
                self.fields["spec_plotas_m2"].initial = s.plotas_m2
                self.fields["spec_svoris_kg"].initial = s.svoris_kg
                self.fields["spec_medziagos_kodas"].initial = s.medziagos_kodas
            if getattr(d, "pavirsiu_dangos_id", None):
                g = d.pavirsiu_dangos
                self.fields["dang_ktl_ec_name"].initial = g.ktl_ec_name
                self.fields["dang_miltelinis_name"].initial = g.miltelinis_name
                self.fields["dang_spalva_ral"].initial = g.spalva_ral
                self.fields["dang_blizgumas"].initial = g.blizgumas

    def save(self, commit=True):
        uzk = super().save(commit=False)
        detale = self.cleaned_data.get("detale") or getattr(self.instance, "detale", None)
        if detale is None:
            detale = Detale.objects.create(pavadinimas=self.cleaned_data.get("detale_pavadinimas") or "Detalė")

        mapping = {
            "pavadinimas": "detale_pavadinimas",
            "brezinio_nr": "detale_brezinio_nr",
            "kiekis_metinis": "kiekis_metinis",
            "kiekis_menesis": "kiekis_menesis",
            "kiekis_partijai": "kiekis_partijai",
            "kiekis_per_val": "kiekis_per_val",
            "ilgis_mm": "ilgis_mm",
            "plotis_mm": "plotis_mm",
            "aukstis_mm": "aukstis_mm",
            "skersmuo_mm": "skersmuo_mm",
            "storis_mm": "storis_mm",
            "kabinimo_budas": "kabinimo_budas",
            "kabliuku_kiekis": "kabliuku_kiekis",
            "kabinimo_anga_mm": "kabinimo_anga_mm",
            "kabinti_per": "kabinti_per",
            "pakuotes_tipas": "pakuotes_tipas",
            "vienetai_dezeje": "vienetai_dezeje",
            "vienetai_paleje": "vienetai_paleje",
            "pakuotes_pastabos": "pakuotes_pastabos",
            "testai_druskos_rukas_val": "testai_druskos_rukas_val",
            "testas_adhezija": "testas_adhezija",
            "testas_storis_mikronai": "testas_storis_mikronai",
            "testai_kita": "testai_kita",
            "ppap_dokumentai": "ppap_dokumentai",
            "priedai_info": "priedai_info",
        }
        for model_field, form_field in mapping.items():
            val = self.cleaned_data.get(form_field)
            if val not in (None, ""):
                setattr(detale, model_field, val)
        detale.save()

        if any(self.cleaned_data.get(k) not in (None, "") for k in
               ["spec_metalas", "spec_plotas_m2", "spec_svoris_kg", "spec_medziagos_kodas"]):
            s = _get_or_create_spec(detale)
            if self.cleaned_data.get("spec_metalas"): s.metalas = self.cleaned_data["spec_metalas"]
            if self.cleaned_data.get("spec_plotas_m2") not in (None, ""): s.plotas_m2 = self.cleaned_data["spec_plotas_m2"]
            if self.cleaned_data.get("spec_svoris_kg") not in (None, ""): s.svoris_kg = self.cleaned_data["spec_svoris_kg"]
            if self.cleaned_data.get("spec_medziagos_kodas"): s.medziagos_kodas = self.cleaned_data["spec_medziagos_kodas"]
            s.save()

        if any(self.cleaned_data.get(k) not in (None, "") for k in
               ["dang_ktl_ec_name", "dang_miltelinis_name", "dang_spalva_ral", "dang_blizgumas"]):
            g = _get_or_create_dangos(detale)
            if self.cleaned_data.get("dang_ktl_ec_name"): g.ktl_ec_name = self.cleaned_data["dang_ktl_ec_name"]
            if self.cleaned_data.get("dang_miltelinis_name"): g.miltelinis_name = self.cleaned_data["dang_miltelinis_name"]
            if self.cleaned_data.get("dang_spalva_ral"): g.spalva_ral = self.cleaned_data["dang_spalva_ral"]
            if self.cleaned_data.get("dang_blizgumas"): g.blizgumas = self.cleaned_data["dang_blizgumas"]
            g.save()

        uzk.detale = detale
        if commit:
            uzk.save()
        return uzk
