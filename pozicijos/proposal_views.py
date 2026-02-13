from __future__ import annotations

import io
import os
from datetime import datetime
from decimal import Decimal
from urllib.parse import urlencode
from xml.sax.saxutils import escape as xml_escape

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


def _get_lang(request) -> str:
    lang = (request.GET.get("lang") or "lt").lower()
    return "en" if lang.startswith("en") else "lt"


def _as_bool(v: str | None, default: bool = False) -> bool:
    if v is None:
        return default
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


LANG_LABELS = {
    "lt": {
        "offer_title": "PASIŪLYMAS",
        "date_label": "Data",
        "section_main": "Pagrindinė informacija",
        "section_prices": "Kainos (aktualios eilutės)",
        "section_drawings": "Brėžinių miniatiūros",
        "no_data": "Nėra duomenų.",
        "no_prices": "Nėra aktyvių kainų eilučių šiai pozicijai.",
        "no_drawings": "Nėra brėžinių.",
        "col_price": "Kaina",
        "col_unit": "Matas",
        "col_qty_from": "Kiekis nuo",
        "col_qty_to": "Kiekis iki",
        "col_valid_from": "Galioja nuo",
        "col_valid_to": "Galioja iki",
    },
    "en": {
        "offer_title": "OFFER",
        "date_label": "Date",
        "section_main": "Main information",
        "section_prices": "Prices (active lines)",
        "section_drawings": "Drawing thumbnails",
        "no_data": "No data.",
        "no_prices": "No active price lines for this position.",
        "no_drawings": "No drawings.",
        "col_price": "Price",
        "col_unit": "Unit",
        "col_qty_from": "Qty from",
        "col_qty_to": "Qty to",
        "col_valid_from": "Valid from",
        "col_valid_to": "Valid to",
    },
}

FIELD_LABELS = {
    "lt": {
        "klientas": "Klientas",
        "projektas": "Projektas",
        "poz_kodas": "Brėžinio kodas",
        "poz_pavad": "Detalės pavadinimas",
        "metalas": "Metalo tipas",
        "plotas": "Plotas (m²)",
        "svoris": "Svoris (kg)",
        "paruosimas": "Paruošimas",
        "padengimas": "Padengimas",
        "padengimo_standartas": "Padengimo standartas",
        "spalva": "Spalva",
        "miltu_kodas": "Miltų kodas",
        "miltu_serija": "Miltų serija",
        "pakavimas": "Pakavimas",
        "atlikimo_terminas": "Atlikimo terminas",
        "atlikimo_terminas_darbo_dienos": "Atlikimo terminas (darbo dienos)",
        "kaina": "Kaina (EUR)",
        "kaina_eur": "Kaina (EUR)",
        "paslauga_ktl": "Papildoma paslauga: KTL",
        "paslauga_miltai": "Papildoma paslauga: Miltai",
        "paslauga_paruosimas": "Papildoma paslauga: Paruošimas",
        "ktl_kabinimo_budas": "Kabinimo būdas",
        "pastabos": "Pastabos",
    },
    "en": {
        "klientas": "Customer",
        "projektas": "Project",
        "poz_kodas": "Drawing code",
        "poz_pavad": "Part name",
        "metalas": "Metal type",
        "plotas": "Area (m²)",
        "svoris": "Weight (kg)",
        "paruosimas": "Preparation",
        "padengimas": "Coating",
        "padengimo_standartas": "Coating standard",
        "spalva": "Color",
        "miltu_kodas": "Powder code",
        "miltu_serija": "Powder series",
        "pakavimas": "Packaging",
        "atlikimo_terminas": "Lead time",
        "atlikimo_terminas_darbo_dienos": "Lead time (working days)",
        "kaina": "Price (EUR)",
        "kaina_eur": "Price (EUR)",
        "paslauga_ktl": "Extra service: KTL",
        "paslauga_miltai": "Extra service: Powder coating",
        "paslauga_paruosimas": "Extra service: Preparation",
        "ktl_kabinimo_budas": "Hanging method",
        "pastabos": "Notes",
    },
}


def proposal_prepare(request, pk: int):
    _ = get_object_or_404(Pozicija, pk=pk)

    lang = _get_lang(request)
    notes = (request.GET.get("notes", "") or "").strip()

    params: list[tuple[str, str]] = [("lang", lang)]

    if _as_bool(request.GET.get("show_prices"), default=True):
        params.append(("show_prices", "1"))
    if _as_bool(request.GET.get("show_drawings"), default=True):
        params.append(("show_drawings", "1"))

    if notes:
        params.append(("notes", notes))

    for kid in request.GET.getlist("kaina_id"):
        params.append(("kaina_id", kid))

    if _as_bool(request.GET.get("preview"), default=False):
        params.append(("preview", "1"))

    url = reverse("pozicijos:pdf", args=[pk])
    if params:
        url += "?" + urlencode(params, doseq=True)
    return redirect(url)


def _register_fonts() -> tuple[str, str]:
    fonts_dir = os.path.join(settings.MEDIA_ROOT, "fonts")

    candidates_regular = [
        os.path.join(fonts_dir, "NotoSans-Regular.ttf"),
        os.path.join(fonts_dir, "DejaVuSans.ttf"),
    ]
    candidates_bold = [
        os.path.join(fonts_dir, "NotoSans-Bold.ttf"),
    ]

    def register_font(alias: str, path: str) -> str | None:
        try:
            pdfmetrics.registerFont(TTFont(alias, path))
            return alias
        except Exception:
            return None

    regular = "Helvetica"
    bold = "Helvetica-Bold"

    reg_path = next((p for p in candidates_regular if os.path.exists(p)), None)
    bold_path = next((p for p in candidates_bold if os.path.exists(p)), None)

    if reg_path:
        regular = register_font("APP-Regular", reg_path) or regular
    if bold_path:
        bold = register_font("APP-Bold", bold_path) or bold

    if bold == "Helvetica-Bold" and regular != "Helvetica":
        bold = regular

    return regular, bold


def _fmt_decimal(d: Decimal) -> str:
    s = f"{d:f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def _price_range_from_kainos(kainos) -> str:
    prices = [k.kaina for k in kainos if getattr(k, "kaina", None) is not None]
    if not prices:
        return "—"
    mn = min(prices)
    mx = max(prices)
    return _fmt_decimal(mn) if mn == mx else f"{_fmt_decimal(mn)}–{_fmt_decimal(mx)}"


def _is_price_label(lbl: str) -> bool:
    ll = (lbl or "").lower()
    return ("kaina" in ll and ("eur" in ll or "€" in lbl)) or ("price" in ll and ("eur" in ll or "€" in lbl))


def _make_paragraph(text: str, style: ParagraphStyle) -> Paragraph:
    safe = xml_escape(text or "").replace("\n", "<br/>")
    return Paragraph(safe, style)


def _humanize_case(text: str) -> str:
    """
    Jei visas tekstas mažosiomis -> pakeliam pirmą raidę.
    Jei jau turi didžiąsias/formatavimą -> neliečiam.
    """
    if not text:
        return text
    s = str(text).strip()
    if not s:
        return s
    if s == s.lower():
        return s[:1].upper() + s[1:]
    return s


def _build_field_rows(pozicija: Pozicija, lang: str) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    skip = {"id", "created", "updated", "atlikimo_terminas_data", "pastabos"}

    labels_map = FIELD_LABELS.get(lang, {})

    for field in pozicija._meta.fields:
        if field.name in skip:
            continue

        value = getattr(pozicija, field.name, None)
        if value in (None, ""):
            continue

        label = labels_map.get(field.name)
        if not label:
            label = f"Field: {field.name}" if lang == "en" else str(field.verbose_name or field.name).capitalize()

        if isinstance(value, bool):
            rows.append((label, ("Yes" if value else "No") if lang == "en" else ("Yra" if value else "Nėra")))
            continue

        # CHOICE laukams imam display reikšmę (pvz. Girliandos)
        get_disp = getattr(pozicija, f"get_{field.name}_display", None)
        if callable(get_disp) and getattr(field, "choices", None):
            try:
                value_str = str(get_disp())
            except Exception:
                value_str = str(value)
        else:
            if field.name in {"atlikimo_terminas", "atlikimo_terminas_darbo_dienos"}:
                try:
                    n = int(value)
                    value_str = f"{n} working days" if lang == "en" else f"{n} darbo dienos"
                except Exception:
                    value_str = str(value)
            else:
                value_str = str(value)

        value_str = _humanize_case(value_str)
        rows.append((label, value_str))

    return rows


def _get_kainos_for_pdf(pozicija: Pozicija):
    qs = pozicija.kainos_eilutes.filter(busena="aktuali")
    return qs.order_by("matas", "kiekis_nuo", "kiekis_iki", "galioja_nuo", "galioja_iki", "-created")


def _resolve_preview_path(b) -> str | None:
    """
    Universalesnis preview paėmimas.
    """

    def _exists(p: str | None) -> str | None:
        if p and isinstance(p, str) and os.path.exists(p):
            return p
        return None

    def _from_filefield(obj, attr: str) -> str | None:
        try:
            f = getattr(obj, attr, None)
            if not f:
                return None

            # absoliutus path
            p = getattr(f, "path", None)
            ok = _exists(p)
            if ok:
                return ok

            # MEDIA relative name -> absoliutus
            name = getattr(f, "name", None)
            if name:
                p2 = os.path.join(settings.MEDIA_ROOT, str(name))
                ok = _exists(p2)
                if ok:
                    return ok
        except Exception:
            return None
        return None

    if b is None:
        return None

    # 1) standartinis preview field
    for attr in ("preview", "preview_image", "thumb", "thumbnail", "image_preview"):
        ok = _from_filefield(b, attr)
        if ok:
            return ok

    # 2) preview_abspath (property/method)
    try:
        pa = getattr(b, "preview_abspath", None)
        if callable(pa):
            pa = pa()
        ok = _exists(pa)
        if ok:
            return ok
    except Exception:
        pass

    # 3) kiti dažni failų laukai
    for attr in ("image", "file", "uploaded", "upload", "source", "original", "failas"):
        ok = _from_filefield(b, attr)
        if ok:
            return ok

    # 4) jei yra method/property grąžinanti preview relative path
    for attr in ("preview_relpath", "preview_path", "get_preview_path", "best_image_path_for_pdf"):
        try:
            v = getattr(b, attr, None)
            if callable(v):
                v = v()
            if isinstance(v, str) and v:
                # absoliutus arba relative
                ok = _exists(v)
                if ok:
                    return ok
                ok = _exists(os.path.join(settings.MEDIA_ROOT, v))
                if ok:
                    return ok
        except Exception:
            continue

    return None


def proposal_pdf(request, pk: int):
    pozicija = get_object_or_404(Pozicija, pk=pk)

    lang = _get_lang(request)
    labels = LANG_LABELS.get(lang, LANG_LABELS["lt"])

    kainos = list(_get_kainos_for_pdf(pozicija))
    field_rows = _build_field_rows(pozicija, lang)

    kainu_rezis = _price_range_from_kainos(kainos)
    if kainu_rezis != "—":
        new_rows = []
        replaced = False
        for lbl, val in field_rows:
            if (not replaced) and _is_price_label(lbl):
                new_rows.append((lbl, kainu_rezis))
                replaced = True
            else:
                new_rows.append((lbl, val))
        field_rows = new_rows

    notes_extra = (request.GET.get("notes", "") or "").strip()
    poz_pastabos = (pozicija.pastabos or "").strip()
    combined_notes = "\n\n".join([t for t in [poz_pastabos, notes_extra] if t]).strip()

    notes_label = FIELD_LABELS.get(lang, FIELD_LABELS["lt"]).get("pastabos", "Pastabos")

    insert_idx = None
    for i, (lbl, _val) in enumerate(field_rows):
        if _is_price_label(lbl):
            insert_idx = i + 1
            break
    if insert_idx is None:
        insert_idx = len(field_rows)

    brez = list(pozicija.breziniai.all())

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    font_regular, font_bold = _register_fonts()

    notes_style = ParagraphStyle(
        name="Notes",
        fontName=font_regular,
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#111827"),
    )

    margin_left = 18 * mm
    margin_right = 18 * mm
    bottom_margin = 20 * mm

    def new_page_y() -> float:
        c.showPage()
        return height - 30 * mm

    top_bar_h = 18 * mm
    c.setFillColor(colors.HexColor("#f3f4f6"))
    c.rect(0, height - top_bar_h, width, top_bar_h, stroke=0, fill=1)

    logo_path = getattr(settings, "OFFER_LOGO_PATH", None) or os.path.join(settings.MEDIA_ROOT, "logo.png")
    if logo_path and os.path.exists(logo_path):
        try:
            img = ImageReader(logo_path)
            c.drawImage(
                img,
                margin_left,
                height - top_bar_h + (top_bar_h - 11 * mm) / 2,
                width=28 * mm,
                height=11 * mm,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            pass

    company_name = getattr(settings, "OFFER_COMPANY_NAME", "") or "UAB Elameta"
    line1 = getattr(settings, "OFFER_COMPANY_LINE1", "") or ""
    line2 = getattr(settings, "OFFER_COMPANY_LINE2", "") or ""
    right_x = width - margin_right

    c.setFont(font_bold, 10)
    c.setFillColor(colors.HexColor("#111827"))
    c.drawRightString(right_x, height - 6 * mm, company_name)

    c.setFont(font_regular, 8)
    y_company = height - 10 * mm
    if line1:
        c.drawRightString(right_x, y_company, line1)
        y_company -= 3.5 * mm
    if line2:
        c.drawRightString(right_x, y_company, line2)

    header_top = height - top_bar_h - 6 * mm
    header_h = 46 * mm
    header_bottom = header_top - header_h

    preview_w = 62 * mm
    preview_h = header_h
    preview_x = width - margin_right - preview_w
    preview_y = header_bottom

    hero = brez[0] if brez else None
    hero_img_path = _resolve_preview_path(hero)

    c.setStrokeColor(colors.HexColor("#e5e7eb"))
    c.setFillColor(colors.HexColor("#f9fafb"))
    c.rect(preview_x, preview_y, preview_w, preview_h, stroke=1, fill=1)

    if hero_img_path:
        try:
            c.drawImage(
                ImageReader(hero_img_path),
                preview_x + 2,
                preview_y + 2,
                width=preview_w - 4,
                height=preview_h - 4,
                preserveAspectRatio=True,
                anchor="c",
                mask="auto",
            )
        except Exception:
            hero_img_path = None

    if not hero_img_path:
        ext = (getattr(hero, "ext", "") or "").lower() if hero is not None else ""
        mark = "3D" if ext in {"stp", "step"} else "N/A"
        c.setFont(font_bold, 14)
        c.setFillColor(colors.HexColor("#6b7280"))
        c.drawCentredString(preview_x + preview_w / 2, preview_y + preview_h / 2, mark)

    x_left = margin_left
    c.setFillColor(colors.HexColor("#111827"))
    c.setFont(font_bold, 16)
    c.drawString(x_left, header_top - 6 * mm, labels["offer_title"])

    poz_kodas = pozicija.poz_kodas or pozicija.pk
    c.setFont(font_regular, 9)
    c.setFillColor(colors.HexColor("#111827"))
    c.drawString(x_left, header_top - 12.5 * mm, f"Position: {poz_kodas}" if lang == "en" else f"Pozicija: {poz_kodas}")

    c.setFillColor(colors.HexColor("#6b7280"))
    c.drawString(x_left, header_top - 17 * mm, datetime.now().strftime(f"{labels['date_label']}: %Y-%m-%d"))

    sub_parts = []
    if pozicija.klientas:
        sub_parts.append(str(pozicija.klientas))
    if pozicija.projektas:
        sub_parts.append(str(pozicija.projektas))
    sub_line = " • ".join(sub_parts)
    if sub_line:
        c.setFillColor(colors.HexColor("#6b7280"))
        c.setFont(font_regular, 9)
        c.drawString(x_left, header_top - 22 * mm, sub_line)

    y = header_bottom - 8
    c.setStrokeColor(colors.HexColor("#e5e7eb"))
    c.setLineWidth(0.6)
    c.line(margin_left, y, width - margin_right, y)
    y -= 18

    def draw_section_title(title: str) -> None:
        nonlocal y
        if y < bottom_margin + 20 * mm:
            y = new_page_y()
        c.setFont(font_bold, 12)
        c.setFillColor(colors.HexColor("#111827"))
        c.drawString(margin_left, y, title)
        y -= 5
        c.setStrokeColor(colors.HexColor("#e5e7eb"))
        c.setLineWidth(0.6)
        c.line(margin_left, y, width - margin_right, y)
        y -= 8

    def draw_table_flow(tbl: Table, table_width: float, extra_gap: float = 14) -> None:
        nonlocal y
        parts = [tbl]
        while parts:
            t = parts.pop(0)
            avail_h = y - bottom_margin
            if avail_h <= 0:
                y = new_page_y()
                continue

            _tw, th = t.wrap(table_width, 0)
            if th <= avail_h:
                t.drawOn(c, margin_left, y - th)
                y = y - th - extra_gap
                continue

            split_parts = t.split(table_width, avail_h)
            if not split_parts:
                y = new_page_y()
                parts.insert(0, t)
                continue

            first = split_parts[0]
            rest = split_parts[1:]

            _fw, fh = first.wrap(table_width, 0)
            first.drawOn(c, margin_left, y - fh)
            y = y - fh - extra_gap

            if rest:
                y = new_page_y()
                parts = rest + parts

    draw_section_title(labels["section_main"])

    rows_for_table: list[tuple[str, object]] = [(lbl, val) for (lbl, val) in field_rows]
    if combined_notes:
        rows_for_table.insert(insert_idx, (notes_label, _make_paragraph(combined_notes, notes_style)))

    if rows_for_table:
        table_width = width - margin_left - margin_right
        label_col_width = 70 * mm
        value_col_width = table_width - label_col_width

        tbl = Table([[lbl, val] for (lbl, val) in rows_for_table], colWidths=[label_col_width, value_col_width])
        tbl.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), font_regular),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e5e7eb")),
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f9fafb")),
                    ("FONTNAME", (0, 0), (0, -1), font_bold),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        draw_table_flow(tbl, table_width)
    else:
        c.setFont(font_regular, 9)
        c.setFillColor(colors.HexColor("#6b7280"))
        c.drawString(margin_left, y, labels["no_data"])
        y -= 12

    draw_section_title(labels["section_prices"])

    if kainos:
        table_width = width - margin_left - margin_right
        col_widths = [40 * mm, 25 * mm, 22 * mm, 22 * mm, 28 * mm, 28 * mm]
        rows = [[labels["col_price"], labels["col_unit"], labels["col_qty_from"], labels["col_qty_to"], labels["col_valid_from"], labels["col_valid_to"]]]
        for k in kainos:
            rows.append(
                [
                    "" if k.kaina is None else str(k.kaina),
                    str(k.matas or ""),
                    "—" if k.kiekis_nuo is None else str(k.kiekis_nuo),
                    "—" if k.kiekis_iki is None else str(k.kiekis_iki),
                    k.galioja_nuo.strftime("%Y-%m-%d") if k.galioja_nuo else "—",
                    k.galioja_iki.strftime("%Y-%m-%d") if k.galioja_iki else "—",
                ]
            )

        tbl = Table(rows, colWidths=col_widths, repeatRows=1)
        tbl.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), font_regular),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("FONTNAME", (0, 0), (-1, 0), font_bold),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f9fafb")),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e5e7eb")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        draw_table_flow(tbl, table_width)
    else:
        c.setFont(font_regular, 9)
        c.setFillColor(colors.HexColor("#6b7280"))
        c.drawString(margin_left, y, labels["no_prices"])
        y -= 12

    if len(brez) == 0:
        draw_section_title(labels["section_drawings"])
        c.setFont(font_regular, 9)
        c.setFillColor(colors.HexColor("#6b7280"))
        c.drawString(margin_left, y, labels["no_drawings"])
        y -= 12
    elif len(brez) > 1:
        draw_section_title(labels["section_drawings"])
        thumbs = brez[1:3]

        available = width - margin_left - margin_right
        gap = 6 * mm
        thumb_w = (available - gap * 2) / 3
        thumb_h = thumb_w * 0.75

        needed_h = thumb_h + 8 * mm
        if y - needed_h < bottom_margin:
            y = new_page_y()

        top_y = y
        for i, b in enumerate(thumbs):
            x = margin_left + i * (thumb_w + gap)
            c.setStrokeColor(colors.HexColor("#e5e7eb"))
            c.setLineWidth(0.6)
            c.rect(x, top_y - thumb_h, thumb_w, thumb_h, stroke=1, fill=0)

            img_path = _resolve_preview_path(b)

            if img_path:
                try:
                    c.drawImage(
                        ImageReader(img_path),
                        x + 1,
                        top_y - thumb_h + 1,
                        width=thumb_w - 2,
                        height=thumb_h - 2,
                        preserveAspectRatio=True,
                        anchor="c",
                        mask="auto",
                    )
                except Exception:
                    img_path = None

            if not img_path:
                ext = (getattr(b, "ext", "") or "").lower()
                mark = "3D" if ext in {"stp", "step"} else "N/A"
                c.setFont(font_bold, 12)
                c.setFillColor(colors.HexColor("#6b7280"))
                c.drawCentredString(x + thumb_w / 2, top_y - thumb_h / 2, mark)

        y = top_y - needed_h - 6

    c.setFont(font_regular, 8)
    c.setFillColor(colors.HexColor("#6b7280"))
    c.drawRightString(width - margin_right, 15 * mm, datetime.now().strftime("%Y-%m-%d %H:%M"))

    c.save()
    pdf = buffer.getvalue()
    buffer.close()

    resp = HttpResponse(pdf, content_type="application/pdf")
    poz_kodas = pozicija.poz_kodas or pozicija.pk
    resp["Content-Disposition"] = (
        f'inline; filename="offer_{poz_kodas}.pdf"'
        if lang == "en"
        else f'inline; filename="pasiulymas_{poz_kodas}.pdf"'
    )
    return resp
