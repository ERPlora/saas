"""The installed app's door into a business: ``GET /shell/open/<id>/`` (PLAN-SAAS bloque 3; PLAN-HUB round 18).

``ERPlora/app`` boots on ``{SaaS}/shell/`` (the SPA's launcher under the app's address, ``hubs/frontend/routes.ts``)
and links the till to a hub only when a navigation with ``?shell=1`` leaves an entry page of the SaaS
(``hub_link.rs``): without it every hardware call answers ``not_the_linked_hub``. This door runs «Open»
(``hubs.business.open``) for the signed-in account with that mark and sends the window to the Hub's start of the
jump, as the old SaaS's ``/shell/open/<id>/`` did. The launcher's «Open» inside the app asks the same operation
(``open-business.ts``); this address is the one a link can carry.

Signed out, the sign-in is the app's start (``/shell/?next=…``), which comes back here. A business of someone
else (or unknown) is 404, never named; one that does not open now (being prepared, suspended, deleted) goes back
to the launcher, which says why.
"""

from uuid import UUID

from django.contrib.auth.views import redirect_to_login
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from live.context import get_builder
from live.errors import Conflict, NotFound

from hubs import services
from hubs.schemas import BusinessOpenIn

#: The app's start: ``ERPlora/app`` boots there and it never changes (working-rules §12).
SHELL = "/shell/"


@never_cache
@require_GET
def open_business(request: HttpRequest, hub_id: UUID) -> HttpResponse:
    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path(), login_url=SHELL)
    try:
        opened = services.business_open(
            get_builder().from_request(request), BusinessOpenIn(id=hub_id, shell=True)
        )
    except NotFound as missing:
        raise Http404(str(missing)) from missing
    except Conflict:
        return HttpResponseRedirect(SHELL)
    return HttpResponseRedirect(opened.url)
