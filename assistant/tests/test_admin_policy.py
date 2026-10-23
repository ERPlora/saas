"""«Model that answers» in the admin (ASSISTANT-G17, G10, G60): one page for the one policy, with the model that
answers and the fallback one, saved through ``assistant.policy.update`` as the member of the staff who clicks."""

import pytest
from django.contrib.messages import get_messages

from assistant.models import AIModel, AIRoutingPolicy
from assistant.tests.conftest import grant

pytestmark = pytest.mark.django_db

POLICY = "/admin/assistant/airoutingpolicy/policy/"


@pytest.fixture
def models(provider):
    return {
        "large": AIModel.objects.create(provider=provider, model_id="gpt-5.5", display_name="GPT-5.5"),
        "small": AIModel.objects.create(provider=provider, model_id="gpt-5.4-mini", display_name="GPT-5.4 mini"),
    }


@pytest.fixture
def as_ai_admin(client, ai_admin):
    client.force_login(ai_admin)
    return client


def texts(response) -> list[str]:
    return [str(message) for message in get_messages(response.wsgi_request)]


def test_the_list_of_the_policy_opens_its_one_page(as_ai_admin):
    response = as_ai_admin.get("/admin/assistant/airoutingpolicy/")

    assert response.status_code == 302 and response["Location"] == POLICY


def test_the_page_offers_the_models_that_can_answer_with_the_current_choice(as_ai_admin, models):
    policy = AIRoutingPolicy.solo()
    policy.active_model = models["large"]
    policy.save()

    page = as_ai_admin.get(POLICY).content.decode()

    assert f'<option value="{models["large"].pk}" selected>OpenAI · GPT-5.5 (gpt-5.5)</option>' in page
    assert f'<option value="{models["small"].pk}">OpenAI · GPT-5.4 mini (gpt-5.4-mini)</option>' in page
    assert 'name="fallback_model"' in page


def test_a_model_that_answers_but_was_turned_off_is_warned(as_ai_admin, models):
    policy = AIRoutingPolicy.solo()
    policy.active_model = models["large"]
    policy.save()
    models["large"].is_available = False
    models["large"].save()

    page = as_ai_admin.get(POLICY).content.decode()

    assert "The model that answers is off or its provider is: choose another one." in page


def test_saving_the_choice_changes_the_model_that_answers(as_ai_admin, ai_admin, models):
    response = as_ai_admin.post(POLICY, {"active_model": str(models["small"].pk), "fallback_model": str(models["large"].pk)})

    assert response.status_code == 302 and response["Location"] == POLICY
    policy = AIRoutingPolicy.solo()
    assert (policy.active_model, policy.fallback_model, policy.updated_by) == (models["small"], models["large"], ai_admin)
    assert texts(response) == ["The model that answers was saved."]


def test_a_refused_choice_says_why_and_saves_nothing(as_ai_admin, models):
    response = as_ai_admin.post(POLICY, {"active_model": str(models["small"].pk), "fallback_model": str(models["small"].pk)})

    assert response.status_code == 302
    assert texts(response) == ["The fallback model must be another model."]
    assert AIRoutingPolicy.solo().active_model is None


def test_a_member_who_may_only_look_cannot_save(client, make_user, models):
    viewer = grant(make_user("viewer@erplora.com", is_staff=True), "view_airoutingpolicy")
    client.force_login(viewer)

    page = client.get(POLICY).content.decode()
    assert 'value="Save"' not in page
    assert '<select name="active_model" id="id_active_model" disabled>' in page

    client.post(POLICY, {"active_model": str(models["small"].pk)})
    assert AIRoutingPolicy.solo().active_model is None


def test_the_policy_is_neither_added_nor_deleted_by_hand(as_ai_admin):
    assert as_ai_admin.get("/admin/assistant/airoutingpolicy/add/").status_code == 403


def test_without_the_permission_the_page_is_refused(client, plain_staff):
    client.force_login(plain_staff)

    assert client.get(POLICY).status_code == 403


def test_without_a_session_the_page_asks_to_sign_in(client):
    response = client.get(POLICY)

    assert response.status_code == 302 and "/admin/login/" in response["Location"]
