from __future__ import annotations

from decimal import Decimal

from django import forms
from django.forms import inlineformset_factory

from .models import Pozicija, KainosEilute

BUSENA_UI_CHOICES = [
    ("aktuali", "Aktuali"),
    ("neaktuali", "Neaktuali"),
]

MATAS_CHOICES = [
    ("Vnt.", "Vnt."),
    ("kg", "kg"),
    ("komplektas", "komplektas"),
]


class KainosEiluteForm(forms.ModelForm):
    """
    Intervalinė kainodara (be fiksuotos kainos UI).

    Taisyklė (sutarta):
    - Jei eilutė pažymėta DELETE -> jos nevaliduojam.
    - Jei eilutė nauja ir "efektyviai tuščia" -> leidžiam praeiti be klaidų ir jos neišsaugom.
    - Jei pildoma (užpildytas bent vienas iš esminių laukų) -> privaloma kaina.
      Kiekio intervalas (kiekis_nuo/kiekis_iki) yra PASIRENKAMAS:
        * jei pildomas bent vienas iš jų -> privaloma abu ir nuo <= iki.
        * jei abu tušti -> leidžiam kainą įvesti be detalių skaičiaus.
    - Esamai (instance.pk) eilutei (jei ne DELETE) visada taikom privalomumą (neleidžiam paversti į „tuščią“).
    """

    busena_ui = forms.ChoiceField(
        label="Būsena",
        choices=BUSENA_UI_CHOICES,
        required=True,
    )

    class Meta:
        model = KainosEilute
        fields = [
            "kaina",
            "matas",
            "kiekis_nuo",
            "kiekis_iki",
            "galioja_nuo",
            "galioja_iki",
            "pastaba",
        ]
        widgets = {
            "galioja_nuo": forms.DateInput(attrs={"type": "date", "class": "js-date"}),
            "galioja_iki": forms.DateInput(attrs={"type": "date", "class": "js-date"}),
            "pastaba": forms.Textarea(attrs={"rows": 1, "data-autoresize": "1"}),
        }

    # Esminiai laukai, pagal kuriuos sprendžiam "pildoma ar tuščia"
    _CORE_FIELDS = ("kaina", "kiekis_nuo", "kiekis_iki", "galioja_nuo", "galioja_iki", "pastaba")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # bendros klasės
        for _, f in self.fields.items():
            css = f.widget.attrs.get("class", "")
            f.widget.attrs["class"] = (css + " poz-field").strip()

        # Matas: select su ribotais pasirinkimais + initial suderinimas su UI default
        if "matas" in self.fields:
            self.fields["matas"].required = True
            self.fields["matas"].widget = forms.Select(choices=MATAS_CHOICES)

            default_matas = MATAS_CHOICES[0][0] if MATAS_CHOICES else None
            inst_matas = getattr(self.instance, "matas", None)
            self.fields["matas"].initial = inst_matas or default_matas

        # Skaitiniai – patogesni input'ai
        if "kaina" in self.fields:
            w = self.fields["kaina"].widget
            w.input_type = "text"
            w.attrs.setdefault("inputmode", "decimal")
            # UI reikalavimas: 4 skaitmenys po kablelio
            w.attrs.setdefault("placeholder", "0.0000")
            w.attrs.setdefault("data-decimals", "4")
            w.attrs.setdefault("autocomplete", "off")

            # Jei instance turi reikšmę – suformatuojam į 4 skaitmenis, kad UI rodytų 0.0000
            try:
                inst_val = getattr(self.instance, "kaina", None)
                if inst_val is not None and self.initial.get("kaina") in (None, ""):
                    self.initial["kaina"] = f"{Decimal(inst_val):.4f}"
            except Exception:
                pass

        for n in ("kiekis_nuo", "kiekis_iki"):
            if n in self.fields:
                w = self.fields[n].widget
                w.input_type = "text"
                w.attrs.setdefault("inputmode", "numeric")
                w.attrs.setdefault("placeholder", "")

        # Leisti tuščias naujas eilutes (validuosim patys clean'e, kai "pildoma")
        for n in ("kaina", "kiekis_nuo", "kiekis_iki", "galioja_nuo", "galioja_iki", "pastaba"):
            if n in self.fields:
                self.fields[n].required = False

        # Inicializuojam busena_ui iš DB (empty_form -> "aktuali")
        db_busena = getattr(self.instance, "busena", None) or "aktuali"
        self.fields["busena_ui"].initial = "aktuali" if db_busena == "aktuali" else "neaktuali"

        # Vidiniai flag'ai:
        self._skip_model_validation = False
        self._skip_save = False

    def _is_new(self) -> bool:
        return not bool(getattr(self.instance, "pk", None))

    def _is_effectively_empty(self, cleaned: dict | None = None) -> bool:
        """
        Tuščia laikom tik naują eilutę (instance.pk nėra), kai neįvesta nieko iš CORE laukų.
        """
        if not self._is_new():
            return False

        data = cleaned if cleaned is not None else getattr(self, "cleaned_data", None)
        if not isinstance(data, dict):
            return False

        for key in self._CORE_FIELDS:
            val = data.get(key)
            if val is None:
                continue
            if isinstance(val, str):
                if val.strip() != "":
                    return False
            else:
                # date/decimal/int ir pan.
                return False
        return True

    def clean(self):
        cleaned = super().clean()

        # Jei pažymėta trinti – nevaliduojam
        if cleaned.get("DELETE"):
            return cleaned

        # UI -> DB busena
        bus_ui = cleaned.get("busena_ui") or "aktuali"
        cleaned["busena"] = "aktuali" if bus_ui == "aktuali" else "sena"

        # Nauja ir tuščia -> leidžiam praeiti, bet neišsaugom ir praleidžiam model validation
        if self._is_new() and self._is_effectively_empty(cleaned):
            self._skip_model_validation = True
            self._skip_save = True
            return cleaned

        # Esamai eilutei (ir naujai pildomai) – privalomumai
        kn = cleaned.get("kiekis_nuo")
        kk = cleaned.get("kiekis_iki")
        kaina = cleaned.get("kaina")

        def _blank(v) -> bool:
            if v is None:
                return True
            if isinstance(v, str):
                return v.strip() == ""
            return False

        # 1) Kaina – visada privaloma, jei eilutė nėra "efektyviai tuščia" (tą aukščiau jau atfiltravom)
        if _blank(kaina):
            self.add_error("kaina", "Privaloma užpildyti „Kaina“.")

        # 2) Kiekio intervalas – neprivalomas. Bet jei pildomas bent vienas -> privaloma abu.
        has_any_qty = (not _blank(kn)) or (not _blank(kk))
        if has_any_qty:
            if _blank(kn):
                self.add_error("kiekis_nuo", "Jei nurodai intervalą – privaloma užpildyti „Kiekis nuo“.")
            if _blank(kk):
                self.add_error("kiekis_iki", "Jei nurodai intervalą – privaloma užpildyti „Kiekis iki“.")

            # jei abu yra – logika
            try:
                if not _blank(kn) and not _blank(kk):
                    if int(kn) > int(kk):
                        self.add_error(
                            "kiekis_iki",
                            "„Kiekis iki“ turi būti didesnis arba lygus „Kiekis nuo“.",
                        )
            except Exception:
                # jei vartotojas įvedė ne skaičių – Django pats paprastai duoda klaidą
                pass

        return cleaned

    def _post_clean(self):
        # Jei nauja tuščia eilutė – praleidžiam model full_clean, kad niekas nebandytų jos versti "privaloma"
        if getattr(self, "_skip_model_validation", False):
            return
        super()._post_clean()

    def save(self, commit=True):
        # Jei sutarta: tuščios naujos eilutės nesaugom
        if getattr(self, "_skip_save", False):
            return self.instance

        inst: KainosEilute = super().save(commit=False)

        # busena_ui -> inst.busena
        bus_ui = self.cleaned_data.get("busena_ui") or "aktuali"
        inst.busena = "aktuali" if bus_ui == "aktuali" else "sena"

        # kad neliktų fiksuotos logikos DB lygyje (UI jos nebėra)
        if hasattr(inst, "yra_fiksuota"):
            inst.yra_fiksuota = False
        if hasattr(inst, "fiksuotas_kiekis"):
            inst.fiksuotas_kiekis = None

        if commit:
            inst.save()
        return inst


KainaFormSet = inlineformset_factory(
    Pozicija,
    KainosEilute,
    form=KainosEiluteForm,
    extra=0,
    can_delete=True,
)

KainaFormSetNoDelete = inlineformset_factory(
    Pozicija,
    KainosEilute,
    form=KainosEiluteForm,
    extra=0,
    can_delete=False,
)
