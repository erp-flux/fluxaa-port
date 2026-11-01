from django.core.management.base import BaseCommand, CommandError

from apps.core.models import Port
from apps.registry.services.journal import verify_chain


class Command(BaseCommand):
    help = "Recompute the hash chains (journal and access audit, plus the N4 access log) and report any break."

    def handle(self, *args, **options):
        from apps.secure.services import verify_chain as verify_secure

        broken = False
        for port in Port.objects.all():
            for chain in ("journal", "audit"):
                result = verify_chain(port, chain)
                status = "OK" if result["ok"] else f"BROKEN at seq {result['broken_at']} ({result['reason']})"
                broken |= not result["ok"]
                self.stdout.write(f"{port.code} {chain}: {result['count']} entries — {status}")
            try:
                secure = verify_secure(port.code)
                broken |= not secure["ok"]
                self.stdout.write(f"{port.code} n4-access: {secure['count']} entries — {'OK' if secure['ok'] else 'BROKEN at ' + str(secure['broken_at'])}")
            except Exception as exc:  # secure database unreachable from this process
                self.stdout.write(f"{port.code} n4-access: not checked ({exc})")
        if broken:
            raise CommandError("At least one chain is broken: the registry has been altered outside the application.")
