# detaliu_registras/admin.py
from django.contrib import admin

from .models import (
    Klientas,
    Projektas,
    Detale,
    DetaleSpecifikacija,
    PavirsiuDangos,
    Uzklausa,
    Kaina,
    Kainodara,
    KainosPartijai,
)

# ---- Klientas
@admin.register(Klientas)
class KlientasAdmin(admin.ModelAdmin):
    list_display = ("vardas", "created", "updated")
    search_fields = ("vardas",)
    ordering = ("vardas",)


# ---- Projektas
@admin.register(Projektas)
class ProjektasAdmin(admin.ModelAdmin):
    list_display = ("pavadinimas", "klientas", "created", "updated")
    search_fields = ("pavadinimas", "klientas__vardas")
    list_filter = ("klientas",)
    autocomplete_fields = ("klientas",)
    ordering = ("pavadinimas",)


# ---- Detalė / jos papildomi 1-1 duomenys kaip Inline
class DetaleSpecifikacijaInline(admin.StackedInline):
    model = DetaleSpecifikacija
    can_delete = True
    extra = 0


class PavirsiuDangosInline(admin.StackedInline):
    model = PavirsiuDangos
    can_delete = True
    extra = 0


@admin.register(Detale)
class DetaleAdmin(admin.ModelAdmin):
    list_display = ("pavadinimas", "brezinio_nr", "created", "updated")
    search_fields = ("pavadinimas", "brezinio_nr")
    inlines = [DetaleSpecifikacijaInline, PavirsiuDangosInline]
    ordering = ("pavadinimas",)


# ---- Kaina: rodoma Užklausos inline ir atskirai
class KainaInline(admin.TabularInline):
    model = Kaina
    extra = 0
    fields = (
        "busena",
        "suma",
        "valiuta",
        "yra_fiksuota",
        "kiekis_nuo",
        "kiekis_iki",
        "fiksuotas_kiekis",
        "kainos_matas",
    )


@admin.register(Kaina)
class KainaAdmin(admin.ModelAdmin):
    list_display = (
        "uzklausa",
        "suma",
        "valiuta",
        "busena",
        "yra_fiksuota",
        "kiekis_nuo",
        "kiekis_iki",
        "fiksuotas_kiekis",
        "kainos_matas",
        "created",
    )
    list_filter = ("busena", "valiuta", "yra_fiksuota", "kainos_matas")
    search_fields = ("uzklausa__id", "uzklausa__detale__pavadinimas", "uzklausa__projektas__pavadinimas")
    autocomplete_fields = ("uzklausa",)
    ordering = ("-id",)


# ---- Užklausa su Kaina inline
@admin.register(Uzklausa)
class UzklausaAdmin(admin.ModelAdmin):
    list_display = ("id", "klientas", "projektas", "detale", "data", "created", "updated")
    search_fields = (
        "id",
        "klientas__vardas",
        "projektas__pavadinimas",
        "detale__pavadinimas",
        "detale__brezinio_nr",
    )
    list_filter = ("data",)
    autocomplete_fields = ("klientas", "projektas", "detale")
    inlines = [KainaInline]
    ordering = ("-id",)


# ---- Kainodaros „antraštė“ + eilutės
class KainosPartijaiInline(admin.TabularInline):
    model = KainosPartijai
    # JEI KainosPartijai turėtų daugiau nei vieną FK į Kainodara, privaloma fk_name.
    # Mūsų dabartinėje schemoje yra vienas FK: "kainodara".
    fk_name = "kainodara"
    extra = 0
    fields = ("kiekis_nuo", "kiekis_iki", "suma", "valiuta")


@admin.register(Kainodara)
class KainodaraAdmin(admin.ModelAdmin):
    list_display = ("id", "uzklausa", "pavadinimas", "created", "updated")
    search_fields = ("pavadinimas", "uzklausa__id", "uzklausa__detale__pavadinimas")
    autocomplete_fields = ("uzklausa",)
    inlines = [KainosPartijaiInline]
    ordering = ("-id",)


@admin.register(KainosPartijai)
class KainosPartijaiAdmin(admin.ModelAdmin):
    list_display = ("id", "kainodara", "kiekis_nuo", "kiekis_iki", "suma", "valiuta", "created", "updated")
    search_fields = ("kainodara__pavadinimas", "kainodara__uzklausa__id")
    autocomplete_fields = ("kainodara",)
    ordering = ("-id",)
