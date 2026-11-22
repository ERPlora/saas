"""Commands of fiscal: the Hub sends a business's authorisation, the staff decide on it.

An upload is not an authority, it waits for a person (``submitted``); a newer upload replaces the one still
waiting (``returned`` with ``SUPERSEDED``) and never the one in force; only a waiting one is approved or
returned, and returning needs a reason the customer can act on; approving replaces the approval in force. The
staff may also withdraw an approval (with a reason), and each step is keyed by the business, whose snapshot
carries the outcome to the Hub (``hubs.queries.hub_sync.hub_snapshot``, block ``verifactu``).

Every step bumps the business's ``state_version`` in its transaction (``hubs.services.hub_push.bump_state``) and pushes
the snapshot once it commits (``push_after_commit``; ``reconcile_hub_states`` retries it while the Hub is
away), records its event (the trail: who, which business, which version) and tells the owner and the admins of
the business (``tell_the_business``), and once it commits mails them and, for one that waits for a review, the
review desk (``fiscal.emails``, FISCAL-F05). No document ever leaves in an event, a snapshot or a mail.

One module per entity or use case. Nothing is re-exported here: a name is imported from its own module
(``from fiscal.services.representation_grants import representation_submit``):

- ``staff_gate``: who of the staff may decide or change the stamp;
- ``business_notices``: the owner and the admins of the business hear of a change of its authorisation;
- ``representation_grants``: the Hub sends an authorisation and the staff decide on it;
- ``stamp_changes``: ERPlora's stamp as representative (FISCAL-F06).
"""

# Importing a module registers its operations; the ``as`` tells ruff the import is kept on purpose.
from fiscal.services import staff_gate as staff_gate
from fiscal.services import business_notices as business_notices
from fiscal.services import representation_grants as representation_grants
from fiscal.services import stamp_changes as stamp_changes
