from django.core.management.base import BaseCommand

from apps.registry import catalog
from apps.registry.bootstrap import bootstrap_port


class Command(BaseCommand):
    help = "Load the reference catalogue (templates M0–M9, MA2, MA3, milestones, requests, documents, causes) into the ports."

    def add_arguments(self, parser):
        parser.add_argument("--port", action="append", help="Port code (SLFNA, TGLFW). Default: all known ports.")
        parser.add_argument("--refresh", action="store_true", help="Realign labels of reference rows (never templates).")

    def handle(self, *args, **options):
        for code in options["port"] or list(catalog.PORTS):
            result = bootstrap_port(code, refresh=options["refresh"])
            self.stdout.write(self.style.SUCCESS(f"{code}: " + ", ".join(f"{k}={v}" for k, v in result.items() if k != "port")))
