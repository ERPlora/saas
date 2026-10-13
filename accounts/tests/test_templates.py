"""The account screens are Vue pages (``accounts/frontend/pages``): the launcher and every error
of the sign-in. Only the auto-submitted form of the jump to a hub stays a Django template, because
it is not a screen: it POSTs the one-time code to the hub (``hub_login_form.html``)."""

from pathlib import Path

from django.conf import settings
from django.template.loader import get_template

ACCOUNTS_TEMPLATES = Path(__file__).resolve().parent.parent / "templates" / "accounts"
SOCIALACCOUNT_TEMPLATES = Path(settings.BASE_DIR) / "templates" / "socialaccount"


def test_only_the_jump_form_stays_a_template():
    assert sorted(path.name for path in ACCOUNTS_TEMPLATES.iterdir()) == ["hub_login_form.html"]
    assert get_template("accounts/hub_login_form.html")


def test_the_google_error_screens_are_vue_pages_too():
    """allauth's «Third-Party Login Failure» and «Login Cancelled» now redirect to /login/error."""
    assert not (SOCIALACCOUNT_TEMPLATES / "authentication_error.html").exists()
    assert not (SOCIALACCOUNT_TEMPLATES / "login_cancelled.html").exists()
