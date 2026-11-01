"""The only door to the AI provider (Anthropic Claude API, structured outputs).

Nothing else in the code base talks to the provider. Every request goes through ``ask()``, which
returns JSON validated against a schema, and through ``services._run()``, which records the trace.
"""
from __future__ import annotations

import json

from django.conf import settings
from django.utils.translation import gettext as _


class AssistantUnavailable(Exception):
    """The assistance is switched off, not allowed here, or the provider did not answer usefully."""


def enabled_for(port) -> bool:
    """Platform switch (key + provider agreement) AND the port's own opt-in with its agreement reference."""
    return bool(
        getattr(settings, "FLUXAA_AI_ENABLED", False)
        and port is not None
        and port.ai_assistance_enabled
        and (port.ai_agreement_reference or "").strip()
    )


def get_client():  # replaced by a fake in the tests
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover — dependency listed in requirements.txt
        raise AssistantUnavailable(_("The AI library is not installed on this server.")) from exc
    return anthropic.Anthropic(
        api_key=settings.ANTHROPIC_API_KEY,
        timeout=getattr(settings, "FLUXAA_AI_TIMEOUT_SECONDS", 90),
        max_retries=2,
    )


def ask(*, system: str, content: list[dict], schema: dict, max_tokens: int = 4096) -> dict:
    """One request, one JSON answer matching *schema* (structured outputs)."""
    client = get_client()
    try:
        response = client.messages.create(
            model=settings.FLUXAA_AI_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": content}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
    except AssistantUnavailable:
        raise
    except Exception as exc:  # network, quota, provider error: the registry never depends on it
        raise AssistantUnavailable(_("The assistant could not be reached: %(e)s") % {"e": type(exc).__name__}) from exc
    if getattr(response, "stop_reason", "") in ("refusal", "max_tokens"):
        raise AssistantUnavailable(_("The assistant returned no usable answer (%(r)s).") % {"r": response.stop_reason})
    text = next((block.text for block in response.content if getattr(block, "type", "") == "text"), "")
    try:
        return json.loads(text)
    except (TypeError, ValueError) as exc:
        raise AssistantUnavailable(_("The assistant returned an unreadable answer.")) from exc
