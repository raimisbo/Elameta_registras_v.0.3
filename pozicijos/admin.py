from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import (
    Pozicija,
    KainosEilute,
    MaskavimoEilute,
    PozicijosBrezinys,
    MetaloStorisEilute,
)


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
