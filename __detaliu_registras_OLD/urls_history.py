# detaliu_registras/urls_history.py
from django.urls import path
from .views_history import HistoryPartialView

app_name = "detaliu_registras_history"

urlpatterns = [
    path(
        "uzklausos/<int:pk>/history/<str:model>/<int:obj_pk>/",
        HistoryPartialView.as_view(),
        name="history_partial",
    ),
]
