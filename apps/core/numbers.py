"""Numbers typed by people: "32 046,310" (French keyboard) and "32046.310" both mean the same quantity."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

SPACES = {" ", " ", " ", " ", "'"}


def parse_decimal(value) -> Decimal:
    """Parse a quantity, accepting a decimal comma. Raise ValueError when ambiguous or not a number.

    A value holding both a comma and a point ("32,046.310") is refused rather than guessed: a registry
    figure must never depend on an interpretation.
    """
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    text = "".join(ch for ch in str(value).strip() if ch not in SPACES)
    if "," in text:
        if "." in text or text.count(",") > 1:
            raise ValueError(f"ambiguous number: {value!r}")
        text = text.replace(",", ".")
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"not a number: {value!r}") from exc
    if not number.is_finite():
        raise ValueError(f"not a number: {value!r}")
    return number
