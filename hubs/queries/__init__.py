"""Read operations of hubs, and the reads its commands and its push to the Hub share.

The public ones need no permission and no account: the taxonomy of the sign-up and the industry pages
and the plans on sale, which a visitor reads before signing up. Only active rows, in the
caller's language (``ctx.language``, which a live stream carries outside the request).

The rest are an account's (``hubs.view``, held by every signed-in account): its businesses, a
business's page and members, its invitations and a business's payer. Who may read what is decided
by the account's ``HubMember`` role (``access_control``): somebody without access to a business gets
404, never a hint that it exists; a role below the one needed gets 403.

An account's API key with ``hubs.read`` opens the reads declared ``expose_api=True`` (its businesses, a
business's page and members, the taxonomy and the plans) as that account (``accounts.api_auth``); no
command is exposed yet.

One module per entity or use case. Nothing is re-exported here: a name is imported from its own module
(``from hubs.queries.businesses import business_get``).
"""

# Importing a module registers its operations.
from hubs.queries import taxonomy
from hubs.queries import plan_catalog
from hubs.queries import access_control
from hubs.queries import signup
from hubs.queries import addresses
from hubs.queries import businesses
from hubs.queries import payers
from hubs.queries import invitations
from hubs.queries import membership
from hubs.queries import system_checks
from hubs.queries import hub_sync
from hubs.queries import custom_domains
from hubs.queries import hub_usage
from hubs.queries import data_copies
