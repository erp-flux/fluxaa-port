"""Standard forms of a call, every kind of cargo — one structure, one family of forms per issuing party (docs/FORMULAIRES.md).

The public surface is the one of the former single module: ``FORMS``, ``available``, ``for_call``, ``grouped``,
``context``, ``render``, ``issue``; the families register their forms when the package is imported, and the
import order below is the display order within each family (the reference forms first).
"""
from .core import (  # noqa: F401
    FAMILIES,
    FORMS,
    F,
    Form,
    Pair,
    auto_issue,
    available,
    checklist,
    context,
    dt,
    fields,
    for_call,
    grouped,
    issue,
    offered,
    qr,
    render,
    table,
    text,
)

# isort: off
from . import standard  # noqa: E402, F401  — the fourteen reference forms of the ship/shore interface
from . import authority  # noqa: E402, F401  — decisions of the harbour master, port authority, customs; berth limits; security
from . import agency  # noqa: E402, F401
from . import ship  # noqa: E402, F401
from . import terminal  # noqa: E402, F401
from . import surveyor  # noqa: E402, F401
from . import services  # noqa: E402, F401
from . import provider  # noqa: E402, F401
from . import owner  # noqa: E402, F401
from . import cargo  # noqa: E402, F401  — v1.5: dry bulk, containers, general cargo, ro-ro; PAEC, vetting grid, handling plan
# isort: on

__all__ = ["FAMILIES", "FORMS", "F", "Form", "Pair", "auto_issue", "available", "checklist", "context", "dt", "fields", "for_call", "grouped",
           "issue", "offered", "qr", "render", "table", "text"]
