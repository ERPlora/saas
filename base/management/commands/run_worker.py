"""``manage.py run_worker``: the ``saas-worker`` task, long-running, one per deploy (saas#305; ERPlora/aws
``stacks/prod/apps.tf``), as the Hub's ``run_worker`` is its ``worker``'s.

Runs ``base.worker.run`` until SIGTERM (ECS stopping the task) or SIGINT (Ctrl-C). The handlers only ask the loop to
stop and wake its wait (``Listener.interrupt``), so the push in course ends cleanly and the process exits 0; a worker
that fails exits with its code (non-zero), which the infra's ``task_failed`` rule reports. The previous handlers come
back when it returns.
"""

import signal
import threading

from django.core.management.base import BaseCommand, CommandError

from base import worker

STOP_SIGNALS = (signal.SIGTERM, signal.SIGINT)


class Command(BaseCommand):
    help = (
        "Run the SaaS's worker until SIGTERM or SIGINT: the WhatsApp deliveries to the Hub as soon as they are due, and "
        "the reconciliations of every 15 minutes."
    )

    def handle(self, *args, **options):
        stop = threading.Event()
        listener = worker.make_listener()

        def request_stop(signum, frame):
            stop.set()
            listener.interrupt()

        previous = {sig: signal.signal(sig, request_stop) for sig in STOP_SIGNALS}
        try:
            self.stdout.write("worker: started")
            self.stdout.flush()
            code = worker.run(stop, listener=listener)
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
            listener.close()
        if code != 0:
            raise CommandError(f"run_worker: the worker stopped with exit code {code}.", returncode=code)
        self.stdout.write("worker: stopped")
