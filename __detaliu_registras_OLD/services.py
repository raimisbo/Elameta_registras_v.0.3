"""
Service layer for business logic
Separates complex operations from views and models
"""
from django.db import transaction
from django.core.exceptions import ValidationError
from django.db.models import Count
from .models import Klientas, Projektas, Detale, Uzklausa, Kaina, Danga
import logging

logger = logging.getLogger(__name__)


def _normalize_path(value):
    """
    Konvertuoja tinklo kelią (\\server\dir\file) į HTTP-like kelią (server/dir/file).
    Jei jau http(s) – palieka. Jei None/tuščia – grąžina None.
    """
    if not value:
        return None
    s = str(value)
    if s.startswith("http://") or s.startswith("https://"):
        return s
    return s.strip("\\").replace("\\", "/")


def _extract(data, keys):
    """Grąžina naują dict tik su nurodytais raktais (jei yra)."""
    if not data:
        return {}
    return {k: data.get(k) for k in keys if k in data}


class UzklausaService:
    """Service for handling complex Uzklausa operations"""

    @staticmethod
    @transaction.atomic
    def create_full_request(form_data, projektas_data=None, detale_data=None):
        """
        Sukuria pilną užklausą (Klientas/Projektas/Detale/Uzklausa).
        Atgalinis suderinamumas su senu parašu (ignoruoja papildomus argumentus, jei jų nėra).

        Tikėtini raktai form_data (senas kelias):
          - existing_klientas | new_klientas_vardas
          - existing_projektas | projekto_pavadinimas, uzklausos_data, pasiulymo_data
          - existing_detale | detale_fields (dict)
        Naujieji (pasirinktinai):
          - projektas_data (dict) – papildomi Projektas laukai
          - detale_data (dict) – papildomi Detale laukai
        """
        try:
            klientas = UzklausaService._get_or_create_klientas(form_data)
            projektas = UzklausaService._get_or_create_projektas(form_data, klientas, projektas_data)
            detale = UzklausaService._get_or_create_detale(form_data, projektas, detale_data)

            uzklausa = Uzklausa.objects.create(
                klientas=klientas,
                projektas=projektas,
                detale=detale,
            )
            logger.info("Sukurta užklausa id=%s klientui '%s'", uzklausa.id, getattr(klientas, "vardas", klientas))
            return uzklausa

        except ValidationError:
            raise
        except Exception as e:
            logger.exception("Klaida kuriant pilną užklausą: %s", e)
            raise ValidationError(f"Nepavyko sukurti užklausos: {e}")

    @staticmethod
    def _resolve_instance_or_pk(model_cls, value, field_name="id"):
        """Leidžia paduoti arba instancą, arba PK – grąžina instancą."""
        if value is None:
            return None
        if isinstance(value, model_cls):
            return value
        return model_cls.objects.get(**{field_name: value})

    @staticmethod
    def _get_or_create_klientas(form_data):
        """Naudoja esamą klientą (obj/pk) arba sukuria naują iš vardo."""
        existing_kl = form_data.get("existing_klientas")
        new_kl_vardas = form_data.get("new_klientas_vardas")

        if existing_kl:
            return UzklausaService._resolve_instance_or_pk(Klientas, existing_kl)
        if new_kl_vardas:
            return Klientas.objects.create(
                vardas=new_kl_vardas,
                telefonas=form_data.get("klientas_telefonas", ""),
                el_pastas=form_data.get("klientas_el_pastas", ""),
            )
        raise ValidationError("Klientas privalomas (pasirinkite esamą arba nurodykite naują vardą).")

    @staticmethod
    def _get_or_create_projektas(form_data, klientas, projektas_data=None):
        """
        Naudoja esamą projektą arba sukuria naują.
        Papildomi laukai (nauji): projekto_pradzia, projekto_pabaiga, kaina_galioja_iki,
        apmokejimo_salygos, transportavimo_salygos.
        """
        existing_pr = form_data.get("existing_projektas")
        if existing_pr:
            return UzklausaService._resolve_instance_or_pk(Projektas, existing_pr)

        pavadinimas = form_data.get("projekto_pavadinimas") or form_data.get("projekto_pavadinimas_default") or "Projektas"
        uzklausos_data = form_data.get("uzklausos_data")
        pasiulymo_data = form_data.get("pasiulymo_data")

        if uzklausos_data and pasiulymo_data:
            ValidationService.validate_project_dates(uzklausos_data, pasiulymo_data)

        extra = _extract(
            projektas_data,
            ["projekto_pradzia", "projekto_pabaiga", "kaina_galioja_iki", "apmokejimo_salygos", "transportavimo_salygos"]
        )

        return Projektas.objects.create(
            klientas=klientas,
            pavadinimas=pavadinimas,
            uzklausos_data=uzklausos_data,
            pasiulymo_data=pasiulymo_data,
            **extra
        )

    @staticmethod
    def _get_or_create_detale(form_data, projektas, detale_data=None):
        """
        Naudoja esamą detalę arba sukuria naują.
        Sujungia seną `detale_fields` + naują `detale_data`. Sutvarko M2M `danga` ir nuorodų normalizavimą.
        """
        existing_det = form_data.get("existing_detale")
        if existing_det:
            return UzklausaService._resolve_instance_or_pk(Detale, existing_det)

        payload = {}
        payload.update(form_data.get("detale_fields") or {})
        payload.update(detale_data or {})

        # Normalizuojam nuorodas
        if "nuoroda_brezinio" in payload:
            payload["nuoroda_brezinio"] = _normalize_path(payload.get("nuoroda_brezinio"))
        if "nuoroda_pasiulymo" in payload:
            payload["nuoroda_pasiulymo"] = _normalize_path(payload.get("nuoroda_pasiulymo"))

        # ManyToMany 'danga' atskirai
        danga_values = payload.pop("danga", None)

        # BENT projektas privalomas
        detale = Detale.objects.create(projektas=projektas, **payload)

        # Pririšam dangas (gali būti id sąrašas arba pavadinimų sąrašas)
        if danga_values:
            ids = []
            for v in danga_values:
                try:
                    # jei skaičius/id
                    ids.append(int(v))
                    continue
                except (TypeError, ValueError):
                    pass
                # bandome pagal pavadinimą
                try:
                    d = Danga.objects.get(pavadinimas=v)
                    ids.append(d.id)
                except Danga.DoesNotExist:
                    logger.warning("Danga '%s' nerasta – praleidžiama", v)
            if ids:
                detale.danga.set(ids)

        return detale

    @staticmethod
    @transaction.atomic
    def update_prices(detale, formset):
        """
        Atnaujina visas detalės kainas:
          - esamas „aktuali“ → „sena“
          - sukuria naujas ir pažymi kaip „aktuali“
        """
        try:
            detale.kainos.filter(busena="aktuali").update(busena="sena")

            for form in formset:
                cd = getattr(form, "cleaned_data", None)
                if not cd or cd.get("DELETE"):
                    continue

                # Jei ModelForm – tiesiog commit=False
                try:
                    kaina = form.save(commit=False)
                except Exception:
                    fields = {}
                    for key in ("suma", "kiekis_nuo", "kiekis_iki", "fiksuotas_kiekis", "kainos_matas", "tipas"):
                        if key in cd:
                            fields[key] = cd.get(key)
                    kaina = Kaina(**fields)

                kaina.detale = detale
                kaina.busena = "aktuali"
                # Jeigu modelyje nėra 'tipas' (labai sena schema) – ignore
                if hasattr(kaina, "tipas") and not getattr(kaina, "tipas", None):
                    # default – vieneto kaina
                    try:
                        kaina.tipas = "VIENETO"
                    except Exception:
                        pass
                kaina.save()

            logger.info("Kainos atnaujintos detalei id=%s", getattr(detale, "id", None))

        except ValidationError:
            raise
        except Exception as e:
            logger.exception("Klaida atnaujinant kainas: %s", e)
            raise ValidationError(f"Nepavyko atnaujinti kainų: {e}")

    @staticmethod
    def get_active_price(detale, quantity):
        """
        Grąžina „aktyvią“ kainą pagal kiekį.
        Jei nustatytas `fiksuotas_kiekis` – tikslus atitikmuo.
        Kitu atveju – tikrina intervalą [kiekis_nuo; kiekis_iki].
        """
        active_prices = detale.kainos.filter(busena="aktuali")
        for price in active_prices:
            fk = getattr(price, "fiksuotas_kiekis", None)
            if fk is not None:
                if quantity == fk:
                    return price
            else:
                nuo = getattr(price, "kiekis_nuo", 0) or 0
                iki = getattr(price, "kiekis_iki", None)
                if iki is None:
                    if quantity >= nuo:
                        return price
                else:
                    if nuo <= quantity <= iki:
                        return price
        return None


class ReportService:
    """Service for generating reports and analytics"""

    @staticmethod
    def get_client_statistics():
        """Skaičiuoja užklausas per Uzklausa ir projektus per Projektas."""
        uzk_counts = {
            row["klientas_id"]: row["c"]
            for row in Uzklausa.objects.values("klientas_id").annotate(c=Count("id"))
        }
        proj_counts = {
            row["klientas_id"]: row["c"]
            for row in Projektas.objects.values("klientas_id").annotate(c=Count("id"))
        }
        out = []
        for kl in Klientas.objects.all().only("id", "vardas"):
            out.append({
                "vardas": kl.vardas,
                "uzklausu_kiekis": uzk_counts.get(kl.id, 0),
                "projektu_kiekis": proj_counts.get(kl.id, 0),
            })
        return out

    @staticmethod
    def get_coating_usage_stats():
        """Statistika pagal dangas (jei ryšys yra)."""
        return list(
            Detale.objects.values("danga__pavadinimas")
            .annotate(usage_count=Count("id"))
            .order_by("-usage_count")
        )


class ValidationService:
    """Service for complex validation logic"""

    @staticmethod
    def validate_price_ranges(prices_data):
        """Validuoja, kad kainų intervalai nepersidengtų."""
        sorted_prices = sorted(prices_data, key=lambda x: x.get("kiekis_nuo", 0))
        for i in range(len(sorted_prices) - 1):
            current = sorted_prices[i]
            next_price = sorted_prices[i + 1]
            current_end = current.get("kiekis_iki")
            next_start = next_price.get("kiekis_nuo")
            if current_end and next_start and current_end >= next_start:
                raise ValidationError(
                    f"Kainų diapazonai persidengia: {current_end} >= {next_start}"
                )
        return True

    @staticmethod
    def validate_project_dates(uzklausos_data, pasiulymo_data):
        """Pasiūlymo data negali būti ankstesnė už užklausos datą."""
        if uzklausos_data and pasiulymo_data and uzklausos_data > pasiulymo_data:
            raise ValidationError("Pasiūlymo data negali būti ankstesnė už užklausos datą")
        return True
