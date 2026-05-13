from django.contrib import admin
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils import timezone
from simple_history.admin import SimpleHistoryAdmin

from .models import (
    Pozicija,
    KainosEilute,
    MaskavimoEilute,
    PozicijosBrezinys,
    MetaloStorisEilute,
)


_HISTORY_EXCLUDED_FIELDS = {
    "id",
    "created",
    "updated",
}


def _admin_history_action_label(history_type: str) -> str:
    if history_type == "+":
        return "Sukurta"
    if history_type == "~":
        return "Pakeista"
    if history_type == "-":
        return "Ištrinta"
    return history_type or "—"


def _admin_field_label(model, field_name: str) -> str:
    try:
        field = model._meta.get_field(field_name)
        return str(field.verbose_name or field_name)
    except Exception:
        return field_name


def _admin_history_value(record, field_name: str) -> str:
    value = getattr(record, field_name, None)

    if value in (None, ""):
        return "—"

    get_display = getattr(record, f"get_{field_name}_display", None)
    if callable(get_display):
        try:
            display_value = get_display()
            if display_value not in (None, ""):
                return str(display_value)
        except Exception:
            pass

    if isinstance(value, bool):
        return "Yra" if value else "Nėra"

    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d %H:%M")

    return str(value)


def _admin_history_user(record) -> str:
    user = getattr(record, "history_user", None)
    if not user:
        return "—"
    try:
        return user.get_username()
    except Exception:
        return str(user)


def _admin_history_date(record) -> str:
    dt = getattr(record, "history_date", None)
    if not dt:
        return "—"
    try:
        dt = timezone.localtime(dt)
    except Exception:
        pass
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _admin_history_changes(record, previous_record, model) -> list[tuple[str, str, str]]:
    """
    Grąžina: [(field_label, old_value, new_value), ...]
    """
    if previous_record is None:
        return []

    changes: list[tuple[str, str, str]] = []

    for field in model._meta.fields:
        name = field.name
        if name in _HISTORY_EXCLUDED_FIELDS:
            continue

        old_raw = getattr(previous_record, name, None)
        new_raw = getattr(record, name, None)

        if old_raw == new_raw:
            continue

        label = str(field.verbose_name or name)
        old_value = _admin_history_value(previous_record, name)
        new_value = _admin_history_value(record, name)
        changes.append((label, old_value, new_value))

    return changes


# ---- Inlines (patogu matyti viską Pozicijoje) ----
class KainosEiluteInline(admin.TabularInline):
    model = KainosEilute
    extra = 0
    fields = (
        "busena",
        "kaina",
        "matas",
        "yra_fiksuota",
        "fiksuotas_kiekis",
        "kiekis_nuo",
        "kiekis_iki",
        "galioja_nuo",
        "galioja_iki",
        "prioritetas",
        "pastaba",
        "updated",
    )
    readonly_fields = ("updated",)
    ordering = ("-updated", "-id")


class MaskavimoEiluteInline(admin.TabularInline):
    model = MaskavimoEilute
    extra = 0
    fields = ("paslauga", "maskuote", "vietu_kiekis", "aprasymas", "updated")
    readonly_fields = ("updated",)
    ordering = ("id",)


class MetaloStorisEiluteInline(admin.TabularInline):
    model = MetaloStorisEilute
    extra = 0
    fields = ("storis_mm", "updated")
    readonly_fields = ("updated",)
    ordering = ("id",)


class PozicijosBrezinysInline(admin.TabularInline):
    model = PozicijosBrezinys
    extra = 0
    fields = ("pavadinimas", "failas", "uploaded_at")
    readonly_fields = ("uploaded_at",)
    ordering = ("-uploaded_at", "-id")


# ---- Admin registracijos ----
@admin.register(Pozicija)
class PozicijaAdmin(SimpleHistoryAdmin):
    readonly_fields = ("history_changes_preview",)

    list_display = (
        "id",
        "poz_kodas",
        "poz_pavad",
        "klientas",
        "projektas",
        "paslauga_ktl",
        "paslauga_miltai",
        "paslauga_paruosimas",
        "updated",
    )
    search_fields = ("poz_kodas", "poz_pavad", "klientas", "projektas")
    list_filter = (
        "paslauga_ktl",
        "paslauga_miltai",
        "paslauga_paruosimas",
        "pakavimo_tipas",
        "maskavimo_tipas",
        "papildomos_paslaugos",
        "created",
        "updated",
    )
    ordering = ("-updated", "-id")
    date_hierarchy = "updated"

    inlines = (
        KainosEiluteInline,
        MaskavimoEiluteInline,
        MetaloStorisEiluteInline,
        PozicijosBrezinysInline,
    )

    @admin.display(description="Pakeitimų istorija")
    def history_changes_preview(self, obj):
        if not obj or not obj.pk:
            return "Istorija bus rodoma išsaugojus detalę."

        records = list(
            obj.history.select_related("history_user")
            .order_by("-history_date", "-history_id")[:30]
        )

        if not records:
            return "Istorijos įrašų nėra."

        rows = []

        for record in records:
            previous_record = getattr(record, "prev_record", None)
            action = _admin_history_action_label(getattr(record, "history_type", ""))
            date_text = _admin_history_date(record)
            user_text = _admin_history_user(record)

            if getattr(record, "history_type", "") == "+":
                rows.append(
                    "<tr>"
                    f"<td>{escape(date_text)}</td>"
                    f"<td>{escape(user_text)}</td>"
                    f"<td>{escape(action)}</td>"
                    "<td colspan='3'>Sukurta pradinė detalės versija.</td>"
                    "</tr>"
                )
                continue

            changes = _admin_history_changes(record, previous_record, Pozicija)

            if not changes:
                rows.append(
                    "<tr>"
                    f"<td>{escape(date_text)}</td>"
                    f"<td>{escape(user_text)}</td>"
                    f"<td>{escape(action)}</td>"
                    "<td colspan='3'>Reikšmingų laukų pakeitimų nerasta.</td>"
                    "</tr>"
                )
                continue

            first = True
            for field_label, old_value, new_value in changes:
                rows.append(
                    "<tr>"
                    f"<td>{escape(date_text) if first else ''}</td>"
                    f"<td>{escape(user_text) if first else ''}</td>"
                    f"<td>{escape(action) if first else ''}</td>"
                    f"<td><strong>{escape(field_label)}</strong></td>"
                    f"<td>{escape(old_value)}</td>"
                    f"<td>{escape(new_value)}</td>"
                    "</tr>"
                )
                first = False

        html = (
            "<div style='max-width:100%; overflow:auto;'>"
            "<table style='border-collapse:collapse; width:100%; font-size:13px;'>"
            "<thead>"
            "<tr>"
            "<th style='text-align:left; border-bottom:1px solid #ddd; padding:6px;'>Data</th>"
            "<th style='text-align:left; border-bottom:1px solid #ddd; padding:6px;'>Kas</th>"
            "<th style='text-align:left; border-bottom:1px solid #ddd; padding:6px;'>Veiksmas</th>"
            "<th style='text-align:left; border-bottom:1px solid #ddd; padding:6px;'>Laukas</th>"
            "<th style='text-align:left; border-bottom:1px solid #ddd; padding:6px;'>Buvo</th>"
            "<th style='text-align:left; border-bottom:1px solid #ddd; padding:6px;'>Tapo</th>"
            "</tr>"
            "</thead>"
            "<tbody>"
            + "".join(rows) +
            "</tbody>"
            "</table>"
            "<div style='margin-top:6px; color:#6b7280; font-size:12px;'>"
            "Rodomi paskutiniai 30 istorijos įrašų. Techniniai laukai created/updated nerodomi."
            "</div>"
            "</div>"
        )

        return mark_safe(html)



@admin.register(KainosEilute)
class KainosEiluteAdmin(SimpleHistoryAdmin):
    list_display = (
        "id",
        "pozicija",
        "busena",
        "kaina",
        "matas",
        "yra_fiksuota",
        "fiksuotas_kiekis",
        "kiekis_nuo",
        "kiekis_iki",
        "galioja_nuo",
        "galioja_iki",
        "prioritetas",
        "updated",
    )
    search_fields = ("pozicija__poz_kodas", "pozicija__poz_pavad", "pozicija__klientas", "pozicija__projektas")
    list_filter = ("busena", "yra_fiksuota", "galioja_nuo", "galioja_iki", "updated")
    list_select_related = ("pozicija",)
    ordering = ("-updated", "-id")
    date_hierarchy = "updated"


@admin.register(MaskavimoEilute)
class MaskavimoEiluteAdmin(admin.ModelAdmin):
    list_display = ("id", "pozicija", "paslauga", "maskuote", "vietu_kiekis", "updated")
    search_fields = ("pozicija__poz_kodas", "pozicija__poz_pavad", "maskuote", "aprasymas")
    list_filter = ("paslauga", "updated")
    list_select_related = ("pozicija",)
    ordering = ("id",)


@admin.register(PozicijosBrezinys)
class PozicijosBrezinysAdmin(admin.ModelAdmin):
    list_display = ("id", "pozicija", "pavadinimas", "filename", "uploaded_at")
    search_fields = ("pozicija__poz_kodas", "pozicija__poz_pavad", "pavadinimas", "failas")
    list_select_related = ("pozicija",)
    ordering = ("-uploaded_at", "-id")

    @admin.display(description="Failas")
    def filename(self, obj: PozicijosBrezinys) -> str:
        return obj.filename


@admin.register(MetaloStorisEilute)
class MetaloStorisEiluteAdmin(admin.ModelAdmin):
    list_display = ("id", "pozicija", "storis_mm", "updated")
    search_fields = ("pozicija__poz_kodas", "pozicija__poz_pavad")
    list_select_related = ("pozicija",)
    ordering = ("id",)
