"""Events of billing (``<app>.<entity>.<fact>``): recorded by services.py in the outbox.

billing reacts to no event of another app, so this module only names its own. No live query cites them
yet (billing has no ``live.py``): the forms ask once and read the answer.
"""

#: A VAT number was asked about in VIES and the answer logged (payload: ``vat_number``, ``status``).
VAT_CHECK_COMPLETED = "billing.vat_check.completed"

ALL = [VAT_CHECK_COMPLETED]
