"""Django admin of the AI gateway (``erplora.com/admin``): what ERPlora's staff configure so the assistant answers,
one module per page: the providers with their models and «Choose models from the provider» (``providers``), «Model
that answers» with «Try a model» (``routing_policy``; the run of a try, ``model_tries``) and «Assistant usage
records» (``usage``). The member of the staff acting, as the services see them, is ``staff``.

Only active staff enter the admin (``accounts.admin.sign_in.admin_has_permission``) and each page asks the model
permission of Django that backs it; ``support`` gets none of the assistant's (its keys are ERPlora's spend).
"""

# Importing a module registers its admins, in this order; the ``as`` tells ruff the import is kept on purpose.
from assistant.admin import staff as staff
from assistant.admin import model_tries as model_tries
from assistant.admin import providers as providers
from assistant.admin import routing_policy as routing_policy
from assistant.admin import usage as usage
