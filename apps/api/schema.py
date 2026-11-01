"""OpenAPI description of the authentication schemes that drf-spectacular cannot infer."""
from drf_spectacular.extensions import OpenApiAuthenticationExtension


class MasterAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "apps.api.authentication.MasterAuthentication"
    name = "masterLink"

    def get_security_definition(self, auto_schema):
        return {
            "type": "apiKey", "in": "header", "name": "Authorization",
            "description": "`Master <token>` — the account-less access link handed to the master by the agency "
                           "(EF-13): limited to one call, expires after departure.",
        }


class BearerTokenScheme(OpenApiAuthenticationExtension):
    target_class = "apps.api.authentication.BearerTokenAuthentication"
    name = "bearerToken"

    def get_security_definition(self, auto_schema):
        return {"type": "http", "scheme": "bearer",
                "description": "Personal token created from the profile page (after two-factor authentication "
                               "for the roles that require it)."}


class MfaSessionScheme(OpenApiAuthenticationExtension):
    target_class = "apps.api.authentication.MfaSessionAuthentication"
    name = "cookieAuth"

    def get_security_definition(self, auto_schema):
        return {"type": "apiKey", "in": "cookie", "name": "sessionid",
                "description": "Browser session of the web application (field app), with the CSRF token. For CAP, APO "
                               "and SUR the session counts only after two-factor authentication."}
