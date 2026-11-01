from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.core.models import Port
from apps.registry.services.exports import FORMAT_VERSION


class Command(BaseCommand):
    help = "Reversibility export of a whole port (EF-15) to a zip file — format documented in docs/FORMAT_EXPORT.md."

    def add_arguments(self, parser):
        parser.add_argument("port")
        parser.add_argument("output")

    def handle(self, *args, **options):
        from apps.registry.services.exports import export_port

        port = Port.objects.filter(code=options["port"]).first()
        if port is None:
            raise CommandError("Unknown port.")
        data = export_port(port, None)  # traced in the access journal as a command-line export
        Path(options["output"]).write_bytes(data)
        self.stdout.write(self.style.SUCCESS(f"{FORMAT_VERSION}: {len(data)} bytes written to {options['output']}"))
