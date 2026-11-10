"""A mail that cannot leave while allauth is answering a request is a handled 503, never a 500 (saas#391).

allauth mails inside its own views (the sign-up's code, the reset link). When the mailer refuses (SES still in its
sandbox mails nobody who is not verified), the exception left the view and the browser got Django's HTML 500. The
adapter now logs the failure and raises ``MailNotSent``; ``MailOutageMiddleware`` answers it in allauth's own
error envelope with the code ``mail_unavailable``, which the pages show as their usual «try again» error.
"""

from django.http import JsonResponse
from django.utils.translation import gettext as _


class MailNotSent(Exception):
    """The mailer refused a mail allauth had to send (the cause is chained and was logged)."""


class MailOutageMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        if not isinstance(exception, MailNotSent):
            return None
        message = _("We could not send the email right now. Try again in a few minutes.")
        return JsonResponse(
            {"status": 503, "errors": [{"code": "mail_unavailable", "message": message}]}, status=503
        )
