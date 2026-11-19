"""Django admin of accounts, one module per concern: the users with their preferences and photo (``users``; their
businesses, ``hubs.admin``), the one-time codes (``one_time_codes``), the API keys (``api_keys``: a superuser revokes
them, and issues one for a team account), the sessions (``sessions``: ``allauth.usersessions``' own page, read only; a
superuser closes them, «Close sessions») and the audit trail (``audit_trail``). The jump to the Hub admin is
``hub_admin_jump`` and the admin's sign-in, ``sign_in``."""

# Importing a module registers its admins, in this order.
from accounts.admin import hub_admin_jump
from accounts.admin import users
from accounts.admin import sign_in
from accounts.admin import one_time_codes
from accounts.admin import api_keys
from accounts.admin import sessions
from accounts.admin import audit_trail
