from django.db import models
from uuid import uuid4
from pathlib import Path
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from simple_history.models import HistoricalRecords


def upload_drawing(instance, filename):
    ext = Path(filename).suffix.lower()
    return f"breziniai/{instance.detale_id or 'unknown'}/{uuid4().hex}{ext}"

IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".gif", ".svg"}
PDF_EXT = {".pdf"}
CAD_EXT = {".dxf", ".dwg"}
ALL_EXT = IMG_EXT | PDF_EXT | CAD_EXT

TIPAI = [("img", "Vaizdas"), ("pdf", "PDF"), ("cad", "CAD")]


class Brezinys(models.Model):
    detale = models.ForeignKey("Detale", on_delete=models.CASCADE, related_name="breziniai")
    pavadinimas = models.CharField(max_length=255, blank=True)
    versija = models.CharField(max_length=64, blank=True, null=True)
    tipas = models.CharField(max_length=10, choices=TIPAI, default="img")
    failas = models.FileField(
        upload_to=upload_drawing,
        blank=True, null=True,
        validators=[FileExtensionValidator(allowed_extensions=[e[1:] for e in sorted(ALL_EXT)])],
    )
    isorinis_url = models.URLField(blank=True, null=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created",)

    def __str__(self):
        return self.pavadinimas or (self.failas.name if self.failas else self.isorinis_url) or f"Brezinys #{self.pk}"

    @staticmethod
    def detect_type_by_ext(name: str) -> str:
        ext = Path(name or "").suffix.lower()
        if ext in IMG_EXT: return "img"
        if ext in PDF_EXT: return "pdf"
        if ext in CAD_EXT: return "cad"
        return "img"  # numatyta

    @property
    def is_image(self) -> bool:
        if self.failas:
            return Path(self.failas.name).suffix.lower() in IMG_EXT
        return False

    def clean(self):
        if not self.failas and not self.isorinis_url:
            raise ValidationError("Reikia failo arba išorinio URL.")
        if self.failas and self.failas.size > 50 * 1024 * 1024:  # 50 MB pvz.
            raise ValidationError("Failas per didelis (maks. 50 MB).")

    def save(self, *args, **kwargs):
        # auto nustatyk tipą pagal failo plėtinį (jei nepaduotas)
        if not self.tipas:
            src = self.failas.name if self.failas else self.isorinis_url or ""
            self.tipas = Brezinys.detect_type_by_ext(src)
        return super().save(*args, **kwargs)

# --- Bazinė laiko žymų klasė: BŪTINAI abstract ---
class Timestamped(models.Model):
    created = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated = models.DateTimeField(auto_now=True, null=True, blank=True)

    class Meta:
        abstract = True


# --- Pagrindiniai katalogai ---
class Klientas(Timestamped):
    vardas = models.CharField(max_length=255)

    # istorija
    history = HistoricalRecords()

    def __str__(self):
        return self.vardas


class Projektas(Timestamped):
    klientas = models.ForeignKey(Klientas, on_delete=models.CASCADE, related_name="projektai")
    pavadinimas = models.CharField(max_length=255)
    aprasymas = models.TextField(blank=True, null=True)

    # istorija
    history = HistoricalRecords()

    def __str__(self):
        return self.pavadinimas


class Detale(Timestamped):
    pavadinimas = models.CharField(max_length=255)
    brezinio_nr = models.CharField(max_length=255, blank=True, null=True)

    # kiekiai
    kiekis_metinis = models.IntegerField(blank=True, null=True)
    kiekis_menesis = models.IntegerField(blank=True, null=True)
    kiekis_partijai = models.IntegerField(blank=True, null=True)
    kiekis_per_val = models.IntegerField(blank=True, null=True)

    # matmenys
    ilgis_mm = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    plotis_mm = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    aukstis_mm = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    skersmuo_mm = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    storis_mm = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)

    # kabinimas
    kabinimo_budas = models.CharField(max_length=255, blank=True, null=True)
    kabliuku_kiekis = models.IntegerField(blank=True, null=True)
    kabinimo_anga_mm = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    kabinti_per = models.CharField(max_length=255, blank=True, null=True)

    # pakuotė
    pakuotes_tipas = models.CharField(max_length=255, blank=True, null=True)
    vienetai_dezeje = models.IntegerField(blank=True, null=True)
    vienetai_paleje = models.IntegerField(blank=True, null=True)
    pakuotes_pastabos = models.CharField(max_length=255, blank=True, null=True)

    # testai
    testai_druskos_rukas_val = models.IntegerField(blank=True, null=True)
    testas_adhezija = models.CharField(max_length=255, blank=True, null=True)
    testas_storis_mikronai = models.IntegerField(blank=True, null=True)
    testai_kita = models.CharField(max_length=255, blank=True, null=True)

    # dokumentai/pastabos
    ppap_dokumentai = models.CharField(max_length=255, blank=True, null=True)
    priedai_info = models.CharField(max_length=255, blank=True, null=True)

    # istorija
    history = HistoricalRecords()

    def __str__(self):
        return f"{self.pavadinimas} ({self.brezinio_nr or '—'})"


class DetaleSpecifikacija(Timestamped):
    detale = models.OneToOneField(Detale, on_delete=models.CASCADE, related_name="specifikacija")
    metalas = models.CharField(max_length=255, blank=True, null=True)
    plotas_m2 = models.DecimalField(max_digits=12, decimal_places=4, blank=True, null=True)
    svoris_kg = models.DecimalField(max_digits=12, decimal_places=4, blank=True, null=True)
    medziagos_kodas = models.CharField(max_length=255, blank=True, null=True)

    # istorija
    history = HistoricalRecords()

    def __str__(self):
        return f"Specifikacija: {self.detale}"


class PavirsiuDangos(Timestamped):
    detale = models.OneToOneField(Detale, on_delete=models.CASCADE, related_name="pavirsiu_dangos")
    ktl_ec_name = models.CharField(max_length=255, blank=True, null=True)
    miltelinis_name = models.CharField(max_length=255, blank=True, null=True)
    spalva_ral = models.CharField(max_length=64, blank=True, null=True)
    blizgumas = models.CharField(max_length=128, blank=True, null=True)

    # istorija
    history = HistoricalRecords()

    def __str__(self):
        return f"Dangos: {self.detale}"


# --- Užklausa ---
class Uzklausa(Timestamped):
    klientas = models.ForeignKey(Klientas, on_delete=models.SET_NULL, null=True, blank=True, related_name="uzklausos")
    projektas = models.ForeignKey(Projektas, on_delete=models.SET_NULL, null=True, blank=True, related_name="uzklausos")
    detale = models.ForeignKey(Detale, on_delete=models.SET_NULL, null=True, blank=True, related_name="uzklausos")
    pastabos = models.TextField(blank=True, null=True)

    # data auto_now_add buvo minėta – laikomės jos
    data = models.DateField(auto_now_add=True, null=True, blank=True)

    # istorija
    history = HistoricalRecords()

    def __str__(self):
        return f"Užklausa #{self.pk}"


# --- KAINA (pažangioji) ---
class Kaina(Timestamped):
    MATAS_CHOICES = [
        ("vnt", "Vnt"),
        ("m2", "m²"),
        ("kg", "kg"),
        ("val", "val."),
    ]

    uzklausa = models.ForeignKey(Uzklausa, on_delete=models.CASCADE, related_name="kainos")
    suma = models.DecimalField(max_digits=12, decimal_places=2)
    valiuta = models.CharField(max_length=10, default="EUR")
    busena = models.CharField(
        max_length=10,
        choices=[("aktuali", "Aktuali"), ("sena", "Sena")],
        default="aktuali",
    )

    # pažangioji kainodara
    yra_fiksuota = models.BooleanField(default=False)
    kiekis_nuo = models.PositiveIntegerField(null=True, blank=True)
    kiekis_iki = models.PositiveIntegerField(null=True, blank=True)
    fiksuotas_kiekis = models.PositiveIntegerField(null=True, blank=True)
    kainos_matas = models.CharField(max_length=8, choices=MATAS_CHOICES, null=True, blank=True)

    # istorija
    history = HistoricalRecords()

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        base = f"{self.suma} {self.valiuta}"
        if self.yra_fiksuota and self.fiksuotas_kiekis:
            return f"{base} ({self.fiksuotas_kiekis} {self.kainos_matas or ''}, {self.busena})"
        if self.kiekis_nuo or self.kiekis_iki:
            r1 = self.kiekis_nuo or 0
            r2 = self.kiekis_iki or "∞"
            return f"{base} [{r1}–{r2}] ({self.busena})"
        return f"{base} ({self.busena})"


# --- Kainodaros lentelės (jei buvo naudotos admin Inline) ---
class Kainodara(Timestamped):
    """Bendresnė kainodaros „antraštė“. Jei nenaudoji – palik, nes admin gali ją referencinti."""
    uzklausa = models.ForeignKey(Uzklausa, on_delete=models.CASCADE, related_name="kainodaros")
    pavadinimas = models.CharField(max_length=255, blank=True, null=True)

    # istorija
    history = HistoricalRecords()

    def __str__(self):
        return f"Kainodara #{self.pk} ({self.pavadinimas or 'be pavadinimo'})"


class KainosPartijai(Timestamped):
    """Eilutės priklausančios konkrečiai Kainodarai (vienas FK).
       Jei tau realiai reikia dviejų FK į Kainodara – pasakyk, paruošiu alternatyvą ir admin fk_name atitinkamai."""
    kainodara = models.ForeignKey(Kainodara, on_delete=models.CASCADE, related_name="partijos")

    # laukai (palieku minimaliai; gali praplėsti pagal poreikį)
    kiekis_nuo = models.PositiveIntegerField(null=True, blank=True)
    kiekis_iki = models.PositiveIntegerField(null=True, blank=True)
    suma = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    valiuta = models.CharField(max_length=10, default="EUR")

    # istorija
    history = HistoricalRecords()

    def __str__(self):
        r1 = self.kiekis_nuo or 0
        r2 = self.kiekis_iki or "∞"
        return f"{self.kainodara} [{r1}–{r2}] = {self.suma or '—'} {self.valiuta}"


class LegacyKaina(Timestamped):
    MATAS_CHOICES = [
        ("vnt", "Vnt"),
        ("m2", "m²"),
        ("kg", "kg"),
        ("val", "val."),
    ]

    uzklausa = models.ForeignKey("Uzklausa", on_delete=models.CASCADE, related_name="legacy_kainos")

    suma = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    valiuta = models.CharField(max_length=10, default="EUR")
    busena = models.CharField(
        max_length=10,
        choices=[("aktuali", "Aktuali"), ("sena", "Sena")],
        default="sena",
    )


    kiekis_nuo = models.PositiveIntegerField(null=True, blank=True)
    kiekis_iki = models.PositiveIntegerField(null=True, blank=True)
    fiksuotas_kiekis = models.PositiveIntegerField(null=True, blank=True)
    yra_fiksuota = models.BooleanField(default=False)
    kainos_matas = models.CharField(max_length=10, choices=MATAS_CHOICES, null=True, blank=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        base = f"{self.suma or '—'} {self.valiuta}"
        if self.yra_fiksuota and self.fiksuotas_kiekis:
            return f"{base} ({self.fiksuotas_kiekis} {self.kainos_matas or ''}, {self.busena})"
        if self.kiekis_nuo or self.kiekis_iki:
            r1 = self.kiekis_nuo or 0
            r2 = self.kiekis_iki or "∞"
            return f"{base} [{r1}–{r2}] ({self.busena})"
        return f"{base} ({self.busena})"


