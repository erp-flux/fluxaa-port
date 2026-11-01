from django import template

from apps.ai import services

register = template.Library()


@register.filter
def extractable(doc, actor):
    """True when *actor* may ask the assistant to read *doc* (Q88, certificates, bill of lading)."""
    return services.can_extract(actor, doc)


@register.filter
def get_item(mapping, key):
    try:
        return mapping.get(key)
    except AttributeError:
        return None
