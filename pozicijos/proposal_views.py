from __future__ import annotations

import io
import os
import tempfile
from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode, urlparse
from xml.sax.saxutils import escape as xml_escape

from PIL import Image
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle

from .models import Pozicija


# ============================================================================
# Helpers
# ============================================================================

def _get_lang(request) -> str:
    lang = (request.GET.get("lang") or "lt").lower()
    return "en" if lang.startswith("en") else "lt"


def _as_bool(v: str | None, default: bool = False) -> bool:
    if v is None:
        return default
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


def _fmt_mm(v) -> str:
    if v is None:
        return ""
    s = str(v)
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def _fmt_price(value, places: int = 4) -> str:
    """
    Kainos atvaizdavimas PDF'e su lietuvišku kableliu.
    DB lieka Decimal su tašku.
    """
    if value is None or value == "":
        return ""
    try:
        decimal_value = Decimal(str(value).replace(",", "."))
        quant = Decimal("1").scaleb(-places)
        return f"{decimal_value.quantize(quant):.{places}f}".replace(".", ",")
    except (InvalidOperation, TypeError, ValueError):
        return str(value)


def _humanize_case(value: str) -> str:
    v = (value or "").strip()
    if not v:
        return v
    return v[:1].upper() + v[1:]


def _make_paragraph(text: str, style: ParagraphStyle) -> Paragraph:
    safe = xml_escape(text or "").replace("\n", "<br/>")
    return Paragraph(safe, style)


def _fmt_local_date(value) -> str:
    if not value:
        return ""
    try:
        if timezone.is_aware(value):
            value = timezone.localtime(value)
        if hasattr(value, "strftime"):
            return value.strftime("%Y-%m-%d")
    except Exception:
        pass
    return str(value)[:10]


# ============================================================================
# Labels / translations
# ============================================================================

LANG_LABELS = {
    "lt": {
        "offer_title": "Komercinis pasiūlymas",
        "date_label": "Data",
        "request_date_label": "Užklausos data",
        "section_main": "Pagrindinė informacija",
        "section_prices": "Kainos (aktualios eilutės)",
        "section_drawings": "Brėžinių miniatiūros",
        "section_notes": "Pastabos",
        "no_data": "Nėra duomenų.",
        "no_prices": "Nėra aktyvių kainų eilučių šiai detalei.",
        "no_drawings": "Nėra brėžinių.",
        "col_price": "Kaina",
        "col_unit": "Matas",
        "col_qty_from": "Kiekis nuo",
        "col_qty_to": "Kiekis iki",
        "col_valid_from": "Galioja nuo",
        "col_valid_to": "Galioja iki",
        "col_note": "Pastaba",
    },
    "en": {
        "offer_title": "Commercial offer",
        "date_label": "Date",
        "request_date_label": "Request date",
        "section_main": "Main information",
        "section_prices": "Prices (active lines)",
        "section_drawings": "Drawing thumbnails",
        "section_notes": "Notes",
        "no_data": "No data.",
        "no_prices": "No active price lines for this position.",
        "no_drawings": "No drawings.",
        "col_price": "Price",
        "col_unit": "Unit",
        "col_qty_from": "Qty from",
        "col_qty_to": "Qty to",
        "col_valid_from": "Valid from",
        "col_valid_to": "Valid to",
        "col_note": "Note",
    },
}

FIELD_LABELS = {
    "lt": {
        "klientas": "Klientas",
        "projektas": "Projektas",
        "poz_kodas": "Detalės kodas",
        "poz_pavad": "Detalės pavadinimas",
        "metalas": "Metalo tipas",
        "metalo_storis": "Metalo storis (mm)",
        "plotas": "Plotas (m²)",
        "svoris": "Svoris (kg)",
        "plotas_svoris": "Plotas / svoris",
        "x_mm": "X (mm)",
        "y_mm": "Y (mm)",
        "z_mm": "Z (mm)",
        "matmenys_xyz": "Matmenys (XYZ)",
        "paruosimas": "Paruošimas",
        "padengimas": "Padengimas",
        "padengimo_standartas": "Padengimo standartas",
        "ktl_dangos_storis_display": "KTL storis (µm)",
        "miltai_dangos_storis_display": "Miltų storis (µm)",
        "spalva": "Spalva",
        "miltu_kodas": "Miltų kodas",
        "miltu_spalva": "Miltų spalva",
        "miltu_blizgumas": "Miltų blizgumas",
        "miltu_serija": "Miltų serija",
        "pakavimas": "Pakavimas",
        "pakavimo_tipas": "Pakavimo tipas",
        "atlikimo_terminas": "Atlikimo terminas",
        "testai_kokybe": "Testai / kokybė",
        "papildomos_paslaugos": "Papildomos paslaugos",
        "papildomos_paslaugos_aprasymas": "Papildomų paslaugų aprašymas",
        "paslauga_ktl": "KTL",
        "paslauga_miltai": "Miltai",
        "paslauga_paruosimas": "Paruošimas",
        "paslaugu_pastabos": "Pastabos Klientui",
    },
    "en": {
        "klientas": "Customer",
        "projektas": "Project",
        "poz_kodas": "Part code",
        "poz_pavad": "Part name",
        "metalas": "Metal type",
        "metalo_storis": "Metal thickness (mm)",
        "plotas": "Area (m²)",
        "svoris": "Weight (kg)",
        "plotas_svoris": "Area / weight",
        "x_mm": "X (mm)",
        "y_mm": "Y (mm)",
        "z_mm": "Z (mm)",
        "matmenys_xyz": "Dimensions (XYZ)",
        "paruosimas": "Preparation",
        "padengimas": "Coating",
        "padengimo_standartas": "Coating standard",
        "ktl_dangos_storis_display": "KTL thickness (µm)",
        "miltai_dangos_storis_display": "Powder thickness (µm)",
        "spalva": "Color",
        "miltu_kodas": "Powder code",
        "miltu_spalva": "Powder color",
        "miltu_blizgumas": "Powder gloss",
        "miltu_serija": "Powder series",
        "pakavimas": "Packaging",
        "pakavimo_tipas": "Packaging type",
        "atlikimo_terminas": "Lead time",
        "testai_kokybe": "Tests / quality",
        "papildomos_paslaugos": "Additional services",
        "papildomos_paslaugos_aprasymas": "Additional services description",
        "paslauga_ktl": "KTL",
        "paslauga_miltai": "Powder",
        "paslauga_paruosimas": "Preparation",
        "paslaugu_pastabos": "Customer notes",
    },
}

VALUE_TRANSLATIONS_EN = {
    "Yra": "Yes",
    "Nėra": "No",
}


def _translate_value_for_lang(value: str, lang: str) -> str:
    if lang != "en":
        return value
    v = (value or "").strip()
    if not v:
        return value
    return VALUE_TRANSLATIONS_EN.get(v, v)


# Tik rodomi pasiūlyme laukai (tvarka pagal sąrašą)
OFFER_FIELD_ORDER = [
    "klientas",
    "projektas",
    "poz_kodas",
    "poz_pavad",
    "metalas",
    "metalo_storis",
    "plotas",
    "svoris",
    "x_mm",
    "y_mm",
    "z_mm",
    "matmenys_xyz",
    "paruosimas",
    "padengimas",
    "padengimo_standartas",
    "ktl_dangos_storis_display",
    "miltai_dangos_storis_display",
    "miltu_kodas",
    "miltu_spalva",
    "miltu_blizgumas",
    "miltu_serija",
    "pakavimas",
    "pakavimo_tipas",
    "atlikimo_terminas",
    "testai_kokybe",
    "papildomos_paslaugos",
    "papildomos_paslaugos_aprasymas",
    "paslauga_ktl",
    "paslauga_miltai",
    "paslaugu_pastabos",
]

# Visai nerodomi pasiūlyme
EXCLUDED_FIELD_NAMES = {
    "ktl_kabinimo_budas",
    "ktl_matmenu_sandauga",
    "miltu_tiekejas",
    "miltu_kaina",
}


# ============================================================================
# Business extraction
# ============================================================================

def _value_with_unit(value, unit: str) -> str:
    s = str(value or "").strip()
    if not s:
        return ""

    low = s.lower()
    if unit == "m²" and ("m²" in low or "m2" in low or "m^2" in low):
        return s
    if unit.lower() in low:
        return s

    return f"{s} {unit}"


def _metalo_storiai_display(pozicija: Pozicija) -> str:
    vals = []
    try:
        rel = getattr(pozicija, "metalo_storio_eilutes", None)
        if rel is not None and hasattr(rel, "all"):
            for row in rel.all().order_by("id"):
                v = getattr(row, "storis_mm", None)
                if v in (None, ""):
                    v = getattr(row, "metalo_storis", None)
                if v not in (None, ""):
                    vals.append(v)
    except Exception:
        pass

    if not vals:
        legacy = getattr(pozicija, "metalo_storis", None)
        if legacy not in (None, ""):
            vals = [legacy]

    out, seen = [], set()
    for v in vals:
        s = _fmt_mm(v)
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return ", ".join(out)


def _build_field_rows(pozicija: Pozicija, lang: str) -> list[tuple[str, str]]:
    labels_map = FIELD_LABELS.get(lang, FIELD_LABELS["lt"])
    rows: list[tuple[str, str]] = []

    for name in OFFER_FIELD_ORDER:
        if name in EXCLUDED_FIELD_NAMES:
            continue

        if name == "metalo_storis":
            ms = _metalo_storiai_display(pozicija)
            if ms:
                rows.append((labels_map.get("metalo_storis", "Metalo storis"), ms))
            continue

        # Pasiūlyme Plotas / Svoris rodome viena eilute.
        if name == "plotas":
            plotas = str(getattr(pozicija, "plotas", "") or "").strip()
            svoris = str(getattr(pozicija, "svoris", "") or "").strip()

            parts = []
            if plotas:
                parts.append(_value_with_unit(plotas, "m²"))
            if svoris:
                parts.append(_value_with_unit(svoris, "kg"))

            if parts:
                rows.append((labels_map.get("plotas_svoris", "Plotas / svoris"), " / ".join(parts)))
            continue

        if name == "svoris":
            continue

        # KTL storis rodomas, jei yra reikšmė.
        if name == "ktl_dangos_storis_display":
            value_str = str(getattr(pozicija, "ktl_dangos_storis_display", "") or "").strip()
            if value_str:
                rows.append((labels_map.get("ktl_dangos_storis_display", "KTL storis (µm)"), value_str))
            continue

        # Miltų storis rodomas tik kai Miltai pasirinkti ir yra reikšmė.
        if name == "miltai_dangos_storis_display":
            if not getattr(pozicija, "paslauga_miltai", False):
                continue

            value_str = str(getattr(pozicija, "miltai_dangos_storis_display", "") or "").strip()
            if value_str:
                rows.append((labels_map.get("miltai_dangos_storis_display", "Miltų storis (µm)"), value_str))
            continue

        # Pasiūlyme X/Y/Z rodome viena eilute per matmenys_xyz,
        # ne trimis atskiromis eilutėmis.
        if name in ("x_mm", "y_mm", "z_mm"):
            continue

        if name == "matmenys_xyz":
            value_str = str(getattr(pozicija, "matmenys_xyz", "") or "").strip()
            if value_str and value_str != "— x — x —":
                rows.append((labels_map.get("matmenys_xyz", "Matmenys (XYZ)"), value_str))
            continue

        try:
            field = pozicija._meta.get_field(name)
        except Exception:
            continue

        value = getattr(pozicija, name, None)
        if value in (None, ""):
            continue

        # Pasiūlyme nerodome „Miltai — Nėra“.
        # Jei Miltai pažymėti, eilutė lieka rodoma kaip „Miltai — Yra“.
        # KTL ir Paruošimo logikos čia neliečiame.
        if name == "paslauga_miltai" and value is False:
            continue

        label = labels_map.get(name) or (f"Field: {name}" if lang == "en" else str(field.verbose_name or name).capitalize())

        if isinstance(value, bool):
            if lang == "en":
                value_str = "Yes" if value else "No"
            else:
                value_str = "Yra" if value else "Nėra"
            rows.append((label, value_str))
            continue

        get_disp = getattr(pozicija, f"get_{name}_display", None)
        if callable(get_disp) and getattr(field, "choices", None):
            try:
                value_str = str(get_disp())
            except Exception:
                value_str = str(value)
        else:
            if name == "atlikimo_terminas":
                try:
                    n = int(value)
                    if lang == "en":
                        value_str = f"{n} working day" if n == 1 else f"{n} working days"
                    else:
                        # Lietuviška skaitvardžių galūnių logika:
                        # 1, 21, 31 -> darbo diena
                        # 2-9, 22-29 -> darbo dienos
                        # 10-20, 30, 40 -> darbo dienų
                        last_two = abs(n) % 100
                        last_one = abs(n) % 10

                        if last_two in range(11, 20) or last_one == 0:
                            suffix = "darbo dienų"
                        elif last_one == 1:
                            suffix = "darbo diena"
                        else:
                            suffix = "darbo dienos"

                        value_str = f"{n} {suffix}"
                except Exception:
                    value_str = str(value)
            else:
                value_str = str(value)

        value_str = _translate_value_for_lang(_humanize_case(value_str), lang)
        rows.append((label, value_str))

    return rows


# ============================================================================
# Drawings / image resolving
# ============================================================================

def _url_to_media_path(url_value: str | None) -> str | None:
    if not url_value:
        return None
    rel = urlparse(url_value).path or url_value
    media_url = (getattr(settings, "MEDIA_URL", "/media/") or "/media/").rstrip("/")
    if rel.startswith(media_url + "/"):
        rel = rel[len(media_url) + 1:]
    rel = rel.lstrip("/")
    path = os.path.join(settings.MEDIA_ROOT, rel)
    return path if os.path.exists(path) else None


def _resolve_preview_path(b) -> str | None:
    if not b:
        return None

    def _ok(p: str | None) -> str | None:
        return p if p and os.path.exists(p) else None

    # preview laukai
    for fname in ("preview", "thumbnail", "thumb", "miniatiura", "miniatura"):
        try:
            f = getattr(b, fname, None)
            if not f:
                continue
            p = _ok(getattr(f, "path", None))
            if p:
                return p
            p = _url_to_media_path(getattr(f, "url", None))
            if p:
                return p
        except Exception:
            pass

    # helperiai (jei projekte yra)
    for helper in ("preview_abspath", "best_image_path_for_pdf", "get_preview_abspath"):
        try:
            fn = getattr(b, helper, None)
            if callable(fn):
                p = _ok(fn())
                if p:
                    return p
        except Exception:
            pass

    # URL property (pvz. models.PozicijosBrezinys.thumb_url)
    for helper_attr in ("thumb_url", "preview_url", "thumbnail_url"):
        try:
            url_value = getattr(b, helper_attr, None)
            if callable(url_value):
                url_value = url_value()
            p = _url_to_media_path(url_value)
            if p:
                return p
        except Exception:
            pass

    # fallback į originalą tik image failams
    image_exts = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
    for attr in ("failas", "file", "image", "uploaded", "upload", "source", "original"):
        try:
            f = getattr(b, attr, None)
            p = _ok(getattr(f, "path", None))
            if p and os.path.splitext(p)[1].lower() in image_exts:
                return p
            p2 = _url_to_media_path(getattr(f, "url", None))
            if p2 and os.path.splitext(p2)[1].lower() in image_exts:
                return p2
        except Exception:
            pass

    return None


def _prepare_image_for_pdf(img_path: str | None) -> tuple[str | None, str | None]:
    """
    Return a ReportLab-safe image path.

    Returns:
      (draw_path, temp_path_to_cleanup)
    """
    if not img_path or not os.path.exists(img_path):
        return None, None

    ext = os.path.splitext(img_path)[1].lower()

    # Dažniausiai ReportLab saugiai suvalgo šituos tiesiogiai.
    # (PNG su alpha irgi dažnai veikia, bet jei norėsi – galima visus PNG irgi konvertuoti.)
    safe_direct_exts = {".jpg", ".jpeg", ".png"}
    if ext in safe_direct_exts:
        return img_path, None

    # Viską kitą (WEBP/TIFF/BMP/...) konvertuojam į PNG per PIL
    try:
        with Image.open(img_path) as im:
            # Suaktyvinam pilną failo nuskaitymą, kad vėliau nebūtų lazy read problemų
            im.load()

            # Sutvarkom režimus į ReportLab draugišką formatą
            if im.mode in ("RGBA", "LA"):
                # Paliekam alpha (mask="auto" drawImage pusėje ją dažnai tvarko)
                converted = im.convert("RGBA")
            elif im.mode == "P":
                # Palettized – jei turi transparency info, verčiam į RGBA, kitaip į RGB
                if "transparency" in im.info:
                    converted = im.convert("RGBA")
                else:
                    converted = im.convert("RGB")
            elif im.mode in ("RGB", "L"):
                converted = im
            else:
                # CMYK, I;16, 1, ir kt.
                converted = im.convert("RGB")

            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
            tmp_path = tmp.name
            tmp.close()

            converted.save(tmp_path, format="PNG")
            return tmp_path, tmp_path

    except Exception:
        return None, None

def _drawing_kind(b) -> str:
    """Grąžina trumpą tipą placeholderiui: PDF / 3D / FILE."""
    try:
        f = getattr(b, "failas", None) or getattr(b, "file", None)
        p = getattr(f, "path", None) or ""
        u = getattr(f, "url", None) or ""
        candidate = p or u or str(b)
        ext = os.path.splitext(str(candidate))[1].lower()
    except Exception:
        ext = ""

    if ext == ".pdf":
        return "PDF"
    if ext in {".stp", ".step", ".igs", ".iges", ".ifc"}:
        return "3D"
    return "FILE"


# ============================================================================
# Fonts
# ============================================================================

def _register_fonts() -> tuple[str, str]:
    """
    Register Unicode-capable fonts for ReportLab so Lithuanian characters render correctly.

    Priority:
      1) settings.OFFER_FONT_REGULAR / settings.OFFER_FONT_BOLD (if provided)
      2) Repo-tracked static fonts: BASE_DIR/pozicijos/static/pozicijos/fonts  <-- MAIN
      3) Any *.ttf in BASE_DIR/media/fonts (legacy fallback)
      4) Common system fonts on Linux (DejaVu / Noto)
      5) Fallback to Helvetica (may show □ for LT letters)
    """
    def _pick_from_dir(dir_path: str) -> tuple[str | None, str | None]:
        if not dir_path or not os.path.isdir(dir_path):
            return None, None
        files = sorted(
            [
                os.path.join(dir_path, f)
                for f in os.listdir(dir_path)
                if f.lower().endswith(".ttf")
            ]
        )
        if not files:
            return None, None

        reg = (
            next((f for f in files if "noto" in os.path.basename(f).lower() and "bold" not in os.path.basename(f).lower()), None)
            or next((f for f in files if "regular" in os.path.basename(f).lower()), None)
            or next((f for f in files if "dejavu" in os.path.basename(f).lower() and "bold" not in os.path.basename(f).lower()), None)
            or files[0]
        )
        bold = (
            next((f for f in files if "noto" in os.path.basename(f).lower() and "bold" in os.path.basename(f).lower()), None)
            or next((f for f in files if "bold" in os.path.basename(f).lower()), None)
            or next((f for f in files if "dejavu" in os.path.basename(f).lower() and "bold" in os.path.basename(f).lower()), None)
            or reg
        )
        return reg, bold

    candidates_regular = [
        getattr(settings, "OFFER_FONT_REGULAR", None),
        getattr(settings, "PDF_FONT_REGULAR", None),
    ]
    candidates_bold = [
        getattr(settings, "OFFER_FONT_BOLD", None),
        getattr(settings, "PDF_FONT_BOLD", None),
    ]

    reg = next((str(p) for p in candidates_regular if p and os.path.exists(str(p))), None)
    bold = next((str(p) for p in candidates_bold if p and os.path.exists(str(p))), None)

    if not reg:
        r1, b1 = _pick_from_dir(os.path.join(settings.BASE_DIR, "pozicijos", "static", "pozicijos", "fonts"))
        reg = reg or r1
        bold = bold or b1

    if not reg:
        r2, b2 = _pick_from_dir(os.path.join(settings.BASE_DIR, "media", "fonts"))
        reg = reg or r2
        bold = bold or b2

    if not reg:
        more_reg = [
            os.path.join(settings.BASE_DIR, "fonts", "NotoSans-Regular.ttf"),
            os.path.join(settings.BASE_DIR, "static", "fonts", "NotoSans-Regular.ttf"),
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        ]
        more_bold = [
            os.path.join(settings.BASE_DIR, "fonts", "NotoSans-Bold.ttf"),
            os.path.join(settings.BASE_DIR, "static", "fonts", "NotoSans-Bold.ttf"),
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        ]
        reg = next((p for p in more_reg if p and os.path.exists(p)), None)
        bold = next((p for p in more_bold if p and os.path.exists(p)), None)

    if reg:
        try:
            pdfmetrics.registerFont(TTFont("OfferRegular", str(reg)))
            if bold and os.path.exists(str(bold)):
                pdfmetrics.registerFont(TTFont("OfferBold", str(bold)))
                return "OfferRegular", "OfferBold"
            return "OfferRegular", "OfferRegular"
        except Exception:
            pass

    return "Helvetica", "Helvetica-Bold"


def _can_generate_proposal(request) -> bool:
    u = getattr(request, "user", None)
    return bool(
        getattr(u, "is_authenticated", False)
        and u.has_perm("pozicijos.change_pozicija")
    )


def _require_generate_proposal(request) -> None:
    if not _can_generate_proposal(request):
        raise PermissionDenied("Pasiūlymo PDF generavimas leidžiamas tik darbuotojui arba administratoriui.")


# ============================================================================
# Views
# ============================================================================

def proposal_prepare(request, pk: int):
    _require_generate_proposal(request)

    pozicija = get_object_or_404(Pozicija, pk=pk)

    lang = _get_lang(request)
    show_prices = _as_bool(request.GET.get("show_prices"), default=True)
    show_drawings = _as_bool(request.GET.get("show_drawings"), default=True)
    notes = (request.GET.get("notes", "") or "").strip()

    available_kainos = list(
        pozicija.kainos_eilutes
        .filter(busena="aktuali")
        .order_by("kiekis_nuo", "kiekis_iki", "-prioritetas", "-created")
    )

    raw_selected_kaina_ids = request.GET.getlist("kaina_id")
    selected_kaina_ids = [
        int(x) for x in raw_selected_kaina_ids
        if str(x).isdigit()
    ]

    # Jei vartotojas dar nieko nepasirinko, paruošimo lange pažymim visas aktualias kainas.
    if show_prices and not raw_selected_kaina_ids:
        selected_kaina_ids = [k.id for k in available_kainos]

    breziniai = list(pozicija.breziniai.all().order_by("eiliskumas", "id"))

    selected_brezinys_id = None
    raw_brezinys_id = (request.GET.get("brezinys_id") or "").strip()
    if raw_brezinys_id.isdigit():
        candidate_id = int(raw_brezinys_id)
        if any(b.id == candidate_id for b in breziniai):
            selected_brezinys_id = candidate_id

    # Jei nepasirinkta ranka – siūlom dabartinį pilotinį variantą:
    # pirmas su preview, jei nėra preview – pirmas failas.
    if selected_brezinys_id is None and breziniai:
        with_preview = []
        without_preview = []
        for b in breziniai:
            if _resolve_preview_path(b):
                with_preview.append(b)
            else:
                without_preview.append(b)

        selected_brezinys_id = (with_preview + without_preview)[0].id

    return render(
        request,
        "pozicijos/proposal_prepare.html",
        {
            "pozicija": pozicija,
            "lang": lang,
            "show_prices": show_prices,
            "show_drawings": show_drawings,
            "notes": notes,
            "available_kainos": available_kainos,
            "selected_kaina_ids": selected_kaina_ids,
            "breziniai": breziniai,
            "selected_brezinys_id": selected_brezinys_id,
        },
    )

def proposal_pdf(request, pk: int):
    _require_generate_proposal(request)

    pozicija = get_object_or_404(Pozicija, pk=pk)
    lang = _get_lang(request)
    labels = LANG_LABELS.get(lang, LANG_LABELS["lt"])

    show_prices = _as_bool(request.GET.get("show_prices"), default=True)
    show_drawings = _as_bool(request.GET.get("show_drawings"), default=True)
    notes = (request.GET.get("notes", "") or "").strip()

    # KAINOS NELIEČIAMOS: rodomos visos aktualios (arba pasirinktos per kaina_id)
    kainos_qs = pozicija.kainos_eilutes.filter(busena="aktuali").order_by("kiekis_nuo", "kiekis_iki", "-prioritetas", "-created")
    selected_ids = [x for x in request.GET.getlist("kaina_id") if str(x).isdigit()]
    if selected_ids:
        kainos_qs = kainos_qs.filter(id__in=selected_ids)
    kainos = list(kainos_qs)

    field_rows = _build_field_rows(pozicija, lang)

    # Bendros pozicijos pastabos yra vidinės ir klientui PDF pasiūlyme nerodomos.
    # Klientui skirtos pastabos eina per lauką paslaugu_pastabos, kuris yra field_rows.
    combined_notes = ""

    brez = list(pozicija.breziniai.all().order_by("eiliskumas", "id"))

    # PRIORITETAS: pasiūlyme rodome pirmą brėžinį pagal detalės eiliškumą.
    # Vienas tiesos šaltinis: pirmas brėžinys detalės lange = rodomas pasiūlyme.
    pilot_brez_prepared = []
    if brez:
        first_brez = brez[0]
        pilot_brez_prepared = [(first_brez, _resolve_preview_path(first_brez))]

    font_regular, font_bold = _register_fonts()
    notes_style = ParagraphStyle(name="notes", fontName=font_regular, fontSize=9, leading=12)
    main_label_style = ParagraphStyle(
        name="main_label",
        fontName=font_bold,
        fontSize=10,
        leading=12,
        splitLongWords=1,
    )
    main_value_style = ParagraphStyle(
        name="main_value",
        fontName=font_regular,
        fontSize=9,
        leading=11,
        splitLongWords=1,
    )
    price_cell_style = ParagraphStyle(name="price_cell", fontName=font_regular, fontSize=8, leading=10)

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4

    margin_left = 18 * mm
    margin_right = 18 * mm
    bottom_margin = 16 * mm
    y = H - 20 * mm

    temp_files_to_cleanup: list[str] = []

    def new_page():
        nonlocal y
        c.showPage()
        y = H - 20 * mm

    def draw_section_title(title: str):
        nonlocal y
        if y < bottom_margin + 14 * mm:
            new_page()
        c.setFont(font_bold, 13)
        c.setFillColor(colors.HexColor("#111827"))
        c.drawString(margin_left, y, title)
        y -= 4
        c.setStrokeColor(colors.HexColor("#e5e7eb"))
        c.line(margin_left, y, W - margin_right, y)
        y -= 6

    def draw_table_split(table_obj: Table, section_title: str, gap_after: float = 10):
        nonlocal y
        avail_w = W - margin_left - margin_right

        while True:
            avail_h = y - bottom_margin
            if avail_h < 20 * mm:
                new_page()
                draw_section_title(section_title)
                avail_h = y - bottom_margin

            parts = table_obj.split(avail_w, avail_h)
            if not parts:
                new_page()
                draw_section_title(section_title)
                continue

            part = parts[0]
            pw, ph = part.wrap(avail_w, avail_h)
            part.drawOn(c, margin_left, y - ph)
            y -= ph

            if len(parts) == 1:
                y -= gap_after
                break

            table_obj = parts[1]
            new_page()
            draw_section_title(section_title)

    # ------------------------------------------------------------------------
    # Header + hero
    # ------------------------------------------------------------------------
    logo_candidates = [
        getattr(settings, "OFFER_LOGO_PATH", None),
        os.path.join(settings.MEDIA_ROOT, "logo.png") if getattr(settings, "MEDIA_ROOT", None) else None,
        os.path.join(settings.BASE_DIR, "media", "logo.png"),
        os.path.join(settings.BASE_DIR, "static", "img", "logo.png"),
        os.path.join(settings.BASE_DIR, "pozicijos", "static", "pozicijos", "img", "logo.png"),
    ]
    logo_path = next((p for p in logo_candidates if p and os.path.exists(str(p))), None)

    # Kairė viršuje: logo
    logo_w = 42 * mm
    logo_h = 14 * mm
    logo_x = margin_left
    logo_y = H - 28 * mm

    if logo_path:
        try:
            c.drawImage(
                logo_path,
                logo_x,
                logo_y,
                width=logo_w,
                height=logo_h,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            pass

    # Po logo: dokumento pavadinimas.
    # Nuleidžiam žemiau ir padidinam, kad neprapultų tarp logo ir identifikatorių.
    offer_title_y = H - 41 * mm
    c.setFont(font_bold, 18)
    c.setFillColor(colors.HexColor("#111827"))
    c.drawString(margin_left, offer_title_y, labels["offer_title"])

    # Po pavadinimu: greiti identifikatoriai.
    # Paliekam aiškesnį tarpą nuo „Komercinis pasiūlymas“.
    header_project = str(getattr(pozicija, "projektas", "") or "").strip()
    header_part_code = str(getattr(pozicija, "poz_kodas", "") or "").strip()

    header_left_y = offer_title_y - 10 * mm
    if header_project:
        c.setFont(font_bold, 10.5)
        c.setFillColor(colors.HexColor("#111827"))
        c.drawString(margin_left, header_left_y, f"Projektas: {header_project}")
        header_left_y -= 6 * mm

    if header_part_code:
        c.setFont(font_bold, 10.5)
        c.setFillColor(colors.HexColor("#111827"))
        c.drawString(margin_left, header_left_y, f"Detalės kodas: {header_part_code}")

    # Dešinė viršuje: pasiūlymo generavimo data
    c.setFont(font_regular, 9)
    c.setFillColor(colors.HexColor("#6b7280"))
    c.drawRightString(
        W - margin_right,
        H - 18 * mm,
        f'{labels["date_label"]}: {datetime.now().strftime("%Y-%m-%d")}',
    )

    # Centre viršuje: pilotinė / pirmoji brėžinio miniatiūra
    try:
        hero_source = pilot_brez_prepared
    except NameError:
        hero_source = brez_prepared[:1] if "brez_prepared" in locals() else []

    hero_prepared = hero_source[0] if show_drawings and hero_source else None

    # Hero zonos geometriją skaičiuojame visada, kai show_drawings=True.
    # Taip PDF kepurės išdėstymas nesikeičia net tada, kai brėžinio nėra:
    # dešinėje tiesiog lieka tuščia vieta.
    hero_x = None
    hero_y = None
    hero_box_w = None
    hero_box_h = None

    if show_drawings:
        title_block_right = margin_left + 72 * mm
        free_left = title_block_right + 6 * mm
        free_right = W - margin_right
        free_w = max(60 * mm, free_right - free_left)

        # Tokie patys matmenys kaip ir su brėžiniu.
        hero_box_w = free_w * 0.78
        hero_box_h = hero_box_w * (2.0 / 3.0)

        # Centruojame laisvoje dešinėje zonoje.
        hero_x = free_left + (free_w - hero_box_w) / 2

        # Data yra viršuje dešinėje; hero zoną laikome žemiau datos bloko.
        # Jei header_date_y nėra sukurtas, reiškia rodom tik vieną datos eilutę.
        date_block_bottom_y = locals().get("header_date_y", H - 22.2 * mm)
        hero_top_y = date_block_bottom_y - 2 * mm
        hero_y = hero_top_y - hero_box_h

    if hero_prepared and hero_x is not None and hero_y is not None and hero_box_w is not None and hero_box_h is not None:
        c.setStrokeColor(colors.HexColor("#e5e7eb"))
        c.setLineWidth(0.6)
        c.rect(hero_x, hero_y, hero_box_w, hero_box_h, stroke=1, fill=0)

        hero_drawn = False
        b0, hero_path = hero_prepared
        hero_kind = _drawing_kind(b0)

        if hero_path:
            draw_path, temp_path = _prepare_image_for_pdf(hero_path)
            if temp_path:
                temp_files_to_cleanup.append(temp_path)
            if draw_path:
                try:
                    c.drawImage(
                        ImageReader(draw_path),
                        hero_x + 2,
                        hero_y + 2,
                        width=hero_box_w - 4,
                        height=hero_box_h - 4,
                        preserveAspectRatio=True,
                        anchor="c",
                        mask="auto",
                    )
                    hero_drawn = True
                except Exception:
                    hero_drawn = False

        if not hero_drawn:
            c.setFont(font_bold, 12)
            c.setFillColor(colors.HexColor("#9ca3af"))
            c.drawCentredString(hero_x + hero_box_w / 2, hero_y + hero_box_h / 2, hero_kind)

    # SVARBU:
    # jei show_drawings=True, rezervuojame tą pačią vietą net kai brėžinio nėra.
    # Todėl „Pagrindinė informacija“ prasideda toje pačioje vietoje.
    if show_drawings and hero_y is not None:
        y = hero_y - 10 * mm
    else:
        y = H - 46 * mm

    # ------------------------------------------------------------------------
    # Main section
    # ------------------------------------------------------------------------
    draw_section_title(labels["section_main"])
    y -= 4 * mm

    rows_for_table = list(field_rows)
    if combined_notes:
        rows_for_table.append((labels["section_notes"], combined_notes))

    if rows_for_table:
        table_data = []
        for lbl, val in rows_for_table:
            # Paragraph leidžia ilgesniam tekstui, pvz. Pakavimas,
            # automatiškai lūžti į kitą eilutę ir neišplaukti už puslapio ribų.
            table_data.append([
                _make_paragraph(str(lbl), main_label_style),
                _make_paragraph(str(val or ""), main_value_style),
            ])

        table_width = W - margin_left - margin_right
        col1 = 78 * mm  # daugiau vietos pavadinimams
        col2 = table_width - col1

        t = Table(table_data, colWidths=[col1, col2], repeatRows=0)
        t.setStyle(
            TableStyle(
                [
                    ("FONT", (0, 0), (-1, -1), font_regular, 9),
                    ("FONT", (0, 0), (0, -1), font_bold, 9),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e5e7eb")),
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f9fafb")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        draw_table_split(t, labels["section_main"], gap_after=18)
    else:
        c.setFont(font_regular, 9)
        c.setFillColor(colors.HexColor("#6b7280"))
        c.drawString(margin_left, y, labels["no_data"])
        y -= 12

    # ------------------------------------------------------------------------
    # Prices (ALL active lines)
    # ------------------------------------------------------------------------
    if show_prices:
        draw_section_title(labels["section_prices"])
        y -= 4 * mm
        if kainos:
            rows = [[
                labels["col_price"],
                labels["col_unit"],
                labels["col_qty_from"],
                labels["col_qty_to"],
                labels["col_valid_from"],
                labels["col_valid_to"],
                labels["col_note"],
            ]]
            for k in kainos:
                price_note = (k.pastaba or "").strip()
                rows.append([
                    _fmt_price(k.kaina),
                    str(k.matas or ""),
                    "—" if k.kiekis_nuo is None else str(k.kiekis_nuo),
                    ("+" if k.kiekis_nuo is not None else "—") if k.kiekis_iki is None else str(k.kiekis_iki),
                    k.galioja_nuo.strftime("%Y-%m-%d") if k.galioja_nuo else "—",
                    k.galioja_iki.strftime("%Y-%m-%d") if k.galioja_iki else "—",
                    _make_paragraph(price_note, price_cell_style) if price_note else "",
                ])

            pt = Table(
                rows,
                colWidths=[28 * mm, 16 * mm, 18 * mm, 18 * mm, 24 * mm, 24 * mm, 46 * mm],
                repeatRows=1,
            )
            pt.setStyle(
                TableStyle(
                    [
                        ("FONT", (0, 0), (-1, -1), font_regular, 8),
                        ("FONT", (0, 0), (-1, 0), font_bold, 8),
                        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e5e7eb")),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f9fafb")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 4),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            draw_table_split(pt, labels["section_prices"], gap_after=10)
        else:
            c.setFont(font_regular, 9)
            c.setFillColor(colors.HexColor("#6b7280"))
            c.drawString(margin_left, y, labels["no_prices"])
            y -= 12

    # ------------------------------------------------------------------------
    # Drawings
    # ------------------------------------------------------------------------
    # Brėžinio miniatiūra rodoma tik centre viršuje kaip pilotinis vaizdas.
    # Atskiro apatinio miniatiūrų bloko PDF'e nebededame.

    # Cleanup temp images
    for p in temp_files_to_cleanup:
        try:
            os.unlink(p)
        except Exception:
            pass

    c.showPage()
    c.save()

    resp = HttpResponse(content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="offer_{pozicija.poz_kodas or pozicija.pk}.pdf"'
    resp.write(buf.getvalue())
    return resp
