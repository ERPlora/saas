"""«Continue with Google» (PLAN-SAAS §6, ADR-0154), over allauth.headless (headless only).

The Vue sign-in posts allauth.headless's provider redirect (``provider_redirect``) with the page to come
back to, and Google comes back to ``/auth/google/callback/``, the URI registered with it: allauth's own
callback view, mounted there under allauth's route name (``config/urls.py``), because allauth builds the
``redirect_uri`` of both the authorization request and the token exchange from
``reverse("google_callback")``. Without credentials (``GOOGLE_OAUTH_ENABLED``) neither is served: the
redirect answers allauth.headless's JSON 404 (``doors.closed``), the callback Django's.
"""

from functools import wraps

from allauth.headless.constants import Client
from allauth.headless.socialaccount.views import RedirectToProviderView
from allauth.socialaccount.providers.google.views import oauth2_callback
from django.conf import settings
from django.http import Http404

from accounts import doors


def _not_found(request):
    raise Http404("Google sign-in is not configured.")


def _only_when_configured(view, refusal):
    @wraps(view)
    def guarded(request, *args, **kwargs):
        if not settings.GOOGLE_OAUTH_ENABLED:
            return refusal(request)
        return view(request, *args, **kwargs)

    return guarded


provider_redirect = _only_when_configured(RedirectToProviderView.as_api_view(client=Client.BROWSER), doors.closed)
callback = _only_when_configured(oauth2_callback, _not_found)
