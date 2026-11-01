"""Reset a person's second factor from the server (lost phone of the platform operator, for instance).

The person registers a new authenticator application at the next sign-in. The reset is written to the port's access
journal when the account belongs to a port, and the person is told by e-mail.
"""
from __future__ import annotations

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError

from apps.core.models import User


class Command(BaseCommand):
    help = "Reset the two-factor authentication of an account (the person enrols again at the next sign-in)."

    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument("--reason", required=True, help="why the reset is made (written to the access journal)")

    def handle(self, *args, email, reason, **options):
        user = User.objects.filter(email__iexact=email.strip()).first()
        if user is None:
            raise CommandError(f"No account with the e-mail address {email}.")
        user.mfa_enabled = False
        user.mfa_secret_encrypted = ""
        user.save(update_fields=["mfa_enabled", "mfa_secret_encrypted"])
        if user.port is not None:
            from apps.registry.services import journal

            journal.audit(port=user.port, user=user, action="mfa.reset", obj=user, label="FLUXAA (server command)",
                          detail=reason[:300])
        send_mail("[FLUXAA Port] Double authentification réinitialisée / Two-factor authentication reset",
                  f"La double authentification de votre compte ({user.email}) a été réinitialisée par l'exploitant : "
                  f"{reason}. Vous enregistrerez une nouvelle application à votre prochaine connexion.\n\n"
                  f"The two-factor authentication of your account ({user.email}) was reset by the platform operator: "
                  f"{reason}. You will register a new application at your next sign-in.",
                  settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=True)
        self.stdout.write(self.style.SUCCESS(f"Two-factor authentication reset for {user.email}."))
