"""The reads of the AI gateway, each an operation (``@operation``, ``kind="query"``) in a read-only transaction.

One module per entity or use case. Nothing is re-exported here: a name is imported from its own module
(``from assistant.queries.gates import staff_with``).
"""

# Importing a module registers its operations; the ``as`` tells ruff the import is kept on purpose.
from assistant.queries import gates as gates
from assistant.queries import provider_keys as provider_keys
from assistant.queries import routing_policy as routing_policy
from assistant.queries import callers as callers
from assistant.queries import usage as usage
from assistant.queries import docs as docs
