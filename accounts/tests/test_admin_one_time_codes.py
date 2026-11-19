"""The Django admin of the one-time codes: the jump's codes and the changes of email waiting, read only."""

import pytest

pytestmark = pytest.mark.django_db


def test_exchange_codes_are_read_only(staff_client):
    client, _ = staff_client

    assert client.get("/admin/accounts/authexchangecode/add/").status_code == 403


def test_a_change_of_email_waiting_is_seen_without_its_code_nor_its_session(staff_client, ana):
    from accounts.models import EmailChangeRequest

    client, _ = staff_client
    change = EmailChangeRequest.objects.create(
        user=ana, session_key="secret-session-key-0123456789", email="ana@new.example", code_hash="c0de" * 16
    )

    listing = client.get("/admin/accounts/emailchangerequest/")
    page = client.get(f"/admin/accounts/emailchangerequest/{change.pk}/change/")

    assert listing.status_code == page.status_code == 200
    assert "ana@new.example" in listing.text
    assert "c0de" not in listing.text + page.text and "secret-session-key" not in listing.text + page.text
    assert client.get("/admin/accounts/emailchangerequest/add/").status_code == 403
