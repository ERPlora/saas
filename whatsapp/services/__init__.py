"""The commands of whatsapp (``@operation`` kind="command"): the only writes of the app, each in its transaction.

Only the platform runs them (``platform_actor.platform_context``): the Hub through its signed doors, Meta through its
webhook, the ``saas-worker`` and the commands, and the staff's admin actions. No account role holds
``whatsapp.manage``. A call to Meta or to the Hub never happens inside one of these: ``gateway`` calls Meta or the Hub
between two commands, so no lock waits for a third party.

One module per entity or use case. Nothing is re-exported here: a name is imported from its own module
(``from whatsapp.services.delivery_queue import wake_the_worker``). A module that logs does it as ``whatsapp.services``,
the name of the app's door, not its own:

- ``platform_actor``: the permission of every command and the platform's context;
- ``channel_snapshot``: the business's WhatsApp in the Hub's snapshot (door 4);
- ``meta_webhook``: what Meta's webhook reported, parked for the Hub;
- ``delivery_queue``: what waits for the Hub, its push to doors 1 and 2, the staff's «Push to the Hub now» and door 6;
- ``message_sends``: door 5;
- ``template_mirror``: doors 8 and 9, the business's templates at Meta and their mirror here;
- ``phone_numbers``: the business's number, its connection (doors 11 and 12) and the renewal of Meta's permission;
- ``retention``: the daily forgetting.

A refusal raises the envelope's error (``live.errors``): the transaction rolls back, the reservation with it. The
cap's is the exception: ``whatsapp.message.claim`` returns it (``refused``) so the snapshot it announces leaves after
the COMMIT (a rolled-back transaction drops its ``on_commit``), and door 5 answers the same 409.
"""

# Importing a module registers its operations; the ``as`` tells ruff the import is kept on purpose.
from whatsapp.services import platform_actor as platform_actor
from whatsapp.services import channel_snapshot as channel_snapshot
from whatsapp.services import delivery_queue as delivery_queue
from whatsapp.services import meta_webhook as meta_webhook
from whatsapp.services import message_sends as message_sends
from whatsapp.services import template_mirror as template_mirror
from whatsapp.services import phone_numbers as phone_numbers
from whatsapp.services import retention as retention
