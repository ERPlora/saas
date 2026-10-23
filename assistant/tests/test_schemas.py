"""The inputs and outputs of the assistant's operations (``assistant.schemas``): a provider's key travels as a
secret, so neither the ``repr`` of an input nor its dump shows it."""

from pydantic import SecretStr

from assistant.schemas import CredentialIn
from assistant.tests.conftest import API_KEY

PROVIDER = "0190b3a0-0000-7000-8000-000000000000"


def test_the_key_of_an_input_is_a_secret():
    data = CredentialIn(provider=PROVIDER, label="default", api_key=API_KEY)

    assert isinstance(data.api_key, SecretStr)
    assert data.api_key.get_secret_value() == API_KEY
    assert API_KEY not in repr(data)
    assert API_KEY not in data.model_dump_json()


def test_a_key_of_spaces_is_no_key():
    assert CredentialIn(provider=PROVIDER, label="default", api_key="   ").api_key is None
    assert CredentialIn(provider=PROVIDER, label="default").api_key is None


def test_the_label_is_trimmed_and_defaults_to_default():
    assert CredentialIn(provider=PROVIDER).label == "default"
    assert CredentialIn(provider=PROVIDER, label="  main ").label == "main"
