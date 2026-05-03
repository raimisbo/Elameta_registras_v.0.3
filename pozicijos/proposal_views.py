from __future__ import annotations

import io
import os
import tempfile
from datetime import datetime
from urllib.parse import urlencode, urlparse
from xml.sax.saxutils import escape as xml_escape

from PIL import Image
from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
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


def _humanize_case(value: str) -> str:
    v = (value or "").strip()
    if not v:
        return v
    return v[:1].upper() + v[1:]


def _make_paragraph(text: str, style: ParagraphStyle) -> Paragraph:
    safe = xml_escape(text or "").replace("\n", "<br/>")
    return Paragraph(safe, style)


# ============================================================================
# Labels / translations
# ============================================================================

LANG_LABELS = {
    "lt": {
        "offer_title": "PASIŪLYMAS",
        "date_label": "Data",
        "section_main": "Pagrindinė informacija",
        "section_prices": "Kainos (aktualios eilutės)",
        "section_drawings": "Brėžinių miniatiūros",
        "section_notes": "Pastabos",
        "no_data": "Nėra duomenų.",
        "no_prices": "Nėra aktyvių kainų eilučių šiai pozicijai.",
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
        "offer_title": "OFFER",
        "date_label": "Date",
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
        "poz_kodas": "Brėžinio kodas",
        "poz_pavad": "Detalės pavadinimas",
        "metalas": "Metalo tipas",
        "metalo_storis": "Metalo storis",
        "plotas": "Plotas (m²)",
        "svoris": "Svoris (kg)",
        "x_mm": "X (mm)",
        "y_mm": "Y (mm)",
        "z_mm": "Z (mm)",
        "matmenys_xyz": "Matmenys (XYZ)",
        "paruosimas": "Paruošimas",
        "padengimas": "Padengimas",
        "padengimo_standartas": "Padengimo standartas",
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
        "paslaugu_pastabos": "Paslaugų pastabos",
    },
    "en": {
        "klientas": "Customer",
        "projektas": "Project",
        "poz_kodas": "Drawing code",
        "poz_pavad": "Part name",
        "metalas": "Metal type",
        "metalo_storis": "Metal thickness",
        "plotas": "Area (m²)",
        "svoris": "Weight (kg)",
        "x_mm": "X (mm)",
        "y_mm": "Y (mm)",
        "z_mm": "Z (mm)",
        "matmenys_xyz": "Dimensions (XYZ)",
        "paruosimas": "Preparation",
        "padengimas": "Coating",
        "padengimo_standartas": "Coating standard",
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
        "paslaugu_pastabos": "Service notes",
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
    "spalva",
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
    "paslauga_paruosimas",
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

        try:
            field = pozicija._meta.get_field(name)
        except Exception:
            continue

        value = getattr(pozicija, name, None)
        if value in (None, ""):
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
                        if n % 10 == 1 and n % 100 != 11:
                            value_str = f"{n} darbo diena"
                        elif n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
                            value_str = f"{n} darbo dienos"
                        else:
                            value_str = f"{n} darbo dienų"
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


# ============================================================================
# Views
# ============================================================================

def proposal_prepare(request, pk: int):
    qs = request.GET.copy()
    if "lang" not in qs:
        qs["lang"] = "lt"
    if "show_prices" not in qs:
        qs["show_prices"] = "1"
    if "show_drawings" not in qs:
        qs["show_drawings"] = "1"

    url = f"{reverse('pozicijos:pdf', args=[pk])}?{urlencode(qs, doseq=True)}"
    return redirect(url)


def proposal_pdf(request, pk: int):
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

    poz_notes = (pozicija.pastabos or "").strip()
    combined_notes = "\n\n".join([x for x in [poz_notes, notes] if x])

    brez = list(pozicija.breziniai.all().order_by("id"))

    # PRIORITETAS: pasiūlyme rodome tik vieną pilotinį brėžinį.
    # Pirmiau imamas pirmas brėžinys, turintis preview; jei preview nėra – pirmas failas.
    brez_with_preview = []
    brez_without_preview = []
    for b in brez:
        pp = _resolve_preview_path(b)
        if pp:
            brez_with_preview.append((b, pp))
        else:
            brez_without_preview.append((b, None))
    pilot_brez_prepared = (brez_with_preview + brez_without_preview)[:1]

    font_regular, font_bold = _register_fonts()
    notes_style = ParagraphStyle(name="notes", fontName=font_regular, fontSize=9, leading=12)
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
        c.setFont(font_bold, 12)
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
    if logo_path:
        try:
            c.drawImage(logo_path, margin_left, H - 20 * mm, width=30 * mm, height=10 * mm, preserveAspectRatio=True, mask="auto")
        except Exception:
            pass

    c.setFont(font_bold, 16)
    c.setFillColor(colors.HexColor("#111827"))
    c.drawString(margin_left, H - 30 * mm, labels["offer_title"])

    c.setFont(font_regular, 9)
    c.setFillColor(colors.HexColor("#6b7280"))
    c.drawRightString(W - margin_right, H - 24 * mm, datetime.now().strftime("%Y-%m-%d"))

    code = pozicija.poz_kodas or str(pozicija.pk)
    c.setFont(font_regular, 10)
    c.setFillColor(colors.HexColor("#111827"))
    c.drawString(margin_left, H - 36 * mm, code)

    sub = " • ".join([x for x in [str(pozicija.klientas or "").strip(), str(pozicija.projektas or "").strip()] if x])
    if sub:
        c.setFont(font_regular, 9)
        c.setFillColor(colors.HexColor("#6b7280"))
        c.drawString(margin_left, H - 41 * mm, sub)

    # Hero dešinėje: pirmas brėžinys su preview; jei nėra – placeholder
    hero_box_w = 56 * mm
    hero_box_h = 36 * mm
    hero_x = W - margin_right - hero_box_w
    hero_y = H - 52 * mm

    c.setStrokeColor(colors.HexColor("#e5e7eb"))
    c.setLineWidth(0.6)
    c.rect(hero_x, hero_y, hero_box_w, hero_box_h, stroke=1, fill=0)

    hero_drawn = False
    hero_kind = "FILE"
    hero_prepared = pilot_brez_prepared[0] if show_drawings and pilot_brez_prepared else None

    if hero_prepared:
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
                        hero_x + 1,
                        hero_y + 1,
                        width=hero_box_w - 2,
                        height=hero_box_h - 2,
                        preserveAspectRatio=True,
                        anchor="c",
                        mask="auto",
                    )
                    hero_drawn = True
                except Exception:
                    hero_drawn = False

    if not hero_drawn:
        c.setFont(font_bold, 11)
        c.setFillColor(colors.HexColor("#9ca3af"))
        c.drawCentredString(hero_x + hero_box_w / 2, hero_y + hero_box_h / 2, hero_kind)

    y = H - 58 * mm

    # ------------------------------------------------------------------------
    # Main section
    # ------------------------------------------------------------------------
    draw_section_title(labels["section_main"])

    rows_for_table = list(field_rows)
    if combined_notes:
        rows_for_table.append((labels["section_notes"], combined_notes))

    if rows_for_table:
        table_data = []
        for lbl, val in rows_for_table:
            if isinstance(val, str) and "\n" in val:
                table_data.append([lbl, _make_paragraph(val, notes_style)])
            else:
                table_data.append([lbl, val])

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
        draw_table_split(t, labels["section_main"], gap_after=10)
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
                    "" if k.kaina is None else str(k.kaina),
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
    # Atskiro brėžinių miniatiūrų bloko PDF'e nebededame.
    # Pilotinė / pirmoji miniatiūra rodoma viršuje dešinėje esančiame hero bloke,
    # kad pasiūlymas neužsitęstų per kelis puslapius vien dėl brėžinių.

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