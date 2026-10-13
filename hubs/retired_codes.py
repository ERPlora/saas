"""Business-type codes the catalogue no longer serves, and the row that replaced each one.

Ported from ERPlora/saas ``public/catalog/retired_codes.py`` (origin/develop). A code is public
(ADR-0129): it is in ``/industries/<code>/`` URLs a search engine indexed and in sign-up forms a
browser cached. Every door that takes a code from outside passes it through
``current_business_type_code`` first.

``peluqueria`` (saas#2099): a legacy row with the same visible name as ``hair_salon``.
"""

RETIRED_BUSINESS_TYPE_CODES: dict[str, str] = {"peluqueria": "hair_salon"}


def current_business_type_code(code: str) -> str:
    """The code to look up today: the replacement of a retired one, or the code unchanged."""
    return RETIRED_BUSINESS_TYPE_CODES.get(code, code)
