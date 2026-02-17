# detaliu_registras/views_history.py
"""
Istorijos (AJAX) dalinis vaizdas, nenaudojant papildomų bibliotekų.
Saugiai pridedamas greta tavo esamų view'ų, kad nereikėtų perrašinėti views.py.
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, render
from django.views import View

# Importuojame modelius, kuriems rodysime istoriją.
# Jei kurio nors neturi projekte – tiesiog išmesk iš žemėlapio.
from .models import Uzklausa, Detale, Kaina, Projektas, Klientas


# Saugus modelių žemėlapis: URL'e priimsime modelio PAVADINIMĄ (string) tik iš šio sąrašo
MODEL_MAP = {
    "Uzklausa": Uzklausa,
    "Detale": Detale,
    "Kaina": Kaina,
    "Projektas": Projektas,
    "Klientas": Klientas,
}


class HistoryPartialView(LoginRequiredMixin, View):
    """
    Grąžina dalinį istorijos HTML (partial), skirtą įkelti per AJAX.
    Jei naršyklė be JS – tas pats šablonas gali būti parodytas ir kaip pilnas puslapis.
    """

    template_name = "detaliu_registras/components/history_partial.html"

    def get(self, request, pk, model, obj_pk):
        """
        :param pk: Pagrindinės Uzklausos ID (naudingas teisėms / breadcrumb'ams)
        :param model: Modelio pavadinimas (raktas iš MODEL_MAP)
        :param obj_pk: Konkretaus objekto PK (pvz., Detale.id, Kaina.id, ...)
        """
        Model = MODEL_MAP.get(model)
        if not Model:
            return render(
                request,
                self.template_name,
                {"history_diffs": [], "error": "Nerastas modelis."},
            )

        obj = get_object_or_404(Model, pk=obj_pk)

        # django-simple-history suteikia .history manager'į
        hist = getattr(obj, "history", None)
        if hist is None:
            return render(
                request,
                self.template_name,
                {"history_diffs": [], "error": "Istorija neaktyvuota šiame modelyje."},
            )

        # Limitas – kad partial'as būtų lengvas
        try:
            limit = int(request.GET.get("limit", 20))
        except Exception:
            limit = 20

        # Naudojame select_related, kad history_user nuskaitytume efektyviai
        entries = list(hist.select_related("history_user").order_by("-history_date")[:limit])

        # Paruošiame dif'ų sąrašą (lyginame su ankstesniu įrašu)
        diffs = []
        for i, h in enumerate(entries):
            changes = []
            if i + 1 < len(entries):
                try:
                    delta = h.diff_against(entries[i + 1])
                    for c in delta.changes:
                        changes.append({
                            "field": c.field,
                            "old": getattr(c, "old", None),
                            "new": getattr(c, "new", None),
                        })
                except Exception:
                    # Jei kažkas nelyginama (pvz., Field pašalintas), ramiai praleidžiam
                    pass
            diffs.append({"h": h, "changes": changes})

        ctx = {
            "history_diffs": diffs,
            "limit": limit,
            "model": model,
            "obj_pk": obj_pk,
            "uzklausa_pk": pk,
        }
        return render(request, self.template_name, ctx)
