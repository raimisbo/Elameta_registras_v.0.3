from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def lt_decimal(value, places=4):
    """
    Decimal atvaizdavimas su lietuvišku kableliu.
    Pvz. 1.25 -> 1,2500, kai places=4.
    """
    if value is None or value == "":
        return ""

    try:
        places = int(places)
    except (TypeError, ValueError):
        places = 4

    try:
        decimal_value = Decimal(str(value).replace(",", "."))
        quant = Decimal("1").scaleb(-places)
        return f"{decimal_value.quantize(quant):.{places}f}".replace(".", ",")
    except (InvalidOperation, TypeError, ValueError):
        return str(value)
