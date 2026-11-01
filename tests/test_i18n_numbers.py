"""Bilingual rendering and figures typed by people (decimal comma, port time)."""
from __future__ import annotations

import re
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.core.numbers import parse_decimal
from apps.registry.models import Measurement
from apps.registry.services import calls as call_svc
from apps.registry.services import measurements as meas
from apps.registry.services import requests as req_svc

from .conftest import act, force_done, make_call, master


def test_parse_decimal_accepts_a_comma_and_refuses_ambiguity():
    assert parse_decimal("32 046,310") == Decimal("32046.310")
    assert parse_decimal("32 046,310") == Decimal("32046.310")
    assert parse_decimal("32046.310") == Decimal("32046.310")
    assert parse_decimal(11.4) == Decimal("11.4")
    for bad in ("32,046.310", "1,2,3", "abc", "NaN", ""):
        with pytest.raises(ValueError):
            parse_decimal(bad)


@pytest.mark.django_db
def test_figures_are_compared_pairwise_and_ship_shore_carries_the_tolerance(world):
    call = make_call(world)
    force_done(call, ["M0:02", "M0:03", "M0:05"])
    call_svc.declare_call(call, act(world, call, "AGE"))
    m = meas.create_measurement(call, act(world, call, "INS"), Measurement.Kind.INITIAL)
    meas.add_value(m, master(world, call), "SHIP", "1000,000")
    assert not m.is_complete and m.differences() == []
    meas.add_value(m, act(world, call, "INS"), "SURVEYOR", "999.5")
    # EF-8.1: ship and shore values are both required; the surveyor's figure is compared but completes nothing
    assert not m.is_complete
    [row] = m.differences()
    assert (row["a"], row["b"], row["difference"]) == ("SHIP", "SURVEYOR", Decimal("0.500"))
    assert m.discrepancy() is None and not m.exceeds_tolerance()
    meas.add_value(m, act(world, call, "TER"), "SHORE", "990")
    assert m.is_complete
    pairs = {(d["a"], d["b"]): d for d in m.differences()}
    assert set(pairs) == {("SHIP", "SHORE"), ("SHIP", "SURVEYOR"), ("SHORE", "SURVEYOR")}
    assert m.discrepancy()["b"] == "SHORE"  # the ship/shore difference carries the tolerance (EF-8.2)
    assert m.exceeds_tolerance() and pairs[("SHIP", "SHORE")]["exceeds"]


@pytest.mark.django_db
def test_request_datetime_typed_in_port_time_is_stored_in_utc(world):
    call = make_call(world)
    world.port.timezone = "Africa/Lagos"  # UTC+1, to make the conversion visible
    world.port.save()
    call.refresh_from_db()
    rtype = req_svc.get_type(call, "BERTH")
    clean = req_svc.validate_form(rtype, {"window_from": "2026-11-02T08:30", "arrival_draft": "11,4"})
    assert clean["window_from"] == "2026-11-02T07:30:00+00:00"
    assert clean["arrival_draft"] == pytest.approx(11.4)


@pytest.mark.django_db(databases=["default", "secure"])
def test_french_pages_keep_css_numbers_unlocalized(client, world):
    call = make_call(world, eta=timezone.now() - timedelta(hours=10))
    force_done(call, ["M0:02", "M0:03", "M0:05"])
    call_svc.declare_call(call, act(world, call, "AGE"))
    user = world.users["AGE"]
    user.language = "fr"
    user.save()
    client.force_login(user)
    html = client.get(f"/escales/{call.pk}/", HTTP_ACCEPT_LANGUAGE="fr").content.decode()
    assert "Aperçu" in html and "Jalons" in html  # tab labels are translated
    assert not re.search(r"(left|width):\s*\d+,\d+%", html), "decimal comma inside a CSS length"
    dashboard = client.get("/", HTTP_ACCEPT_LANGUAGE="fr").content.decode()
    assert not re.search(r"(left|width):\s*\d+,\d+%", dashboard)
    user.language = "en"
    user.save()
    english = client.get(f"/escales/{call.pk}/").content.decode()
    assert "Overview" in english and "Milestones" in english
