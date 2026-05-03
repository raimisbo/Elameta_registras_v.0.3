# pozicijos/services/sync.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..models import KainosEilute, Pozicija


@dataclass(frozen=True)
class KainaEurSyncResult:
    old: Optional[object]
    new: Optional[object]
    changed: bool


def sync_pozicija_kaina_eur(pozicija: Pozicija, *, save: bool = True) -> KainaEurSyncResult:
    """
    Perskaičiuoja pozicijos aktualią kainą pagal KainosEilute.

    Dabartinėje modelio versijoje Pozicija.kaina_eur yra @property, ne DB laukas.
    Todėl čia nieko nerašome į Pozicija lentelę. Funkcija palikta kaip vienas
    oficialus perskaičiavimo / suderinamumo taškas po kainų įrašų keitimo.

    Taisyklė:
      - kaina_eur = pirmos aktualios KainosEilute eilutės kaina,
        kai KainosEilute.busena == 'aktuali', rikiuojant:
          prioritetas ASC, created DESC.
      - Jei aktualių eilučių nėra arba jų kaina NULL -> None.

    Argumentas save paliktas suderinamumui su senais kvietimais. Kadangi
    kaina_eur nėra DB laukas, save=True nebeatlieka Pozicija.save().
    """
    old = pozicija.kaina_eur

    akt = (
        KainosEilute.objects
        .filter(pozicija=pozicija, busena="aktuali")
        .order_by("prioritetas", "-created")
        .first()
    )
    new = getattr(akt, "kaina", None) if akt else None

    changed = (old != new)

    return KainaEurSyncResult(old=old, new=new, changed=changed)
