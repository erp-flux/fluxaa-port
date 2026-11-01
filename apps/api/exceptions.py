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
    return exception_handler(exc, context)
