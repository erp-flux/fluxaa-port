import logging
import signal
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from apps.registry.services.scheduler import tick

log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run the periodic processing loop: tacit countersignatures, alerts, expiries, digests, webhooks."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=int, default=60)
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        running = {"on": True}
        signal.signal(signal.SIGTERM, lambda *_: running.update(on=False))
        while running["on"]:
            close_old_connections()
            summary = tick()
            log.info("scheduler tick: %s", summary)
            if options["once"]:
                self.stdout.write(str(summary))
                return
            for _ in range(options["interval"]):
                if not running["on"]:
                    break
                time.sleep(1)
