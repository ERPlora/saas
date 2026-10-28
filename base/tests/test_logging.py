"""ACCOUNTS-G14 / ACCOUNTS-G76: the log keeps the event and loses the personal data and the secrets.

Ported from ERPlora/saas ``apps/core/tests/test_logging.py`` (origin/develop c5ca8cae8) with its traps: #969 (the
patterns redacted nothing Spanish, mangled an IBAN, kept a JWT's payload, and a filter DROPPED every line that merely
said "token" or "password" — the only evidence of a brute-force run), saas#2140 (the token rule ate the event keys the
alarms look for), saas#2445 (secrets under a quoted or prefixed key, short bearer credentials, hex credentials read as
hashes, 24-character tokens at a dash edge), saas#2458 (the password inside a connection url) and saas#2472 (a long
line held the process for seconds: every rule must run in linear time). Only the formatter is ported: the old
``SensitiveDataFilter`` had become a no-op kept for configuration compatibility, which this project does not need.
"""

from __future__ import annotations

import io
import logging
import random
import re

import pytest

from base.logging import GDPRSafeFormatter


def _fmt(message: str) -> str:
    formatter = GDPRSafeFormatter("%(message)s")
    record = logging.LogRecord("t", logging.INFO, __file__, 1, message, None, None)
    return formatter.format(record)


class TestSpanishIdentifiersAreRedacted:
    @pytest.mark.parametrize(
        "raw",
        [
            "+34 612 345 678",
            "+34612345678",
            "612345678",
            "912 345 678",
        ],
    )
    def test_spanish_phone_numbers(self, raw):
        assert raw not in _fmt(f"cliente {raw} llamó")

    @pytest.mark.parametrize("raw", ["12345678Z", "X1234567L", "B12345678"])
    def test_nif_nie_and_cif(self, raw):
        assert raw not in _fmt(f"documento {raw} verificado")

    def test_iban_is_redacted_whole_and_labelled_right(self):
        out = _fmt("cuenta ES9121000418450200051332 dada de alta")
        assert "ES9121000418450200051332" not in out
        assert "0200051332" not in out, "the IBAN was cut up, not redacted"
        assert "PHONE" not in out, "an IBAN labelled as a phone is worse than none"

    def test_a_jwt_is_redacted_completely(self):
        jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
        out = _fmt(f"authorization: Bearer {jwt}")
        assert "eyJzdWIiOiIxMjM0NTY3ODkwIn0" not in out, "the payload survived"
        assert "dBjftJeZ4CVP" not in out, "the signature survived"

    def test_a_base64url_token_is_redacted(self):
        token = "gAAAAABk-_Xy3mQ2n8pQ7rS9tU0vW1xY2zA3bC4dE5fG6hI7jK8lM9n"
        assert token not in _fmt(f"code={token}")


class TestItStillRedactsWhatItAlreadyDid:
    def test_email(self):
        assert "cliente@ejemplo.com" not in _fmt("alta de cliente@ejemplo.com")

    def test_credit_card(self):
        assert "4242 4242 4242 4242" not in _fmt("tarjeta 4242 4242 4242 4242")


class TestOrdinaryTextSurvives:
    @pytest.mark.parametrize(
        "message",
        [
            "POST /dashboard/hubs/ 200",
            "hub 3f2a activo con 12 usuarios",
            "migración 0042 aplicada en 1234 ms",
        ],
    )
    def test_it_does_not_mangle_normal_log_lines(self, message):
        assert _fmt(message) == message


class TestAuthenticationFailuresAreNotDiscarded:
    """#969: the lines an old filter silenced reach the log, word for word."""

    @pytest.mark.parametrize(
        "message",
        [
            "[hub-machine] invalid token for hub=3f2a",
            "[hub-machine] revoked token used for hub=3f2a",
            "[BOOTSTRAP] Invalid token for Hub 3f2a",
            "[AWS WEBHOOK] Invalid webhook secret",
            "WS auth: token rejected",
            "[WhatsApp] Webhook verification failed (bad token)",
        ],
    )
    def test_they_reach_the_log_as_written(self, message):
        assert _fmt(message) == message

    def test_no_filter_of_the_log_drops_a_record(self):
        """Redact the value, keep the event: a record that is dropped loses the evidence of an attack."""
        from django.conf import settings

        assert "filters" not in settings.LOGGING
        assert all("filters" not in handler for handler in settings.LOGGING["handlers"].values())

    def test_a_record_carrying_an_actual_secret_is_still_redacted_not_dropped(self):
        assert _fmt("login with password=SuperSecreta123") == "login with password=[SECRET_REDACTED]"


class TestOurOwnEventKeysSurvive:
    """saas#2140 — the token pattern ate the event keys the alerts grep for.

    ``TOKEN_PATTERN`` redacts any run of 24+ ``[A-Za-z0-9_-]``, so a long snake_case event key
    reached Loki as ``billing.module_purchase.[TOKEN_REDACTED]`` and a rule keyed on it never
    fired. An identifier we wrote is not a credential: it is lowercase words joined by
    underscores, while every secret this product mints or receives carries digits or capitals.
    """

    @pytest.mark.parametrize(
        "event",
        [
            "billing.module_purchase.period_ended_while_row_says_active",
            "provisioning.hub.deploy_finished_without_health_check",
            "marketplace.upstream_catalogue_returned_empty_list",
            # A key the old SaaS emitted (apps.dashboard.fiscal.vat).
            "fiscal.vat.stripe_charged_no_tax_on_subject_sale",
            # A word right at the cap: "internationalization" is 20 letters.
            "core.internationalization_bundle_missing",
        ],
    )
    def test_a_long_event_key_reaches_the_log_whole(self, event):
        assert _fmt(f"event={event} purchase_id=42") == f"event={event} purchase_id=42"

    def test_a_key_and_a_credential_on_the_same_line_part_ways(self):
        key = "billing.module_purchase.period_ended_while_row_says_active"
        secret = "erpk_live_Q7cRm2ZtV9xKp4LwN8bYs3HdJ6fGa1EqU5oTi0WkBnMvCzXyPl"

        assert _fmt(f"event={key} rejected key {secret}") == f"event={key} rejected key [TOKEN_REDACTED]"


class TestOurOwnIdsSurvive:
    """ACCOUNTS-F40: the ids stay, so the team can follow what happened (ACCOUNTS-F35 logs an account it could not
    erase by its id, never by its email). Every key of this project is a UUIDv7 (``uuid.uuid7()``) and no credential is
    UUID-shaped (no ``UUIDField`` but primary keys), yet the token rule read every ``user=<id>`` as a credential."""

    def test_an_id_as_python_prints_it_reaches_the_log_whole(self):
        account, business = "019a1b2c-3d4e-7f60-8a1b-2c3d4e5f6071", "019a1b2c-3d4e-7f60-9b2c-3d4e5f607182"

        line = f"accounts.anonymize_old_users.failed user={account} hub={business}"

        assert _fmt(line) == line

    def test_the_email_beside_an_id_still_goes(self):
        account = "019a1b2c-3d4e-7f60-8a1b-2c3d4e5f6071"

        assert _fmt(f"user={account} email=ana@example.com") == f"user={account} email=[EMAIL_REDACTED]"

    @pytest.mark.parametrize(
        "secret",
        [
            # Only the id as Python prints it: hyphens swapped for underscores, capitals, or more behind it is no id.
            "550e8400_e29b_41d4_a716_446655440000",
            "550E8400-E29B-41D4-A716-446655440000",
            "550e8400-e29b-41d4-a716-446655440000abcd",
            "550e8400-e29b-41d4-a716-446655440000-e29b",
        ],
    )
    def test_what_only_looks_like_an_id_is_still_redacted(self, secret):
        out = _fmt(f"key {secret} used")

        assert secret not in out
        assert "[TOKEN_REDACTED]" in out


class TestCredentialsStillLookLikeCredentials:
    """The other side of saas#2140: widening the keep-list must not open a door to a secret."""

    @pytest.mark.parametrize(
        "secret",
        [
            # The Hub's API key, ``erpk_<env>_`` + 48 base62, and ours, ``erps_live_`` + 48 (accounts.models).
            "erpk_live_Q7cRm2ZtV9xKp4LwN8bYs3HdJ6fGa1EqU5oTi0WkBnMvCzXyPl",
            "erpk_pre_Q7cRm2ZtV9xKp4LwN8bYs3HdJ6fGa1EqU5oTi0WkBnMvCzXyPl",
            "erps_live_Q7cRm2ZtV9xKp4LwN8bYs3HdJ6fGa1EqU5oTi0WkBnMvCzXyPl",
            # Same shape, but a secret that happens to have drawn only lowercase letters.
            "erpk_live_qwertyuiopasdfghjklzxcvbnmqwertyuiopasdfghjklzxc",
            # Stripe-shaped keys, spelled in two halves so no secret scanner takes the fixture for a live key.
            "sk_" + "live_51NqZpLKj8vXyQwErTyUiOpAsDfGhJkL",
            "whsec_" + "abcdefghijklmnopqrstuvwxyzabcdef",
            # A lowercase hex secret that is not a hash length the keep-list allows.
            "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b",
            # A long lowercase blob with a single underscore: not words, a secret.
            "session_qwertyuiopasdfghjklzxcvbnmqwerty",
            "qwertyuiopasdfghjklzxcvbnmqwerty",
            "qwertyuiopasdfghjklzxcvbnm_live",
            # Word-sized chunks joined by underscores, but carrying digits or capitals.
            "a1b2c3d4_e5f6a7b8_c9d0e1f2_a3b4",
            "AbCdEfGh_IjKlMnOp_QrStUvWx_YzAb",
            # A lowercase prefix does not vouch for the lowercase-and-digits blob behind it.
            "session_a1b2c3d4e5f6a7b8c9d0",
            # Stripe's other key kinds, as issued and with a secret that drew only lowercase.
            "rk_" + "live_51NqZpLKj8vXyQwErTyUiOpAsDfGhJkL",
            "rk_" + "live_qwertyuiopasdfghjklzxcvbnm",
            "sk_" + "test_qwertyuiopasdfghjklzxcvbnm",
            "pk_" + "live_qwertyuiopasdfghjklzxcvbnm",
            # The word cap is 20 letters: one more and it is a blob, wherever it sits.
            "whsec_" + "abcdefghijklmnopqrstu",
            "abcdefghijklmnopqrstu_live",
            # base64url (``secrets.token_urlsafe``) carrying both of its extra characters.
            "kJ8x_Q2m-Zt7VwP_n4Ls-Yb9Hd3R_fG6aE1q",
            # A uuid with its hyphens swapped for underscores. As Python prints it, it is one of our ids, and it stays
            # (TestOurOwnIdsSurvive): the old SaaS's list had it here, but no credential here is UUID-shaped.
            "550e8400_e29b_41d4_a716_446655440000",
            # A slug is cut from the business name, and a sole trader's is their own name: a
            # hyphen anywhere keeps it out of the event-key rule, underscore prefix or not.
            "maria-garcia-lopez-peluqueria",
            "hub_maria-garcia-lopez-peluqueria",
            "maria_garcia-lopez-peluqueria",
        ],
    )
    def test_a_credential_is_still_redacted(self, secret):
        out = _fmt(f"key {secret} used")
        assert secret not in out
        assert "[TOKEN_REDACTED]" in out

    def test_no_api_key_we_mint_can_pass_for_an_event_key(self):
        """Structural, not luck — pinned against the real mint (``accounts.models.ApiKey``).

        The worst draw is a secret made only of characters an event key may carry. It is still redacted because the
        mint has no underscore and its secret is longer than any word, so shortening ``API_KEY_SECRET_LENGTH`` or adding
        ``_`` to ``API_KEY_ALPHABET`` has to fail here and not in the production logs.
        """
        from accounts import models as keys

        event_key_chars = [c for c in keys.API_KEY_ALPHABET if c.islower() or c == "_"]
        rng = random.Random(2140)
        for _ in range(200):
            secret = "".join(rng.choice(event_key_chars) for _ in range(keys.API_KEY_SECRET_LENGTH))
            raw = f"{keys.API_KEY_PREFIX}{secret}"
            assert _fmt(f"key {raw} used") == "key [TOKEN_REDACTED] used"

    def test_every_api_key_we_mint_is_redacted(self):
        from accounts.models import ApiKey

        for _ in range(200):
            raw, _prefix, _hash = ApiKey.new_secret()
            assert _fmt(f"key {raw} used") == "key [TOKEN_REDACTED] used"

    def test_a_jwt_whose_segments_are_lowercase_words_is_still_a_jwt(self):
        """The JWT pattern runs first, so the event-key rule never gets to vouch for a segment."""
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature_made_of_lowercase_words"

        assert _fmt(f"rejected {jwt}") == "rejected [TOKEN_REDACTED]"


class TestSecretsWrittenTheWaysTheRedactorMissed:
    """saas#2445 — four shapes of a credential walked through the redactor whole.

    Each case pairs with what must keep reading as it was: the redactor is a safety net for the
    day someone logs a value by mistake, and a net that also eats ordinary lines gets switched off.
    """

    @pytest.mark.parametrize(
        ("line", "secret"),
        [
            # JSON body, as it travels between services.
            ('body={"password": "hunter2hunter2"}', "hunter2hunter2"),
            ('body={"password":"hunter2hunter2"}', "hunter2hunter2"),
            # repr() of a dict and of a QueryDict (``request.POST``).
            ("POST {'password': 'Tr0ub4dor&3xyz'}", "Tr0ub4dor&3xyz"),
            ("POST {'password': ['Tr0ub4dor&3xyz']}", "Tr0ub4dor&3xyz"),
            # A quoted value with a space in it goes whole, not up to the space.
            ('{"password": "correct horse battery staple"}', "battery staple"),
            ("{'password': 'correct horse battery staple'}", "battery staple"),
            # A passphrase in lowercase words joined by ``_`` goes by its key, not by its shape.
            ("{'password': 'correct_horse_battery_staple'}", "correct_horse_battery_staple"),
            # Field names that end in a credential word (the old SaaS's Hub.cloud_api_token,
            # Hub.hub_secret_key) and the usual OAuth ones.
            ("hub={'cloud_api_token': 'Zq81mXw0pLk2'}", "Zq81mXw0pLk2"),
            ("hub_secret_key=Zq81mXw0pLk2", "Zq81mXw0pLk2"),
            ('{"access_token": "Zq81mXw0pLk2"}', "Zq81mXw0pLk2"),
            ("client_secret: Zq81mXw0pLk2", "Zq81mXw0pLk2"),
        ],
    )
    def test_a_password_under_a_quoted_or_prefixed_key_is_redacted(self, line, secret):
        out = _fmt(line)
        assert secret not in out
        assert "[SECRET_REDACTED]" in out

    def test_the_line_around_a_redacted_value_keeps_its_shape(self):
        """Only the value goes: the key, its quotes and the brackets still say what happened."""
        assert (
            _fmt('body={"password": "hunter2hunter2", "hub": 3}') == 'body={"password": "[SECRET_REDACTED]", "hub": 3}'
        )

    @pytest.mark.parametrize(
        "line",
        [
            "Authorization: Bearer abcDEF123456",
            "authorization=Bearer abcDEF123456",
            "headers={'Authorization': 'Bearer abcDEF123456'}",
        ],
    )
    def test_a_short_bearer_token_goes_with_the_header(self, line):
        out = _fmt(line)
        assert "abcDEF123456" not in out
        assert "[SECRET_REDACTED]" in out

    def test_the_scheme_stays_and_the_credential_goes(self):
        assert _fmt("Authorization: Bearer abcDEF123456") == "Authorization: Bearer [SECRET_REDACTED]"
        assert _fmt("Authorization: Basic dXNlcjpwYXNz") == "Authorization: Basic [SECRET_REDACTED]"

    @pytest.mark.parametrize(
        "secret",
        [
            # ``secrets.token_hex(32)``: 64 hex, the length of a sha256.
            "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b0b822cd15d6c15b0f00a08aa",
            # ``secrets.token_hex(16)``: 32 hex.
            "5402728d4d6effa74f362117597e0b8f",
            # A signed S3 URL's ``X-Amz-Signature`` is 64 hex too, and a failed fetch prints the url.
            "X-Amz-Signature=9f86d081884c7d659a2feaa0c55ad015a3bf4f1b0b822cd15d6c15b0f00a08aa",
            # Nine leading digits read as a Spanish mobile: the phone pattern must not bite them off
            # and leave the other 23 characters of a 32-hex token in clear, under the token length.
            "612345678abcdef0123456789abcdef0",
            # 40 hex is a git sha — and a GitHub OAuth token of the classic kind.
            "e83c5163316f89bfbde7d9ab23ca2e25604af290",
        ],
    )
    def test_a_hex_credential_is_not_waved_through_as_a_hash(self, secret):
        label = secret.rpartition("=")[0]
        expected = f"{label}=[TOKEN_REDACTED]" if label else "[TOKEN_REDACTED]"
        assert _fmt(f"hub token {secret} rejected") == f"hub token {expected} rejected"

    def test_every_hex_credential_we_mint_is_redacted(self):
        """Pinned on the generator, not on a sample: every draw of the two lengths we mint."""
        import secrets

        for nbytes in (16, 32):
            for _ in range(200):
                raw = secrets.token_hex(nbytes)
                assert _fmt(f"hub token {raw} rejected") == "hub token [TOKEN_REDACTED] rejected"

    @pytest.mark.parametrize(
        "secret",
        [
            "-rQRPNk73m3vhxkIZK6KNJab",
            "frQRPNk73m3vhxkIZK6KNJa-",
            "-rQRPNk73m3vhxkIZK6KNJa-",
            "_rQRPNk73m3vhxkIZK6KNJa_",
        ],
    )
    def test_a_24_character_token_at_a_dash_or_underscore_edge_is_redacted(self, secret):
        assert len(secret) == 24
        out = _fmt(f"token {secret} used")
        assert out == "token [TOKEN_REDACTED] used"

    def test_no_urlsafe_token_of_24_characters_slips_by_its_edges(self):
        """``secrets.token_urlsafe(18)`` is 24 characters; ~3 % of draws start or end in ``-``."""
        rng = random.Random(2445)
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        edged = 0
        for _ in range(5000):
            raw = "".join(rng.choice(alphabet) for _ in range(24))
            edged += raw[0] in "-_" or raw[-1] in "-_"
            out = _fmt(f"token {raw} used")
            if out != "token [TOKEN_REDACTED] used":
                # An all-lowercase draw shaped like an event key is the rule of saas#2140, not a leak
                # of this one; the draw can only land there if it carries no digit or capital.
                assert GDPRSafeFormatter._EVENT_KEY.match(raw), raw
        assert edged > 100, "the sample did not exercise the edges"

    @pytest.mark.parametrize(
        "line",
        [
            # The word, without a value: authentication failures must stay readable.
            "password reset requested for hub=3f2a",
            "Authorization header missing",
            "[hub-machine] invalid token for hub=3f2a",
            # A key that merely contains the word is not the credential.
            '{"token_type": "bearer", "expires_in": 3600}',
            "password_changed_at=2026-10-01",
            # Truncated hashes, the way the code prints them.
            "[WEBHOOK] Received for sales - commit: e83c5163",
            "Created version record: sales 1.2.0 (sha256: 9f86d081884c...)",
            # A separator line is not a token.
            "-------------------------------- migrations --------------------------------",
            "________________________________",
        ],
    )
    def test_ordinary_lines_still_read_as_written(self, line):
        assert _fmt(line) == line


class TestAPasswordInsideAConnectionUrl:
    """saas#2458 — ``scheme://user:password@host`` walked through whole.

    No key named the value (the key was ``dsn``) and it was under the token length, so neither
    rule saw it; and with a dotted host the e-mail rule ate password AND host into one label. Only
    the password goes: user, host, port and database are what tell you which connection failed.
    """

    @pytest.mark.parametrize(
        ("line", "expected"),
        [
            (
                "dsn=postgres://erplora:S3cr3tPassw0rd@lb-db:5432/saas",
                "dsn=postgres://erplora:[SECRET_REDACTED]@lb-db:5432/saas",
            ),
            # A dotted host must not be read as the domain of an e-mail with the password as its user.
            (
                "connect failed: postgresql+asyncpg://hub_0123456789ab:S3cr3t@lb-db.erplora.internal:5432/hub_0123456789ab",
                "connect failed: postgresql+asyncpg://hub_0123456789ab:[SECRET_REDACTED]@lb-db.erplora.internal:5432/hub_0123456789ab",
            ),
            # Valkey/Redis carries a password with no user.
            ("broker=redis://:S3cr3t@valkey:6379/0", "broker=redis://:[SECRET_REDACTED]@valkey:6379/0"),
            ("amqp://guest:guest@rabbit:5672/", "amqp://guest:[SECRET_REDACTED]@rabbit:5672/"),
            # A git remote with a token in it, the way a failed clone prints it.
            (
                "clone https://x-access-token:ghs_16C7e42F292c69@github.com/ERPlora/saas.git failed",
                "clone https://x-access-token:[SECRET_REDACTED]@github.com/ERPlora/saas.git failed",
            ),
            # Unencoded ``@`` and ``:`` in the password: it ends at the last ``@`` before the host.
            ("postgres://u:p@ss:w0rd@lb-db/saas", "postgres://u:[SECRET_REDACTED]@lb-db/saas"),
            # The user ends at the first ``:``; a ``:`` inside the password goes with the password.
            ("postgres://u:pa:ss@lb-db/saas", "postgres://u:[SECRET_REDACTED]@lb-db/saas"),
            # An ``@`` further on — in the path, or after a space — is not the end of a password:
            # a port stays a port and the address is the e-mail rule's.
            (
                "GET https://erplora.com:443/api/v1/users/ana@example.com/",
                "GET https://erplora.com:443/api/v1/users/[EMAIL_REDACTED]/",
            ),
            ("GET https://erplora.com:443 by ana@example.com", "GET https://erplora.com:443 by [EMAIL_REDACTED]"),
            # Quoted, as repr() and JSON print it: the quote closes the url.
            (
                "{'url': 'redis://:S3cr3t@valkey:6379/0', 'owner': 'a@b.com'}",
                "{'url': 'redis://:[SECRET_REDACTED]@valkey:6379/0', 'owner': '[EMAIL_REDACTED]'}",
            ),
            (
                '{"url":"redis://:S3cr3t@valkey:6379","owner":"a@b.com"}',
                '{"url":"redis://:[SECRET_REDACTED]@valkey:6379","owner":"[EMAIL_REDACTED]"}',
            ),
        ],
    )
    def test_only_the_password_goes(self, line, expected):
        assert _fmt(line) == expected

    @pytest.mark.parametrize(
        "line",
        [
            # No credentials, or a user without a password: nothing to hide.
            "dsn=postgres://erplora@lb-db:5432/saas",
            "dsn=postgresql://erplora:@lb-db:5432/saas",
            "broker=redis://valkey:6379/0",
            # A port is not a password, with or without a path or a query behind it.
            "GET https://pre.erplora.com:443/api/v1/hubs/?page=2 -> 200",
            "upstream http://10.10.1.6:8000 timed out",
            # Authentication failures keep every word of the evidence.
            "connection to postgresql://hub_0123456789ab@10.10.1.6:5432/hub_0123456789ab failed: "
            'FATAL: password authentication failed for user "hub_0123456789ab"',
            "[hub-machine] invalid token for hub=3f2a from https://erplora.com/api/v1/hub/heartbeat/",
        ],
    )
    def test_a_url_without_a_password_reads_as_written(self, line):
        assert _fmt(line) == line

    def test_a_failed_login_keeps_its_evidence_and_loses_the_password(self):
        line = (
            "connection to postgresql://hub_0123456789ab:S3cr3t@10.10.1.6:5432/hub_0123456789ab failed: "
            'FATAL: password authentication failed for user "hub_0123456789ab"'
        )
        assert _fmt(line) == line.replace("S3cr3t", "[SECRET_REDACTED]")


class TestALongLineIsCleanedInLinearTime:
    """saas#2472: every log line goes through the formatter, so no rule may be quadratic on it.

    The e-mail rule started a scan at every word boundary of a long run of address characters
    and walked to its end looking for an ``@``: 140k characters without one held the process for
    6-12 s. The JWT rule did the same from every ``eyJ`` of a run without dots. Probed on the
    WHOLE formatter, so a new rule that is quadratic falls here too, not only the two that were.
    """

    @pytest.mark.parametrize(
        "line",
        [
            "a.b-c+d" * 20_000,
            "a." * 70_000,
            "a." * 70_000 + "@",
            "x@" + "y." * 70_000,
            "1." * 70_000,
            "a-" * 70_000,
            "ana@x.com%" * 14_000,
            "eyJ-" * 35_000,
            "eyJa." * 28_000,
            "eyJa.b" * 23_000,
            "://a:" * 20_000,
            "x://:" + "@" * 100_000,
            "x://u:" + "a" * 100_000,
            "x://" + "a:" * 50_000,
            "a.b-c+d" * 20_000 + "://",
            "://" * 50_000,
        ],
        ids=[
            "address-run-without-at",
            "dotted-run",
            "dotted-run-then-at",
            "domain-without-tld",
            "dotted-digits",
            "dashed-run",
            "many-addresses",
            "jwt-starts-without-dots",
            "jwt-starts-one-dot",
            "jwt-starts-two-dots-apart",
            "repeated-userinfo",
            "only-at-signs",
            "unterminated-password",
            "colons",
            "scheme-run",
            "bare-separators",
        ],
    )
    def test_a_hostile_line_does_not_stall_the_logger(self, line):
        import time

        started = time.perf_counter()
        _fmt(line)
        assert time.perf_counter() - started < 1.0


class TestAddressesAndJwtsAreRedactedExactlyAsBefore:
    """saas#2472 changed how the two rules scan, not what they cover: the same lines come out.

    Compared against the rules as they were, on lines built from the pieces where their edges
    live — word and non-word characters, ``@``, dots, ``eyJ``, and a non-ASCII letter (``ñ``),
    which is a word character to ``\\b`` but not an address character.
    """

    _EMAIL_BEFORE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
    _JWT_BEFORE = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
    #: No digit 6-9, no ``:``/``/``, no key word and no capital pair, so no other rule can fire
    #: and the formatter's output is the work of these two alone.
    _WORD = ["ana", "x", "1", "_", "-", "ñ", "eyJ", ""]
    _EDGE = ["", "", " ", ".", "-", "%", "+", "@", "ñ", "_"]

    def _before(self, line: str) -> str:
        return self._EMAIL_BEFORE.sub("[EMAIL_REDACTED]", self._JWT_BEFORE.sub("[TOKEN_REDACTED]", line))

    def _part(self, rng: random.Random, most: int) -> str:
        return "".join(rng.choice(self._WORD + self._EDGE) for _ in range(rng.randint(0, most)))

    def _chunk(self, rng: random.Random) -> str:
        """Something shaped like an address or a JWT, often one character off being one."""
        if rng.random() < 0.5:
            tld = rng.choice([".com", ".es", ".c", ".", ".1", ""])
            return self._part(rng, 3) + "@" + self._part(rng, 2) + tld + rng.choice(self._EDGE)
        dot = [".", ".", ".", "-"]
        return "eyJ" + self._part(rng, 2) + rng.choice(dot) + self._part(rng, 2) + rng.choice(dot) + self._part(rng, 2)

    def test_random_lines_come_out_as_they_did(self):
        rng = random.Random(2472)
        redacted = {"[EMAIL_REDACTED]": 0, "[TOKEN_REDACTED]": 0}
        for _ in range(10_000):
            line = "".join(self._chunk(rng) for _ in range(rng.randint(1, 3)))
            # Under the 24 of a token run, or that rule would have its say too.
            assert not re.search(r"[A-Za-z0-9_-]{24,}", line), line
            expected = self._before(line)
            assert _fmt(line) == expected, line
            for label in redacted:
                redacted[label] += label in expected
        # The comparison is only worth something if both rules actually fired on the sample.
        assert redacted["[EMAIL_REDACTED]"] > 200, redacted
        assert redacted["[TOKEN_REDACTED]"] > 100, redacted

    @pytest.mark.parametrize(
        ("line", "expected"),
        [
            # A url-encoded list: the second address starts in the middle of a run (at the ``%``,
            # the word boundary after the first one's TLD). Starting only at the start of a run
            # (the first idea in saas#2472) let it through.
            ("to=ana@x.com%2Cbob@y.com", "to=[EMAIL_REDACTED][EMAIL_REDACTED]"),
            ("ana@x.com-bob@y.com", "[EMAIL_REDACTED][EMAIL_REDACTED]"),
            # The edge is still the word boundary: a leading dot stays outside.
            ("from .ana@x.com", "from .[EMAIL_REDACTED]"),
            ("a.b-c+d" * 3 + " ana@x.com", "a.b-c+d" * 3 + " [EMAIL_REDACTED]"),
            ("ana@x.c ana@x.com", "ana@x.c [EMAIL_REDACTED]"),
            ("x-eyJa.b.c y", "x-[TOKEN_REDACTED] y"),
            ("eyJ-eyJ-eyJa.b.c y", "[TOKEN_REDACTED] y"),
            ("eyJa-eyJ.b eyJa.b.c", "eyJa-eyJ.b [TOKEN_REDACTED]"),
        ],
    )
    def test_the_edges_are_where_they_were(self, line, expected):
        assert self._before(line) == expected, "the case no longer describes the rules as they were"
        assert _fmt(line) == expected


class TestTheLogOfThisProject:
    """The formatter is the one the console handler writes with (CloudWatch Logs in production), so every line of
    every logger, tracebacks included, goes through it."""

    def test_the_console_handler_writes_through_the_redacting_formatter(self):
        from django.conf import settings

        handler = settings.LOGGING["handlers"]["console"]
        formatter = settings.LOGGING["formatters"][handler["formatter"]]
        assert formatter["()"] == "base.logging.GDPRSafeFormatter"

    def test_a_line_of_any_logger_reaches_the_console_without_the_address_nor_the_key(self):
        # The console handler the process set up from settings.LOGGING, pointed at a buffer for this line and back:
        # rebuilding the logging inside a capture would leave every later line writing to a closed stream.
        console = logging.getHandlerByName("console")
        written = io.StringIO()
        stream = console.setStream(written)
        try:
            logging.getLogger("accounts.mail").warning(
                "mail to ana@example.com failed with key erps_live_Q7cRm2ZtV9xKp4LwN8bYs3HdJ6fGa1EqU5oTi0WkBnMvCzXyPl"
            )
        finally:
            console.setStream(stream)
        err = written.getvalue()
        assert "accounts.mail" in err
        assert "mail to [EMAIL_REDACTED] failed with key [TOKEN_REDACTED]" in err
        assert "ana@example.com" not in err

    def test_a_traceback_loses_the_secret_it_carries(self):
        formatter = GDPRSafeFormatter("%(message)s")
        try:
            raise ValueError("could not connect to postgres://saas:S3cr3tPassw0rd@db:5432/saas")
        except ValueError:
            import sys

            record = logging.LogRecord("t", logging.ERROR, __file__, 1, "connect failed", None, sys.exc_info())
        out = formatter.format(record)
        assert "Traceback" in out
        assert "S3cr3tPassw0rd" not in out
        assert "postgres://saas:[SECRET_REDACTED]@db:5432/saas" in out
