"""What a business may name as its own domain (HUBS-F17): the Hub refuses a whole snapshot (422) over a bad one, so
nothing it would refuse gets as far as a row (``hubs.domain_names``)."""

import pytest
from django.core.exceptions import ValidationError
from django.core.validators import DomainNameValidator
from django.http.request import validate_host

from hubs.domain_names import DomainRefused, Refusal, normalized

#: The Hub's ``ALLOWED_HOSTS`` in production (``aws`` ``stacks/prod/apps.tf``) and in local development.
HUB_ALLOWED_HOSTS = [".erplora.com", "hub.erplora.internal", ".localhost", "127.0.0.1", "localhost"]


def hub_accepts(domain: str) -> bool:
    """The Hub's ``base.schemas.custom_domain_of_photo`` (hub#812), word by word: what its 422 tests."""
    value = domain.lower().removesuffix(".")
    if len(value) > 253 or value.endswith("."):
        return False
    try:
        DomainNameValidator(accept_idna=False)(value)
    except ValidationError:
        return False
    if value.rpartition(".")[2].isdigit():
        return False
    return not validate_host(value, HUB_ALLOWED_HOSTS)


@pytest.mark.parametrize(
    ("typed", "stored"),
    [
        ("www.minegocio.es", "www.minegocio.es"),
        ("  WWW.MiNegocio.ES  ", "www.minegocio.es"),
        ("www.minegocio.es.", "www.minegocio.es"),
        ("tienda.minegocio.co.uk", "tienda.minegocio.co.uk"),
        ("www.peluquería.es", "www.xn--peluquera-n5a.es"),
        ("WWW.PELUQUERÍA.ES", "www.xn--peluquera-n5a.es"),
        ("www.xn--peluquera-n5a.es", "www.xn--peluquera-n5a.es"),
    ],
)
def test_a_domain_is_kept_lowercase_ascii_and_without_its_final_dot(typed, stored):
    assert normalized(typed) == stored
    assert hub_accepts(stored)


@pytest.mark.parametrize(
    ("typed", "why"),
    [
        ("https://www.minegocio.es", "scheme"),
        ("http://www.minegocio.es/", "scheme"),
        ("www.minegocio.es/carta", "path"),
        ("www.minegocio.es:8443", "port"),
        ("*.minegocio.es", "wildcard"),
        ("www.*.minegocio.es", "wildcard"),
        ("192.168.1.10", "ip"),
        ("8.8.8.8", "ip"),
        ("[2001:db8::1]", "ipv6"),
        ("2001:db8::1", "ipv6"),
        ("www.minegocio.123", "numeric tld"),
        ("minegocio", "no tld"),
        ("localhost", "no tld"),
        ("", "empty"),
        ("   ", "blank"),
        (".", "only a dot"),
        ("www..minegocio.es", "empty label"),
        (".minegocio.es", "leading dot"),
        ("www.minegocio.es..", "two final dots"),
        ("-www.minegocio.es", "leading hyphen"),
        ("www-.minegocio.es", "trailing hyphen"),
        ("www_1.minegocio.es", "underscore"),
        ("www minegocio.es", "space"),
        ("www.minegocio.es\n", "new line after the name is trimmed, so one inside"),
        ("www.mine\ngocio.es", "new line inside"),
        ("user@www.minegocio.es", "user"),
        ("a" * 64 + ".minegocio.es", "label too long"),
        (".".join(["a" * 60] * 5) + ".es", "name too long"),
        ("a" * 40 + "." + "b" * 21 + ".es", "65 characters: ACM takes 64 at most in a certificate's first name"),
        ("www.xn--a.es", "punycode that decodes to nothing valid"),
        ("www.­.es", "a character IDNA maps to nothing"),
    ],
)
def test_what_the_hub_refuses_never_reaches_a_row(typed, why):
    if why.startswith("new line after"):
        assert normalized(typed) == "www.minegocio.es"
        return
    with pytest.raises(DomainRefused) as refused:
        normalized(typed)
    assert refused.value.reason == Refusal.NOT_A_DOMAIN


@pytest.mark.parametrize(
    "typed",
    [
        "erplora.com",
        "ERPLORA.COM",
        "erplora.com.",
        "www.erplora.com",
        "hub-0193.erplora.com",
        "a.b.erplora.com",
        "hub.erplora.internal",
        "algo.erplora.internal",
        "hubs.localhost",
        "pre.erplora.com",
    ],
)
def test_erplora_and_the_hosts_the_hub_already_answers_are_never_a_customers(typed):
    with pytest.raises(DomainRefused) as refused:
        normalized(typed)
    assert refused.value.reason == Refusal.OURS


def test_the_longest_name_a_certificate_takes_is_a_domain():
    name = "a" * 40 + "." + "b" * 20 + ".es"
    assert len(name) == 64
    assert normalized(name) == name


@pytest.mark.parametrize("typed", ["noterplora.com", "erplora.com.es", "www.erplora.es", "localhost.es", "x-erplora.com"])
def test_a_name_that_only_looks_like_ours_is_a_customers(typed):
    assert normalized(typed) == typed
    assert hub_accepts(typed)


def test_the_public_host_of_this_deployment_is_ours_too(settings):
    settings.PUBLIC_HOST = "plataforma.example.org"
    with pytest.raises(DomainRefused) as refused:
        normalized("www.plataforma.example.org")
    assert refused.value.reason == Refusal.OURS


@pytest.mark.parametrize(
    "typed",
    [
        "www.minegocio.es",
        "WWW.MINEGOCIO.ES.",
        "www.peluquería.es",
        "https://www.minegocio.es",
        "www.minegocio.es:8443",
        "*.minegocio.es",
        "1.2.3.4",
        "www.minegocio.123",
        "minegocio",
        "www.erplora.com",
        "hub.erplora.internal",
        "algo.localhost",
        "ñandú.es",
        "a_b.es",
        "ＷＷＷ．minegocio．es",
    ],
)
def test_all_that_passes_the_hub_accepts_in_its_snapshot(typed):
    """The guard of the contract: a domain this module lets by can never make the Hub refuse the whole snapshot."""
    try:
        stored = normalized(typed)
    except DomainRefused:
        return
    assert hub_accepts(stored), f"{typed!r} became {stored!r}, which the Hub answers with a 422"
