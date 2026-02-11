# pozicijos/forms.py
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from django import forms
from django.forms import modelformset_factory

from .models import Pozicija, PozicijosBrezinys, MaskavimoEilute


KTL_KABINIMO_CHOICES = [
    ("", "—"),
    ("girliandos", "Girliandos"),
    ("traversas", "Traversas"),
    ("pakabos", "Pakabos"),
    ("specialus", "Specialus"),
]

_RE_NUM = re.compile(r"^\d+(?:[.,]\d+)?$")
_RE_RANGE = re.compile(r"^\d+(?:[.,]\d+)?\s*(?:-|\.\.|<>|to)\s*\d+(?:[.,]\d+)?$", re.IGNORECASE)
_RE_CMP = re.compile(r"^(>=|<=|>|<)\s*\d+(?:[.,]\d+)?$")
_RE_PM = re.compile(r"^\d+(?:[.,]\d+)?\s*(?:\+/-|±)\s*\d+(?:[.,]\d+)?$")


def _norm_thickness(value: str) -> str:
    s = (value or "").strip()
    if not s:
        return ""

    s = s.replace("–", "-").replace("—", "-").replace("−", "-")
    s = s.replace("±", "+/-")
    s = re.sub(r"\.\.", "-", s)
    s = re.sub(r"\bto\b", "-", s, flags=re.IGNORECASE)
    s = s.replace(",", ".")
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s*-\s*", "-", s)
    s = re.sub(r"\s*<>\s*", "<>", s)
    s = re.sub(r"\s*\+/-\s*", "+/-", s)
    s = re.sub(r"^(>=|<=|>|<)\s*", r"\1", s)
    return s


def _parse_decimal_1dp(s: str) -> Decimal:
    return Decimal(s.replace(",", ".")).quantize(Decimal("0.1"))


def _validate_thickness_expr(raw: str) -> tuple[str, Decimal | None]:
    s = _norm_thickness(raw)
    if not s:
        return "", None

    if _RE_NUM.fullmatch(s):
        return s, _parse_decimal_1dp(s)

    if _RE_RANGE.fullmatch(s):
        a, b = re.split(r"-|<>", s)
        da = Decimal(a)
        db = Decimal(b)
        if da > db:
            raise forms.ValidationError("Intervale kairė reikšmė negali būti didesnė už dešinę.")
        return s, None

    if _RE_PM.fullmatch(s):
        left, right = s.split("+/-")
        d_right = Decimal(right)
        if d_right < 0:
            raise forms.ValidationError("Po '+/-' turi būti teigiamas skaičius.")
        _ = Decimal(left)
        return s, None

    if _RE_CMP.fullmatch(s):
        return s, None

    raise forms.ValidationError("Netinkamas formatas. Pvz.: 12.5, 12-13, 3<>6, 33 +/- 5, >=12")


def _to_int_str(v):
    if v is None or v == "":
        return ""
    try:
        d = Decimal(str(v))
        return str(int(d))
    except Exception:
        return str(v)


class PozicijaForm(forms.ModelForm):
    ktl_dangos_storis_um = forms.CharField(
        required=False,
        label="KTL dangos storis (µm)",
        widget=forms.TextInput(attrs={"placeholder": "pvz. 12-13, 3<>6, 33 +/- 5"}),
    )
    miltai_dangos_storis_um = forms.CharField(
        required=False,
        label="Miltai dangos storis (µm)",
        widget=forms.TextInput(attrs={"placeholder": "pvz. 12-13, 3<>6, 33 +/- 5"}),
    )

    class Meta:
        model = Pozicija
        fields = [
            "klientas", "projektas", "poz_kodas", "poz_pavad",
            "metalas", "metalo_storis", "plotas", "svoris", "x_mm", "y_mm", "z_mm",
            "paslauga_ktl", "paslauga_miltai", "paslauga_paruosimas", "paruosimas", "padengimas", "padengimo_standartas",
            "partiju_dydziai", "metinis_kiekis_nuo", "metinis_kiekis_iki", "projekto_gyvavimo_nuo", "projekto_gyvavimo_iki",
            "spalva",

            "ktl_kabinimo_budas", "ktl_kabinimas_reme_txt", "ktl_detaliu_kiekis_reme", "ktl_faktinis_kiekis_reme",
            "ktl_ilgis_mm", "ktl_aukstis_mm", "ktl_gylis_mm", "ktl_kabinimas_aprasymas", "ktl_dangos_storis_um", "ktl_pastabos",

            "miltu_kodas", "miltu_spalva", "miltu_tiekejas", "miltu_blizgumas", "miltu_kaina",
            "miltai_kiekis_per_valanda", "miltai_faktinis_per_valanda", "miltai_detaliu_kiekis_reme",
            "miltai_faktinis_kiekis_reme", "miltai_kabinimas_aprasymas", "miltai_dangos_storis_um", "miltai_pastabos",

            "paslaugu_pastabos",
            "atlikimo_terminas", "testai_kokybe",
            "pakavimo_tipas", "pakavimas", "instrukcija",
            "papildomos_paslaugos", "papildomos_paslaugos_aprasymas",
            "pastabos",
        ]
        labels = {"pakavimas": "Aprašymas", "instrukcija": "Pastabos"}
        widgets = {
            "atlikimo_terminas": forms.NumberInput(attrs={"min": 0, "step": 1, "inputmode": "numeric"}),
            "metalo_storis": forms.NumberInput(attrs={"min": 0, "step": "0.01", "inputmode": "decimal", "placeholder": "mm"}),
            "instrukcija": forms.Textarea(attrs={"rows": 2, "data-autoresize": "1"}),
            "paslaugu_pastabos": forms.Textarea(attrs={"rows": 2, "data-autoresize": "1"}),
            "papildomos_paslaugos_aprasymas": forms.Textarea(attrs={"rows": 2, "data-autoresize": "1"}),
            "pastabos": forms.Textarea(attrs={"rows": 3, "data-autoresize": "1"}),

            "x_mm": forms.NumberInput(attrs={"min": 0, "step": "0.01", "inputmode": "decimal", "placeholder": "mm"}),
            "y_mm": forms.NumberInput(attrs={"min": 0, "step": "0.01", "inputmode": "decimal", "placeholder": "mm"}),
            "z_mm": forms.NumberInput(attrs={"min": 0, "step": "0.01", "inputmode": "decimal", "placeholder": "mm"}),

            "ktl_kabinimo_budas": forms.Select(choices=KTL_KABINIMO_CHOICES),
            "ktl_kabinimas_reme_txt": forms.TextInput(attrs={"placeholder": "įrašysite ranka"}),
            "ktl_detaliu_kiekis_reme": forms.NumberInput(attrs={"min": 0, "step": 1, "inputmode": "numeric"}),
            "ktl_faktinis_kiekis_reme": forms.NumberInput(attrs={"min": 0, "step": 1, "inputmode": "numeric"}),
            "ktl_ilgis_mm": forms.NumberInput(attrs={"min": 0, "step": "1", "inputmode": "numeric"}),
            "ktl_aukstis_mm": forms.NumberInput(attrs={"min": 0, "step": "1", "inputmode": "numeric"}),
            "ktl_gylis_mm": forms.NumberInput(attrs={"min": 0, "step": "1", "inputmode": "numeric"}),
            "ktl_kabinimas_aprasymas": forms.Textarea(attrs={"rows": 2, "data-autoresize": "1"}),
            "ktl_pastabos": forms.Textarea(attrs={"rows": 2, "data-autoresize": "1"}),

            "miltu_kaina": forms.NumberInput(attrs={"min": 0, "step": "0.0001", "inputmode": "decimal", "data-decimals": "4"}),
            "miltai_kiekis_per_valanda": forms.NumberInput(attrs={"min": 0, "step": "0.1", "inputmode": "decimal", "data-decimals": "1"}),
            "miltai_faktinis_per_valanda": forms.NumberInput(attrs={"min": 0, "step": "0.1", "inputmode": "decimal", "data-decimals": "1"}),
            "miltai_detaliu_kiekis_reme": forms.NumberInput(attrs={"min": 0, "step": 1, "inputmode": "numeric"}),
            "miltai_faktinis_kiekis_reme": forms.NumberInput(attrs={"min": 0, "step": 1, "inputmode": "numeric"}),
            "miltai_kabinimas_aprasymas": forms.Textarea(attrs={"rows": 2, "data-autoresize": "1"}),
            "miltai_pastabos": forms.Textarea(attrs={"rows": 2, "data-autoresize": "1"}),

            "partiju_dydziai": forms.TextInput(attrs={"placeholder": "pvz. 50, 100, 250"}),
            "metinis_kiekis_nuo": forms.NumberInput(attrs={"min": 0}),
            "metinis_kiekis_iki": forms.NumberInput(attrs={"min": 0}),
            "projekto_gyvavimo_nuo": forms.DateInput(attrs={"type": "date"}),
            "projekto_gyvavimo_iki": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if "ktl_ilgis_mm" in self.fields:
            self.fields["ktl_ilgis_mm"].label = "I"
            self.fields["ktl_aukstis_mm"].label = "A"
            self.fields["ktl_gylis_mm"].label = "G"

        # Edit lange I/A/G rodom be .0
        if self.instance and self.instance.pk and not self.is_bound:
            self.initial["ktl_ilgis_mm"] = _to_int_str(self.instance.ktl_ilgis_mm)
            self.initial["ktl_aukstis_mm"] = _to_int_str(self.instance.ktl_aukstis_mm)
            self.initial["ktl_gylis_mm"] = _to_int_str(self.instance.ktl_gylis_mm)

        # initial rodymas dangos storiams
        if self.instance and self.instance.pk:
            if getattr(self.instance, "ktl_dangos_storis_txt", ""):
                self.fields["ktl_dangos_storis_um"].initial = self.instance.ktl_dangos_storis_txt
            elif self.instance.ktl_dangos_storis_um is not None:
                self.fields["ktl_dangos_storis_um"].initial = str(self.instance.ktl_dangos_storis_um)

            if getattr(self.instance, "miltai_dangos_storis_txt", ""):
                self.fields["miltai_dangos_storis_um"].initial = self.instance.miltai_dangos_storis_txt
            elif self.instance.miltai_dangos_storis_um is not None:
                self.fields["miltai_dangos_storis_um"].initial = str(self.instance.miltai_dangos_storis_um)

        if not getattr(self.instance, "pk", None):
            if "papildomos_paslaugos" in self.fields:
                self.fields["papildomos_paslaugos"].initial = "ne"

    def clean(self):
        cleaned = super().clean()

        metalo_storis_raw = (self.data.get("metalo_storis") or "").strip()
        if metalo_storis_raw:
            try:
                cleaned["metalo_storis"] = Decimal(metalo_storis_raw.replace(",", ".")).quantize(Decimal("0.01"))
            except (InvalidOperation, ValueError):
                self.add_error("metalo_storis", "Įveskite skaičių (mm), pvz. 1.50")

        try:
            ktl_raw = (self.data.get("ktl_dangos_storis_um") or "").strip()
            ktl_txt, ktl_num = _validate_thickness_expr(ktl_raw)
            cleaned["ktl_dangos_storis_um"] = ktl_num
            cleaned["ktl_dangos_storis_txt"] = ktl_txt
        except forms.ValidationError as e:
            self.add_error("ktl_dangos_storis_um", e)

        try:
            m_raw = (self.data.get("miltai_dangos_storis_um") or "").strip()
            m_txt, m_num = _validate_thickness_expr(m_raw)
            cleaned["miltai_dangos_storis_um"] = m_num
            cleaned["miltai_dangos_storis_txt"] = m_txt
        except forms.ValidationError as e:
            self.add_error("miltai_dangos_storis_um", e)

        ktl = bool(cleaned.get("paslauga_ktl"))
        miltai = bool(cleaned.get("paslauga_miltai"))
        par = bool(cleaned.get("paslauga_paruosimas"))

        if ktl or miltai:
            cleaned["paslauga_paruosimas"] = True
            par = True

        def _is_empty(v):
            return not (v or "").strip()

        if par and (not ktl) and (not miltai):
            if _is_empty(cleaned.get("paruosimas", "")):
                cleaned["paruosimas"] = "Gardobond 24T"

        if ktl:
            if _is_empty(cleaned.get("padengimas", "")):
                cleaned["padengimas"] = "KTL BASF CG 570"
            if cleaned.get("padengimo_standartas", None) is None:
                cleaned["padengimo_standartas"] = ""

        miltu_sp = (cleaned.get("miltu_spalva") or "").strip()
        if miltai and miltu_sp:
            cleaned["spalva"] = miltu_sp
        elif not miltai:
            cleaned["spalva"] = ""

        pp = (cleaned.get("papildomos_paslaugos") or "ne").strip().lower()
        pp_txt = (cleaned.get("papildomos_paslaugos_aprasymas") or "").strip()
        if pp not in ("ne", "taip"):
            pp = "ne"
        cleaned["papildomos_paslaugos"] = pp
        if pp == "ne":
            cleaned["papildomos_paslaugos_aprasymas"] = ""
        elif not pp_txt:
            self.add_error("papildomos_paslaugos_aprasymas", "Kai pasirinkta „Taip“, aprašymas yra privalomas.")

        mk_nuo = cleaned.get("metinis_kiekis_nuo")
        mk_iki = cleaned.get("metinis_kiekis_iki")
        if mk_nuo is not None and mk_iki is not None and mk_nuo > mk_iki:
            self.add_error("metinis_kiekis_nuo", "„Nuo“ negali būti didesnis už „Iki“.")
            self.add_error("metinis_kiekis_iki", "„Iki“ negali būti mažesnis už „Nuo“.")

        pg_nuo = cleaned.get("projekto_gyvavimo_nuo")
        pg_iki = cleaned.get("projekto_gyvavimo_iki")
        if pg_nuo and pg_iki and pg_nuo > pg_iki:
            self.add_error("projekto_gyvavimo_nuo", "„Nuo“ negali būti vėliau už „Iki“.")
            self.add_error("projekto_gyvavimo_iki", "„Iki“ negali būti anksčiau už „Nuo“.")

        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.ktl_dangos_storis_txt = self.cleaned_data.get("ktl_dangos_storis_txt", "") or ""
        obj.miltai_dangos_storis_txt = self.cleaned_data.get("miltai_dangos_storis_txt", "") or ""
        if commit:
            obj.save()
            self.save_m2m()
        return obj


class PozicijosBrezinysForm(forms.ModelForm):
    class Meta:
        model = PozicijosBrezinys
        fields = ["pavadinimas", "failas"]


MaskavimoKTLFormSet = modelformset_factory(
    MaskavimoEilute,
    fields=["maskuote", "vietu_kiekis", "aprasymas"],
    extra=0,
    can_delete=True,
)

MaskavimoMiltaiFormSet = modelformset_factory(
    MaskavimoEilute,
    fields=["maskuote", "vietu_kiekis", "aprasymas"],
    extra=0,
    can_delete=True,
)

# Backward-compat alias senam views importui
MaskavimoFormSet = MaskavimoKTLFormSet
