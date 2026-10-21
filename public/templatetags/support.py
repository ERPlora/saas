"""``{% support_email %}``: the support address for a template rendered without the public web's context
processor, like Django's 500 page (``templates/errors/base.html``). One source, ``settings.SUPPORT_EMAIL``, the
same the footer, the contact page and the SPA's «Contact Support» write (PUBLIC-F18)."""

from django import template
from django.conf import settings

register = template.Library()


@register.simple_tag
def support_email() -> str:
    return settings.SUPPORT_EMAIL
