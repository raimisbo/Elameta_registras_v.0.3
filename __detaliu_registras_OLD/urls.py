# detaliu_registras/urls.py

from django.urls import path, re_path
from django.views.generic import RedirectView

from .views import (
    UzklausaListView,
    UzklausaDetailView,
    UzklausaCreateView,
    UzklausaUpdateView,
    KainosRedagavimasView,
    ImportUzklausosCSVView,
)

app_name = "detaliu_registras"

urlpatterns = [
    # Patogūs alias'ai -> sąrašas
    path("", RedirectView.as_view(pattern_name="detaliu_registras:uzklausa_list", permanent=False)),
    path("uzklausos/", RedirectView.as_view(pattern_name="detaliu_registras:uzklausa_list", permanent=False)),

    # Sąrašas (tikrasis kelias, kurį naudoja šablonai)
    path("perziureti_uzklausas/", UzklausaListView.as_view(), name="uzklausa_list"),

    # Nauja užklausa
    path("ivesti_uzklausa/", UzklausaCreateView.as_view(), name="ivesti_uzklausa"),

    # Peržiūra
    path("perziureti_uzklausa/<int:pk>/", UzklausaDetailView.as_view(), name="perziureti_uzklausa"),

    # Redagavimas (pagrindiniai duomenys)
    path("redaguoti_uzklausa/<int:pk>/", UzklausaUpdateView.as_view(), name="redaguoti_uzklausa"),

    # Kaina (viena kaina per užklausą)
    path("perziureti_uzklausa/<int:pk>/kainos/", KainosRedagavimasView.as_view(), name="kainos_redagavimas"),
    path("uzklausa/<int:pk>/kaina/", KainosRedagavimasView.as_view(), name="redaguoti_kaina"),

    # CSV importas (pasirenkama)
    path("importuoti_uzklausas/", ImportUzklausosCSVView.as_view(), name="import_uzklausos"),

    # Legacy saugikliai
    re_path(
        r"^perziureti_uzklausa/(?P<pk>\d+)/kaina/?$",
        RedirectView.as_view(pattern_name="detaliu_registras:kainos_redagavimas", permanent=False),
    ),
    re_path(
        r"^perziureti_uzklausa/(?P<pk>\d+)/kainos/?$",
        RedirectView.as_view(pattern_name="detaliu_registras:kainos_redagavimas", permanent=False),
    ),
]
