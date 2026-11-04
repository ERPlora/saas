"""A service's refusal of what a form marks: the notice on top says to look at the fields, each with its own message.

The words of ``live.ninja``'s refusal of the schema (ERPlora/live#34), so a person never reads two sentences for one
thing. A refusal that marks nothing on a form says its own reason instead: ``InvalidPayload(reason, fields={…: reason})``.
"""

from django.utils.translation import gettext
from live.errors import InvalidPayload


def fields_refused(fields: dict[str, str], *, code: str | None = None) -> InvalidPayload:
    return InvalidPayload(gettext("Check the highlighted details."), code=code, fields=fields)
