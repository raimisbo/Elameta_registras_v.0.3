# pozicijos/urls.py
from django.urls import path
from django.contrib.auth.decorators import login_required
from . import views
from . import proposal_views
from . import kainos_views

app_name = "pozicijos"


def auth(view):
    return login_required(view)

urlpatterns = [
    # sąrašas
    path("", auth(views.pozicijos_list), name="list"),
    path("tbody/", auth(views.pozicijos_tbody), name="tbody"),
    path("stats/", auth(views.pozicijos_stats), name="stats"),
    path("export/csv/", auth(views.pozicijos_export_csv), name="export_csv"),

    # kurti / redaguoti
    path("nauja/", auth(views.pozicija_create), name="create"),
    path("<int:pk>/redaguoti/", auth(views.pozicija_edit), name="edit"),
    path("<int:pk>/kopijuoti/", auth(views.pozicija_copy), name="copy"),

    # detalė
    path("<int:pk>/", auth(views.pozicija_detail), name="detail"),

    # brėžiniai/importai
    path("<int:pk>/breziniai/upload/", auth(views.brezinys_upload), name="brezinys_upload"),
    path("<int:pk>/breziniai/<int:bid>/delete/", auth(views.brezinys_delete), name="brezinys_delete"),
    path("<int:pk>/breziniai/reorder/", auth(views.brezinys_reorder), name="brezinys_reorder"),
    path("_import_csv/", auth(views.pozicijos_import_csv), name="import_csv"),

    # pasiūlymai
    path("<int:pk>/proposal/", auth(proposal_views.proposal_prepare), name="proposal_prepare"),
    # alias senesniems šablonams (jei kažkur dar naudoji pasiulymas_prepare)
    path("<int:pk>/pasiulymas/", auth(proposal_views.proposal_prepare), name="pasiulymas_prepare"),
    path("<int:pk>/pdf/", auth(proposal_views.proposal_pdf), name="pdf"),

    # KAINOS
    path("<int:pk>/kainos/", auth(kainos_views.kainos_list), name="kainos_list"),
    path("<int:pk>/kainos/nauja/", auth(kainos_views.kaina_create), name="kaina_create"),
    path("kainos/<int:id>/redaguoti/", auth(kainos_views.kaina_update), name="kaina_update"),
    path("kainos/<int:id>/aktuali/", auth(kainos_views.kaina_set_aktuali), name="kaina_set_aktuali"),
    path("kainos/<int:id>/salinti/", auth(kainos_views.kaina_delete), name="kaina_delete"),
    path("kainos/<int:id>/history/", auth(kainos_views.kaina_history), name="kaina_history"),

    # 3D
    path("<int:pk>/breziniai/<int:bid>/3d/", auth(views.brezinys_3d), name="brezinys_3d"),
]
