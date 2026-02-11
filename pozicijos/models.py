# pozicijos/models.py
from __future__ import annotations

import os
from decimal import Decimal, InvalidOperation

from django.db import models
from django.utils.text import slugify
from simple_history.models import HistoricalRecords


class Pozicija(models.Model):
    MASKAVIMO_TIPAS_CHOICES = [
        ("nera", "Nėra"),
        ("yra", "Yra"),
    ]
    PAKAVIMO_TIPAS_CHOICES = [
        ("palaidas", "Palaidas"),
        ("standartinis", "Standartinis"),
        ("geras", "Geras"),
        ("individualus", "Individualus"),
    ]

    PAPILDOMOS_PASLAUGOS_CHOICES = [
        ("ne", "Nėra"),
        ("taip", "Yra"),
    ]

    # Pagrindiniai
    klientas = models.CharField("Klientas", max_length=255, blank=True, default="")
    projektas = models.CharField("Projektas", max_length=255, blank=True, default="")
    poz_kodas = models.CharField("Pozicijos kodas", max_length=100, blank=True, default="")
    poz_pavad = models.CharField("Pozicijos pavadinimas", max_length=255, blank=True, default="")

    # Medžiaga / detalė
    metalas = models.CharField("Metalas", max_length=120, blank=True, default="")
    metalo_storis = models.DecimalField(
        "Metalo storis",
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        default=None,
        help_text="Skaičius (pvz. 1.50).",
    )
    plotas = models.CharField("Plotas", max_length=120, blank=True, default="")
    svoris = models.CharField("Svoris", max_length=120, blank=True, default="")

    # Matmenys (mm)
    x_mm = models.DecimalField("X (mm)", max_digits=10, decimal_places=2, null=True, blank=True)
    y_mm = models.DecimalField("Y (mm)", max_digits=10, decimal_places=2, null=True, blank=True)
    z_mm = models.DecimalField("Z (mm)", max_digits=10, decimal_places=2, null=True, blank=True)

    # --- Kabinimas (KTL) ---
    ktl_kabinimo_budas = models.CharField("KTL kabinimo būdas", max_length=200, blank=True, default="")
    ktl_kabinimas_reme_txt = models.CharField("KTL kabinimas rėme", max_length=200, blank=True, default="")
    ktl_detaliu_kiekis_reme = models.IntegerField("KTL detalių kiekis rėme", null=True, blank=True)
    ktl_faktinis_kiekis_reme = models.IntegerField("KTL faktinis kiekis rėme", null=True, blank=True)
    ktl_ilgis_mm = models.DecimalField("KTL ilgis (mm)", max_digits=10, decimal_places=1, null=True, blank=True)
    ktl_aukstis_mm = models.DecimalField("KTL aukštis (mm)", max_digits=10, decimal_places=1, null=True, blank=True)
    ktl_gylis_mm = models.DecimalField("KTL gylis (mm)", max_digits=10, decimal_places=1, null=True, blank=True)
    ktl_kabinimas_aprasymas = models.TextField("KTL kabinimo aprašymas", blank=True, default="")

    # KTL dangos storis
    ktl_dangos_storis_um = models.DecimalField(
        "KTL dangos storis (µm)",
        max_digits=10,
        decimal_places=1,
        null=True,
        blank=True,
    )
    # NEW: tekstinis formatas (pvz. "12-13", "3<>6", "33 +/- 5")
    ktl_dangos_storis_txt = models.CharField(
        "KTL dangos storis (tekstas)",
        max_length=64,
        blank=True,
        default="",
    )

    # DB saugoma KTL matmenų sandauga (I×A×G)
    ktl_matmenu_sandauga_db = models.DecimalField(
        "KTL matmenų sandauga (I×A×G)",
        max_digits=20,
        decimal_places=3,
        null=True,
        blank=True,
    )

    # KTL pastabos
    ktl_pastabos = models.TextField("KTL pastabos", blank=True, default="")

    # --- Miltai ---
    miltai_kiekis_per_valanda = models.DecimalField(
        "Miltai: kiekis per valandą",
        max_digits=10,
        decimal_places=1,
        null=True,
        blank=True,
    )
    miltai_detaliu_kiekis_reme = models.IntegerField("Miltai: detalių kiekis rėme", null=True, blank=True)
    miltai_faktinis_kiekis_reme = models.IntegerField("Miltai: faktinis kiekis rėme", null=True, blank=True)
    miltai_kabinimas_aprasymas = models.TextField("Miltai: kabinimo aprašymas", blank=True, default="")

    miltai_faktinis_per_valanda = models.DecimalField(
        "Miltai: faktinis kiekis per valandą",
        max_digits=10,
        decimal_places=1,
        null=True,
        blank=True,
    )

    # Miltai dangos storis
    miltai_dangos_storis_um = models.DecimalField(
        "Miltai dangos storis (µm)",
        max_digits=10,
        decimal_places=1,
        null=True,
        blank=True,
    )
    # NEW: tekstinis formatas
    miltai_dangos_storis_txt = models.CharField(
        "Miltai dangos storis (tekstas)",
        max_length=64,
        blank=True,
        default="",
    )

    # Miltai pastabos
    miltai_pastabos = models.TextField("Miltai pastabos", blank=True, default="")

    # --- Paslauga (checkbox'ai) ---
    paslauga_ktl = models.BooleanField("KTL", default=False)
    paslauga_miltai = models.BooleanField("Miltai", default=False)
    paslauga_paruosimas = models.BooleanField("Paruošimas", default=False)

    # Legacy spalva
    spalva = models.CharField("Spalva", max_length=120, blank=True, default="")

    # Legacy bendras dangos storis
    padengimo_storis_um = models.CharField("Padengimo storis", max_length=120, blank=True, default="")

    # Miltų identifikacija
    miltu_kodas = models.CharField("Miltų kodas", max_length=120, blank=True, default="")
    miltu_spalva = models.CharField("Miltų spalva", max_length=120, blank=True, default="")
    miltu_tiekejas = models.CharField("Miltų tiekėjas", max_length=120, blank=True, default="")
    miltu_blizgumas = models.CharField("Miltų blizgumas", max_length=120, blank=True, default="")
    miltu_kaina = models.DecimalField("Miltų kaina", max_digits=12, decimal_places=4, null=True, blank=True)

    # Bendri paslaugos laukai
    paruosimas = models.CharField("Paruošimas", max_length=200, blank=True, default="")
    padengimas = models.CharField("Padengimas", max_length=200, blank=True, default="")
    padengimo_standartas = models.CharField("Padengimo standartas", max_length=200, blank=True, default="")
    paslaugu_pastabos = models.TextField("Paslaugų pastabos", blank=True, default="")

    # Kiekiai / laikotarpis
    partiju_dydziai = models.CharField("Partijų dydžiai", max_length=200, blank=True, default="")
    metinis_kiekis_nuo = models.IntegerField("Metinis kiekis nuo", null=True, blank=True)
    metinis_kiekis_iki = models.IntegerField("Metinis kiekis iki", null=True, blank=True)
    projekto_gyvavimo_nuo = models.DateField("Projekto gyvavimo nuo", null=True, blank=True)
    projekto_gyvavimo_iki = models.DateField("Projekto gyvavimo iki", null=True, blank=True)

    # Terminai / kokybė / pakavimas
    atlikimo_terminas = models.IntegerField("Atlikimo terminas (d.d.)", null=True, blank=True)
    atlikimo_terminas_data = models.DateField("Atlikimo terminas (data)", null=True, blank=True)
    testai_kokybe = models.CharField("Testai / kokybė", max_length=255, blank=True, default="")

    pakavimo_tipas = models.CharField(
        "Pakavimo tipas",
        max_length=20,
        choices=PAKAVIMO_TIPAS_CHOICES,
        blank=True,
        default="",
    )
    pakavimas = models.TextField("Pakavimas", blank=True, default="")
    instrukcija = models.TextField("Instrukcija", blank=True, default="")

    papildomos_paslaugos = models.CharField(
        "Papildomos paslaugos",
        max_length=10,
        choices=PAPILDOMOS_PASLAUGOS_CHOICES,
        default="ne",
    )
    papildomos_paslaugos_aprasymas = models.TextField("Papildomų paslaugų aprašymas", blank=True, default="")

    # Maskavimas / pastabos
    maskavimo_tipas = models.CharField(
        "Maskavimo tipas",
        max_length=10,
        choices=MASKAVIMO_TIPAS_CHOICES,
        default="nera",
    )
    maskavimas = models.TextField("Maskavimas", blank=True, default="")
    pastabos = models.TextField("Pastabos", blank=True, default="")

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["-updated", "-id"]

    def __str__(self):
        return self.poz_kodas or f"Pozicija #{self.pk}"

    @property
    def matmenys_xyz(self) -> str:
        vals = []
        for v in (self.x_mm, self.y_mm, self.z_mm):
            vals.append(str(v).rstrip("0").rstrip(".") if v is not None else "—")
        return " x ".join(vals)

    @property
    def metiniai_kiekiai_display(self) -> str:
        if self.metinis_kiekis_nuo is None and self.metinis_kiekis_iki is None:
            return ""
        return f"{self.metinis_kiekis_nuo or ''}–{self.metinis_kiekis_iki or ''}".strip("–")

    @property
    def projekto_gyvavimo_display(self) -> str:
        if not self.projekto_gyvavimo_nuo and not self.projekto_gyvavimo_iki:
            return ""
        nuo = self.projekto_gyvavimo_nuo.isoformat() if self.projekto_gyvavimo_nuo else ""
        iki = self.projekto_gyvavimo_iki.isoformat() if self.projekto_gyvavimo_iki else ""
        return f"{nuo}–{iki}".strip("–")

    @property
    def kaina_eur(self):
        akt = self.kainos_eilutes.filter(busena="aktuali").order_by("-prioritetas", "-id").first()
        return akt.kaina if akt else None

    @property
    def ktl_matmenu_sandauga(self):
        if self.ktl_matmenu_sandauga_db is not None:
            return self.ktl_matmenu_sandauga_db
        if self.ktl_ilgis_mm is None or self.ktl_aukstis_mm is None or self.ktl_gylis_mm is None:
            return None
        try:
            return (Decimal(self.ktl_ilgis_mm) * Decimal(self.ktl_aukstis_mm) * Decimal(self.ktl_gylis_mm)).quantize(
                Decimal("0.001")
            )
        except (InvalidOperation, TypeError):
            return None

    def save(self, *args, **kwargs):
        if self.ktl_ilgis_mm is not None and self.ktl_aukstis_mm is not None and self.ktl_gylis_mm is not None:
            try:
                self.ktl_matmenu_sandauga_db = (
                    Decimal(self.ktl_ilgis_mm) * Decimal(self.ktl_aukstis_mm) * Decimal(self.ktl_gylis_mm)
                ).quantize(Decimal("0.001"))
            except (InvalidOperation, TypeError):
                self.ktl_matmenu_sandauga_db = None
        else:
            self.ktl_matmenu_sandauga_db = None
        super().save(*args, **kwargs)

    @property
    def ktl_dangos_storis_display(self) -> str:
        if (self.ktl_dangos_storis_txt or "").strip():
            return self.ktl_dangos_storis_txt.strip()
        if self.ktl_dangos_storis_um is not None:
            s = str(self.ktl_dangos_storis_um)
            return s.rstrip("0").rstrip(".")
        return ""

    @property
    def miltai_dangos_storis_display(self) -> str:
        if (self.miltai_dangos_storis_txt or "").strip():
            return self.miltai_dangos_storis_txt.strip()
        if self.miltai_dangos_storis_um is not None:
            s = str(self.miltai_dangos_storis_um)
            return s.rstrip("0").rstrip(".")
        return ""


class MaskavimoEilute(models.Model):
    PASLAUGA_CHOICES = [
        ("ktl", "KTL"),
        ("miltai", "Miltai"),
    ]

    pozicija = models.ForeignKey(Pozicija, on_delete=models.CASCADE, related_name="maskavimo_eilutes")
    paslauga = models.CharField("Paslauga", max_length=10, choices=PASLAUGA_CHOICES, default="ktl")
    maskuote = models.CharField("Maskuotė", max_length=255, blank=True, default="")
    vietu_kiekis = models.PositiveIntegerField("Maskavimo vietų kiekis", null=True, blank=True)
    aprasymas = models.TextField("Aprašymas", blank=True, default="")
    created = models.DateTimeField("Sukurta", auto_now_add=True)
    updated = models.DateTimeField("Atnaujinta", auto_now=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.get_paslauga_display()} / {self.maskuote or '—'}"


class KainosEilute(models.Model):
    BUSENA_CHOICES = [
        ("aktuali", "Aktuali"),
        ("sena", "Sena"),
        ("pasiulymas", "Pasiūlymas"),
    ]

    pozicija = models.ForeignKey(Pozicija, on_delete=models.CASCADE, related_name="kainos_eilutes")
    kaina = models.DecimalField("Kaina", max_digits=12, decimal_places=4, null=True, blank=True)
    matas = models.CharField("Matas", max_length=50, blank=True, default="vnt.")
    yra_fiksuota = models.BooleanField("Yra fiksuota", default=False)
    fiksuotas_kiekis = models.IntegerField("Fiksuotas kiekis", null=True, blank=True)
    kiekis_nuo = models.IntegerField("Kiekis nuo", null=True, blank=True)
    kiekis_iki = models.IntegerField("Kiekis iki", null=True, blank=True)
    galioja_nuo = models.DateField("Galioja nuo", null=True, blank=True)
    galioja_iki = models.DateField("Galioja iki", null=True, blank=True)
    busena = models.CharField("Būsena", max_length=20, choices=BUSENA_CHOICES, default="aktuali")
    prioritetas = models.IntegerField("Prioritetas", default=0)
    pastaba = models.TextField("Pastaba", blank=True, default="")
    created = models.DateTimeField("Sukurta", auto_now_add=True)
    updated = models.DateTimeField("Atnaujinta", auto_now=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["-updated", "-id"]

    def __str__(self):
        return f"{self.pozicija_id} / {self.busena} / {self.kaina or '—'}"


def breziniu_upload_to(instance, filename: str):
    base, ext = os.path.splitext(filename)
    safe = slugify(base) or "brezinys"
    return f"pozicijos/{instance.pozicija_id}/{safe}{ext.lower()}"


class PozicijosBrezinys(models.Model):
    pozicija = models.ForeignKey(Pozicija, on_delete=models.CASCADE, related_name="breziniai")
    pavadinimas = models.CharField("Pavadinimas", max_length=255, blank=True)
    failas = models.FileField("Brėžinys", upload_to="pozicijos/breziniai/%Y/%m/")
    uploaded = models.DateTimeField(auto_now_add=True)

    preview = models.ImageField(
        "Miniatiūra",
        upload_to="pozicijos/breziniai/previews/",
        null=True,
        blank=True,
        help_text="Automatiškai sugeneruota PNG miniatiūra.",
    )

    class Meta:
        ordering = ["-uploaded"]

    def __str__(self):
        return self.pavadinimas or getattr(self.failas, "name", "")

    @property
    def filename(self) -> str:
        name = getattr(self.failas, "name", "") or ""
        return os.path.basename(name)

    @property
    def ext(self) -> str:
        _, ext = os.path.splitext(self.filename)
        return ext.lower().lstrip(".")

    @property
    def thumb_url(self):
        if self.preview:
            try:
                return self.preview.url
            except Exception:
                return None
        return None


class MetaloStorisEilute(models.Model):
    pozicija = models.ForeignKey(
        "Pozicija",
        on_delete=models.CASCADE,
        related_name="metalo_storio_eilutes",
        verbose_name="Pozicija",
    )
    storis_mm = models.DecimalField(
        "Metalo storis (mm)",
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    created = models.DateTimeField("Sukurta", auto_now_add=True)
    updated = models.DateTimeField("Atnaujinta", auto_now=True)

    class Meta:
        verbose_name = "Metalo storio eilutė"
        verbose_name_plural = "Metalo storio eilutės"
        ordering = ["id"]

    def __str__(self):
        if self.storis_mm is None:
            return f"#{self.pk} — ∅"
        return f"#{self.pk} — {self.storis_mm} mm"
