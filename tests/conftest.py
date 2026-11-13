"""Shared fixtures: a bootstrapped port (Freetown), one organisation and one user per role."""
from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone, translation

from apps.core.models import Organization, Port, User
from apps.registry.bootstrap import bootstrap_port
from apps.registry.models import PortDefaultParty, Vessel
from apps.registry.services import calls as call_svc
from apps.registry.services.context import Actor, actor_for_call, system_actor


@pytest.fixture
def port(db):
    bootstrap_port("SLFNA")
    return Port.objects.get(code="SLFNA")


@pytest.fixture(autouse=True)
def _language_of_the_test_world():
    """Every test starts in the language of the test world's port (Freetown: English). A message a service writes
    outside a request — a withdrawal note, a refusal — no longer depends on the language a previous test's request
    left active: a test passes alone as it passes in the suite."""
    translation.activate("en")
    yield
    translation.deactivate()


@pytest.fixture
def world(port):
    def org(name, roles):
        return Organization.objects.create(port=port, name=name, allowed_roles=roles, email=f"{name[:5].lower()}@org.test")

    orgs = SimpleNamespace(
        authority=org("Port Authority", ["CAP", "APO", "DIR"]),
        health=org("Customs Immigration Health", ["ADM"]),
        security=org("Security and Navy", ["SUR"]),
        marine=org("Marine Services", ["SVC"]),
        agency=org("Test Agency", ["AGE"]),
        terminal=org("Test Terminal", ["TER"]),
        surveyor=org("Test Surveyor", ["INS"]),
        owner=org("Test Owner", ["COM"]),
        waste=org("Test Waste", ["PRE"]),
        sts=org("Test STS Provider", ["PRE"]),
    )
    for o, role in [(orgs.authority, "CAP"), (orgs.authority, "APO"), (orgs.authority, "DIR"),
                    (orgs.health, "ADM"), (orgs.security, "SUR"), (orgs.marine, "SVC")]:
        PortDefaultParty.objects.create(port=port, organization=o, role=role)
    users = {}
    for role, o in [("CAP", orgs.authority), ("APO", orgs.authority), ("DIR", orgs.authority), ("ADM", orgs.health),
                    ("SUR", orgs.security), ("SVC", orgs.marine), ("AGE", orgs.agency), ("TER", orgs.terminal),
                    ("INS", orgs.surveyor), ("COM", orgs.owner), ("PRE", orgs.waste)]:
        users[role] = User.objects.create_user(
            email=f"{role.lower()}@test.local", password="pw-test-123456", full_name=f"User {role}",
            organization=o, roles=[role],
        )
    vessel = Vessel.objects.create(port=port, imo="9999993", name="MT TEST SPIRIT", flag="Liberia",
                                   vessel_type="Product tanker", dwt=45000)
    return SimpleNamespace(port=port, orgs=orgs, users=users, vessel=vessel)


def make_call(world, *, operations=("M1",), kind="JETTY", eta=None, modules=(), parties=None, green_lights=True, **extra):
    """A call of the test world. The green lights of the naval base, the terminal and the principal (v1.5) are
    given at once unless *green_lights* is False: the scenarios written before 1.5 keep their focus; the green
    lights have their own tests."""
    eta = eta or (timezone.now() + timedelta(days=8))
    parties = parties if parties is not None else [
        (world.orgs.terminal, "TER"), (world.orgs.surveyor, "INS"), (world.orgs.owner, "COM"), (world.orgs.waste, "PRE"),
    ]
    call = call_svc.create_call(
        world.users["AGE"], vessel=world.vessel, eta=eta, requested_berth_kind=kind, operations=list(operations),
        modules=list(modules), parties=parties, etb=eta + timedelta(hours=4), etd=eta + timedelta(days=2),
        product="Gasoil", quantity=30000, **extra,
    )
    if green_lights:
        force_done(call, ["M0:09b", "M0:09c", "M0:09d"])
    return call


def act(world, call, role, strong=True) -> Actor:
    return actor_for_call(call, user=world.users[role], strong_auth=strong)


def master(world, call) -> Actor:
    link, _token, _code = call_svc.issue_master_link(call, act(world, call, "AGE"), master_name="Capt. Test Master")
    return actor_for_call(call, master=link)


def sys(call) -> Actor:
    return system_actor(call.port)


def force_done(call, codes):
    """Test helper: mark template tasks done as the platform would after the corresponding acts. A decision task
    also gets the authorization its decision would have issued (in force for a week), since hold points look at
    the authorization, not at the task flag."""
    from apps.registry.models import TaskStatus
    from apps.registry.services.tasks import system_complete

    actor = system_actor(call.port)
    for code in codes:
        template_code, number = code.split(":")
        for task in call.tasks.filter(template_code=template_code, number=number, status=TaskStatus.PENDING):
            system_complete(task, actor, evidence="test", allow_joint=True)
            grant_authorization(call, task)


def grant_authorization(call, task, *, valid_from=None, valid_until=None):
    """Test helper: the approved request and authorization behind a decision task."""
    from apps.registry.models import Authorization, RequestStatus, RequestType, ServiceRequest

    if task.request_side != "decide" or not task.request_type_code:
        return None
    rtype = RequestType.objects.filter(port=call.port, code=task.request_type_code).first()
    if rtype is None or not rtype.decision_roles:
        return None
    decider = next((u for u in User.objects.filter(organization__port=call.port, is_active=True)
                    if set(u.roles or []) & set(rtype.decision_roles)), None)
    if decider is None:
        return None
    now = timezone.now()
    number = call.requests.count() + 1
    request = ServiceRequest.objects.create(
        call=call, type=rtype, reference=f"{call.reference}-R{number:02d}", status=RequestStatus.APPROVED,
        decision=RequestStatus.APPROVED, requester_role=rtype.requester_roles[0], requester_org=call.agency,
        decision_role=rtype.decision_roles[0], decision_org=decider.organization, decision_user=decider, decided_at=now,
    )
    return Authorization.objects.create(
        call=call, request=request, number=f"AUT-TEST-{request.pk:06d}", type_code=rtype.code,
        issuer_role=rtype.decision_roles[0], issuer_org=decider.organization, issuer_user=decider,
        issuer_label=decider.full_name, scope="test", valid_from=valid_from or now - timedelta(days=1),
        valid_until=valid_until or now + timedelta(days=7), verification_code=f"TEST{request.pk:06d}", seal="test",
    )


@pytest.fixture
def helpers():
    return SimpleNamespace(make_call=make_call, act=act, master=master, sys=sys, force_done=force_done)
