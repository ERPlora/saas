"""«Continue with Google» at the paths registered with Google (PLAN-SAAS §6, ADR-0154).

allauth's own Google views, mounted at ``/auth/google/login/`` and ``/auth/google/callback/`` under
allauth's route names (``config/urls.py``): allauth builds the ``redirect_uri`` of both the
authorization request and the token exchange from ``reverse("google_callback")``, and both must be
the URI registered with Google. Without credentials (``GOOGLE_OAUTH_ENABLED``) they answer 404.
"""

from functools import wraps

from allauth.socialaccount.providers.google.views import oauth2_callback, oauth2_login
from django.conf import settings
from django.http import Http404


def _only_when_configured(view):
    @wraps(view)
    def guarded(request, *args, **kwargs):
        if not settings.GOOGLE_OAUTH_ENABLED:
            raise Http404("Google sign-in is not configured.")
        return view(request, *args, **kwargs)

    return guarded


login = _only_when_configured(oauth2_login)
callback = _only_when_configured(oauth2_callback)
