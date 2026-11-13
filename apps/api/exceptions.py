from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler

from apps.core.guards import ImmutableRecordError
from apps.registry.services.errors import RegistryError


def fluxaa_exception_handler(exc, context):
    from .authentication import SecondFactorRequired

    if isinstance(exc, SecondFactorRequired):
        return Response({"code": "strong_auth_required", "message": str(exc.detail), "details": {}}, status=403)
    if isinstance(exc, RegistryError):
        return Response({"code": exc.code, "message": exc.message, "details": exc.details}, status=exc.http_status)
    if isinstance(exc, ImmutableRecordError):
        return Response({"code": "immutable", "message": str(exc)}, status=409)
    if isinstance(exc, DjangoValidationError):
        # a record refused by its own validation (an organisation named with an invalid e-mail, an IMO number that
        # is not one…): the caller's mistake, said field by field — never a server error
        details = {field: [str(m) for m in messages] for field, messages in exc.message_dict.items()} if hasattr(exc, "error_dict") else {}
        return Response({"code": "validation_error", "message": " ".join(str(m) for m in exc.messages), "details": details}, status=400)
    return exception_handler(exc, context)
