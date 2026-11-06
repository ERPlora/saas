"""What the panel's e2e specs remove when they end (``removingAccountsOf`` of ``tests/e2e/panel/fixtures.ts``, run by
``removeAccountsOf`` and ``removeAccountsWarm``), kept honest here because the CI does not run the e2e: a spec's
accounts and businesses go with the billing profiles they would leave ownerless (saas#374), and a profile of another
account stays, even one that paid a business a spec's account worked in.

The snippet is read from ``fixtures.ts`` as the spec sends it and run as the warm Django runs it.
"""

import json
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from hubs.models import BillingProfile, Hub, HubMember

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "e2e" / "panel" / "fixtures.ts"
PREFIX = "e2e-spec-"

pytestmark = pytest.mark.django_db


def removing_accounts_of(prefix: str) -> str:
    """The Python of ``removingAccountsOf(prefix)``: its array of lines, each one unquoted, joined as the spec joins it."""
    lines = FIXTURES.read_text().split("\n")
    start = lines.index("const removingAccountsOf = (prefix: string) =>") + 2
    end = lines.index("  ].join('\\n');", start)
    snippet = []
    for line in lines[start:end]:
        item = line.strip().removesuffix(",")
        quote = item[0]
        assert quote in "'`" and item.endswith(quote), f"not a one-line string of the snippet: {item}"
        body = item[1:-1]
        snippet.append(body.replace("${JSON.stringify(prefix)}", json.dumps(prefix)) if quote == "`" else body)
    return "\n".join(snippet)


def remove_accounts_of(prefix: str) -> None:
    exec(compile(removing_accounts_of(prefix), "<removingAccountsOf>", "exec"), {})


def account(email: str):
    return get_user_model().objects.create_user(email=email, password="Centeno-y-masa-madre-26")


def business(slug: str, owner, profile, *employees) -> Hub:
    now = timezone.now()
    hub = Hub.objects.create(slug=slug, name=slug, country="ES", billing_profile=profile)
    HubMember.objects.create(hub=hub, user=owner, role=HubMember.Role.OWNER, joined_at=now, accepted_at=now)
    for person in employees:
        HubMember.objects.create(hub=hub, user=person, role=HubMember.Role.EMPLOYEE, joined_at=now, accepted_at=now)
    return hub


def test_a_spec_account_goes_with_its_business_and_the_profile_that_pays_it():
    owner = account(f"{PREFIX}owner@example.com")
    profile = BillingProfile.objects.create(owner=owner)
    business("e2e-spec-bar", owner, profile)
    remove_accounts_of(PREFIX)
    assert not get_user_model().objects.filter(email__startswith=PREFIX).exists()
    assert not Hub.objects.filter(slug="e2e-spec-bar").exists()
    assert not BillingProfile.objects.filter(pk=profile.pk).exists()


def test_the_ownerless_profile_of_a_removed_business_goes():
    owner = account(f"{PREFIX}owner@example.com")
    profile = BillingProfile.objects.create(owner=None)
    business("e2e-spec-bar", owner, profile)
    remove_accounts_of(PREFIX)
    assert not BillingProfile.objects.filter(pk=profile.pk).exists()


def test_the_profile_of_another_account_stays_when_its_business_had_a_spec_employee():
    other = account("someone-else@example.com")
    theirs = BillingProfile.objects.create(owner=other)
    business("their-bar", other, theirs, account(f"{PREFIX}employee@example.com"))
    remove_accounts_of(PREFIX)
    assert BillingProfile.objects.filter(pk=theirs.pk, owner=other).exists()


def test_a_profile_of_another_account_that_pays_another_business_too_stays_and_nothing_fails():
    other = account("someone-else@example.com")
    theirs = BillingProfile.objects.create(owner=other)
    business("their-bar", other, theirs, account(f"{PREFIX}employee@example.com"))
    business("their-cafe", other, theirs)
    remove_accounts_of(PREFIX)
    assert Hub.objects.filter(slug="their-cafe", billing_profile=theirs).exists()


def test_what_another_spec_left_is_not_touched():
    other = account("e2e-other-spec-owner@example.com")
    theirs = BillingProfile.objects.create(owner=other)
    business("e2e-other-spec-bar", other, theirs)
    remove_accounts_of(PREFIX)
    assert get_user_model().objects.filter(pk=other.pk).exists()
    assert BillingProfile.objects.filter(pk=theirs.pk).exists()
