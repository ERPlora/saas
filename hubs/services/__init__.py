"""Write operations of hubs, and the push of what the SaaS knows to the Hub service.

One operation = one transaction (``@operation``), with its event in the outbox. Who may write is
decided by the account's ``HubMember`` role (``access_control.access``). Every change the Hub must learn is
written in the same transaction (``Hub.pending_hub_call``, ``Hub.state_version``) and pushed after the
COMMIT (``sync_hub``, which never runs inside a transaction); when the Hub is away it stays owed and
``manage.py reconcile_hub_states`` retries it.

``accounts.services.hub_jump.issue_code`` and ``redeem_code`` read an account's access from the answered members of each
business (``hubs.member.list_mine``), so a change of people is the jump's next answer. Taking access away queues a
``SessionRevocation`` (delivered after the COMMIT, retried by ``reconcile_hub_states``), and a change of the people of
a business is told to its owner and admins (``notify_people``).

One module per entity or use case. Nothing is re-exported here: a name is imported from its own module
(``from hubs.services.creation import business_create``).
"""

# Importing a module registers its operations.
from hubs.services import refusals
from hubs.services import hub_callbacks
from hubs.services import people_notices
from hubs.services import hub_push
from hubs.services import session_revocations
from hubs.services import exclusive_runs
from hubs.services import subscription_sync
from hubs.services import demo_businesses
from hubs.services import creation
from hubs.services import business_settings
from hubs.services import deletion
from hubs.services import opening
from hubs.services import member_management
from hubs.services import invitation_answers
from hubs.services import ownership
from hubs.services import billing_profiles
from hubs.services import account_changes
from hubs.services import reconciliation
from hubs.services import platform_actions
from hubs.services import custom_domain_checks
from hubs.services import custom_domain_requests
from hubs.services import usage_collection
from hubs.services import suspensions
from hubs.services import scheduled_moves as scheduled_moves
from hubs.services import platform_business
