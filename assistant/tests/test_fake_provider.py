"""The provider's API the assistant's tests talk to (``fake_provider``): what it answers when nothing was scripted,
and what it records of each request."""

import httpx


def test_a_request_nothing_was_scripted_for_gets_a_404_in_openais_error_shape(fake_provider):
    response = httpx.post(f"{fake_provider.url}/v1/chat/completions?stream=1", json={"model": "gpt-4o"})

    assert response.status_code == 404
    assert response.json() == {"error": {"message": "No route POST /v1/chat/completions"}}
    [seen] = fake_provider.requests
    assert (seen.method, seen.path, seen.body) == ("POST", "/v1/chat/completions?stream=1", {"model": "gpt-4o"})


def test_a_body_that_is_not_json_is_recorded_as_its_text(fake_provider):
    fake_provider.reply("POST", "/v1/files", json={"id": "file_1"})

    response = httpx.post(f"{fake_provider.url}/v1/files", content=b"plain words")

    assert response.json() == {"id": "file_1"}
    assert [seen.body for seen in fake_provider.requests] == ["plain words"]
