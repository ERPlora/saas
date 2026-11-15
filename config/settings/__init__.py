"""Django settings of the SaaS.

Configuration comes from the process environment or this repo's ``.env`` through python-decouple,
never from a ``.env`` further up the tree: one there may be the Hub's (its ``DB_NAME`` is
``hub``). ``DEBUG`` is off by default: production must provide ``SECRET_KEY``,
``INTERNAL_SHARED_SECRET``, ``GOOGLE_OAUTH_CLIENT_ID`` and ``GOOGLE_OAUTH_CLIENT_SECRET``; local
development sets ``DEBUG=True`` (``.env.example``) and gets defaults for the root ``compose.yaml``.

Each module of this package holds one concern; Django reads the upper-case names of all of them from here.
"""

from config.settings.core import *
from config.settings.application import *
from config.settings.backends import *
from config.settings.accounts import *
from config.settings.hub_contract import *
from config.settings.web import *
from config.settings.mail import *
from config.settings.public import *
from config.settings.aws import *
from config.settings.fiscal import *
from config.settings.billing import *
from config.settings.assistant import *
from config.settings.whatsapp import *
