"""The inputs and outputs of the assistant's operations (``assistant.schemas``): a provider's key travels as a
secret, so neither the ``repr`` of an input nor its dump shows it."""

from assistant.tests.conftest import API_KEY

PROVIDER = "0190b3a0-0000-7000-8000-000000000000"


def test_the_key_of_a_connection_is_a_secret():
    from assistant.schemas import ConnectionOut

    out = ConnectionOut(id=PROVIDER, name="OpenAI", kind="openai", base_url="https://api.openai.com/v1", api_key=API_KEY, existing=[])

    assert API_KEY not in repr(out) and API_KEY not in out.model_dump_json()
    assert out.api_key.get_secret_value() == API_KEY
