# pozicijos/urls.py
from django.urls import path
from . import views
from . import proposal_views
from . import kainos_views

app_name = "pozicijos"

urlpatterns = [
    path("api/filter-options/", views.api_pozicijos_filter_options, name="api_pozicijos_filter_options"),
    path("api/summary/", views.api_pozicijos_summary, name="api_pozicijos_summary"),
    path("api/preview/", views.api_pozicijos_preview, name="api_pozicijos_preview"),
    path("api/<int:pk>/", views.api_pozicija_detail, name="api_pozicija_detail"),
    path("api/ping/", views.api_ping, name="api_ping"),
    # sąrašas
    path("", views.pozicijos_list, name="list"),
    path("tbody/", views.pozicijos_tbody, name="tbody"),
    path("stats/", views.pozicijos_stats, name="stats"),

    # kurti / redaguoti
    path("nauja/", views.pozicija_create, name="create"),
    path("<int:pk>/redaguoti/", views.pozicija_edit, name="edit"),

    # detalė
    path("<int:pk>/", views.pozicija_detail, name="detail"),

    # brėžiniai/importai
    path("<int:pk>/breziniai/upload/", views.brezinys_upload, name="brezinys_upload"),
    path("<int:pk>/breziniai/<int:bid>/delete/", views.brezinys_delete, name="brezinys_delete"),
    path("_import_csv/", views.pozicijos_import_csv, name="import_csv"),

    # pasiūlymai
    path("<int:pk>/proposal/", proposal_views.proposal_prepare, name="proposal_prepare"),
    # alias senesniems šablonams (jei kažkur dar naudoji pasiulymas_prepare)
    path("<int:pk>/pasiulymas/", proposal_views.proposal_prepare, name="pasiulymas_prepare"),
    path("<int:pk>/pdf/", proposal_views.proposal_pdf, name="pdf"),

    # KAINOS
    path("<int:pk>/kainos/", kainos_views.kainos_list, name="kainos_list"),
    path("<int:pk>/kainos/nauja/", kainos_views.kaina_create, name="kaina_create"),
    path("kainos/<int:id>/redaguoti/", kainos_views.kaina_update, name="kaina_update"),
    path("kainos/<int:id>/aktuali/", kainos_views.kaina_set_aktuali, name="kaina_set_aktuali"),
    path("kainos/<int:id>/salinti/", kainos_views.kaina_delete, name="kaina_delete"),
    path("kainos/<int:id>/history/", kainos_views.kaina_history, name="kaina_history"),

    # 3D
    path("<int:pk>/breziniai/<int:bid>/3d/", views.brezinys_3d, name="brezinys_3d"),
]
