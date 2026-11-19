"""The trial on ``/pricing/``: the line of each card, the note under the plans and the FAQ's answer.

* The trial range comes from the trial of each plan on sale (``trial_period_days`` of the operation's rows), the same
  reading as ``Plan.objects.signup_trial_days()``.
"""

from __future__ import annotations

import re

import pytest

from public import pricing
from public.tests.pricing_pages import UPGRADE_SECTION, card_items, get, html_of, make_plan, upgrade_section

pytestmark = [pytest.mark.django_db]


# --- The trial on the cards -------------------------------------------------------------------


def test_the_card_shows_the_trial_the_plan_grants(no_plans, client):
    make_plan("starter", trial_days=21)

    items = card_items(html_of(client), "Starter")

    assert items == ["Unlimited users", "All the apps turned on at once", "21-day free trial"]


def test_the_card_follows_the_plan_when_its_trial_changes(no_plans, client):
    starter = make_plan("starter", trial_days=15)
    starter.trial_period_days = 30
    starter.save()

    assert re.findall(r"\d+", card_items(html_of(client), "Starter")[-1]) == ["30"]


def test_a_plan_without_trial_shows_no_trial_line(no_plans, client):
    make_plan("free", trial_days=0)

    assert card_items(html_of(client), "Free") == ["Unlimited users", "All the apps turned on at once"]


def test_the_card_trial_is_translated(no_plans, client):
    make_plan("starter", trial_days=15, name_es="Starter")

    assert card_items(html_of(client, language="es"), "Starter")[-1] == (
        "15 días de prueba gratis"
    )


def test_an_upgrade_only_plan_is_shown_but_has_no_sign_up_nor_detail_page(no_plans, client):
    """/pricing/ shows an ``upgrade_only`` row under «More capacity», so a visitor knows it exists, but it is no plan
    to sign up on: not among the cards a visitor signs up on, no detail page and not in «Other plans». The Store
    offers it to a business that already pays and the checkout from Free refuses it (``billing.plan_upgrade_only``)."""
    make_plan("starter", trial_days=15)
    make_plan("pro", trial_days=15, upgrade_only=True)

    response = get(client)
    html = response.content.decode()

    assert [plan["slug"] for plan in response.context["plans_main"]] == ["starter"]
    assert [plan["slug"] for plan in response.context["plans_upgrade"]] == ["pro"]
    assert '<div class="ep-pricing-card__name">Pro</div>' in upgrade_section(html)
    assert '<div class="ep-pricing-card__name">Pro</div>' not in html.split(UPGRADE_SECTION, 1)[0]
    assert client.get("/pricing/pro/").status_code == 404
    others = get(client, "/pricing/starter/").context["other_plans"]
    assert [plan["slug"] for plan in others] == []


# --- The trial period -------------------------------------------------------------------------


def trial_note(html: str) -> str:
    match = re.search(r'<p id="pricing-trial-note"[^>]*>(.*?)</p>', html, re.S)
    assert match, "the pricing page lost its trial note under the plans"
    return " ".join(match.group(1).split())


def trial_answer(response) -> str:
    (item,) = [item for item in response.context["faq_items"] if item["key"] == "trial"]
    return str(item["answer"])


def note_and_answer(client, language: str | None = None) -> tuple[str, str]:
    response = get(client, language=language)
    return trial_note(response.content.decode()), trial_answer(response)


def test_the_page_states_the_trial_length_the_checkout_grants(no_plans, client):
    make_plan("free", trial_days=0)
    make_plan("starter", trial_days=15)
    make_plan("standard", trial_days=15)

    for text in note_and_answer(client):
        # The free plan's 0 is «no trial», not the short end of a range.
        assert re.findall(r"\d+", text) == ["15"], text


def test_the_page_follows_the_plan_when_its_trial_changes(no_plans, client):
    make_plan("starter", trial_days=30)

    for text in note_and_answer(client):
        assert re.findall(r"\d+", text) == ["30"], text


def test_plans_a_visitor_cannot_buy_do_not_count(no_plans, client):
    make_plan("starter", trial_days=15)
    make_plan("internal", trial_days=90, internal_only=True)
    make_plan("retired", trial_days=180, is_active=False)

    for text in note_and_answer(client):
        assert re.findall(r"\d+", text) == ["15"], text


def test_a_plan_reached_only_by_upgrading_does_not_count(no_plans, client):
    make_plan("starter", trial_days=15)
    make_plan("pro", trial_days=30, upgrade_only=True)

    for text in note_and_answer(client):
        assert re.findall(r"\d+", text) == ["15"], text


def test_plans_with_different_trials_are_stated_as_a_range(no_plans, client):
    make_plan("starter", trial_days=15)
    make_plan("standard", trial_days=30)

    for text in note_and_answer(client):
        assert re.findall(r"\d+", text) == ["15", "30"], text


def test_no_trial_on_sale_means_no_trial_promised(no_plans, client):
    make_plan("free", trial_days=0)
    make_plan("starter", trial_days=0)

    for text in note_and_answer(client):
        assert "trial" not in text.lower(), text
        assert not re.findall(r"\d+", text), text


def test_the_trial_is_promised_on_hub_creation_and_not_on_an_upgrade(no_plans, client):
    make_plan("starter", trial_days=15)

    note, answer = note_and_answer(client)

    assert "when you create a Hub" in note
    assert "when creating a Hub" in answer
    assert "does not start a new trial" in answer


def test_a_spanish_visitor_reads_the_trial_in_spanish(no_plans, client):
    make_plan("starter", trial_days=15)

    note, answer = note_and_answer(client, language="es")

    assert re.search(r"\b15 días\b", note), note
    assert "al crear un Hub" in note
    assert re.search(r"\b15 días\b", answer), answer
    assert "al crear un Hub" in answer
    assert "no inicia un nuevo periodo de prueba" in answer


def test_a_one_day_trial_reads_in_the_singular(no_plans, client):
    make_plan("starter", trial_days=1)

    note, answer = note_and_answer(client, language="es")

    assert re.search(r"\b1 día\b", note)
    assert re.search(r"\b1 día\b", answer)


def test_faq_items_called_on_its_own_reads_the_plans_too(no_plans):
    # A public entry point without the caller's reading: never a hand-typed length.
    make_plan("starter", trial_days=30)

    (item,) = [item for item in pricing.faq_items() if item["key"] == "trial"]

    assert re.findall(r"\d+", str(item["answer"])) == ["30"], item["answer"]
