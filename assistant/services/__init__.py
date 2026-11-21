"""The writes of the AI gateway, each an operation (``@operation``, ``kind="command"``) in its own transaction, with
its event in the outbox.

The admin calls them as the member of the staff who clicks (``assistant.admin.staff.staff_context``): each one checks
the model permission of Django that backs it, so a member of the staff without it is refused here too, not only
on the page. The commands call them as the platform (``platform_actor.platform_context``).

One module per entity or use case. Nothing is re-exported here: a name is imported from its own module
(``from assistant.services.platform_actor import platform_context``).
"""

# Importing a module registers its operations; the ``as`` tells ruff the import is kept on purpose.
from assistant.services import platform_actor as platform_actor
from assistant.services import encryption as encryption
from assistant.services import model_choice as model_choice
from assistant.services import turn_usage as turn_usage
from assistant.services import answer_reports as answer_reports
from assistant.services import documentation as documentation
