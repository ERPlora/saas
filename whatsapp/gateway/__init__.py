"""What erplora.com does for a business's WhatsApp, step by step: the commands of ``services`` around the calls to
Meta (``meta``) and to the Hub (``hub_client``), so that no transaction waits for a third party. No ORM here.

One module per job; a name is imported from its own module, never from this package:

- ``deliveries``: what Meta reports, pushed to the Hub, and door 6;
- ``sending``: door 5;
- ``message_templates``: doors 8 and 9, and Meta's list of templates read again into the mirror;
- ``token_renewal``: the daily renewal of Meta's permission;
- ``number_connection``: doors 10–12;
- ``answers``: what a door answers, and Meta's codes of a refusal by what the Hub is told.
"""
