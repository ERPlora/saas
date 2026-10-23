"""The log keeps the event and loses the personal data and the secrets (ACCOUNTS-G14, ACCOUNTS-G76; GDPR art. 5.1.c).

Ported from ERPlora/saas ``apps/core/logging.py`` (origin/develop c5ca8cae8). Every line of every logger is written by
the console handler (CloudWatch Logs in production) through :class:`GDPRSafeFormatter`, tracebacks included
(``settings.LOGGING``): an address, a phone, a NIF, an IBAN, a card, a JWT, a password, a key or a token that someone
logs by mistake reaches the log as a label (``[EMAIL_REDACTED]``…), never as written.

The rule is: **redact values, never drop records** (#969). The old ``SensitiveDataFilter`` dropped every record that
merely said "token", "password" or "secret", the shape of every authentication-failure line ("invalid token for
hub=…", "Invalid webhook secret"): it prevented no leak, because those lines never carried the value, and deleted the
only evidence of a brute-force run or a stolen credential. It is not ported.
"""

import logging
import re


class GDPRSafeFormatter(logging.Formatter):
    """Log formatter that masks personal data in the rendered message.

    Patterns are ordered on purpose: the longest, most structured identifiers go
    first, so an IBAN is redacted as an IBAN rather than chewed up half-way
    through by the phone pattern.
    """

    # Structured identifiers first — they contain digit runs the looser patterns
    # would otherwise bite into.
    IBAN_PATTERN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")
    # JWT: three base64url segments. Matched whole so payload and signature go
    # with the header instead of surviving it.
    # This rule and the e-mail one match their first run even when the rest is missing, and the
    # match without ``rest``/``domain`` is given back as written (``_keep_unless``): otherwise
    # each later ``eyJ``/word boundary of the same run rescans it to the end and fails the same
    # way, quadratic on a long line (saas#2472). Same edges as a plain pattern: it still starts
    # at ``\b``, and a failed run could not have held a match anyway — its end is the same.
    JWT_PATTERN = re.compile(r"\beyJ[A-Za-z0-9_-]+(?P<rest>\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b)?")
    CC_PATTERN = re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b")
    EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+(?P<domain>@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b)?")
    # NIF (8 digits + letter), NIE (X/Y/Z + 7 digits + letter), CIF (letter + 8).
    NIF_PATTERN = re.compile(r"\b(?:[XYZ]\d{7}[A-HJ-NP-TV-Z]|\d{8}[A-HJ-NP-TV-Z]|[A-HJNP-SUVW]\d{8})\b")
    # Spanish phone: nine digits starting 6/7/8/9, optional +34 and separators.
    # Digit lookarounds rather than `\b`: in `+34612345678` there is no word
    # boundary between the prefix and the number, so `\b` would never match it.
    PHONE_PATTERN = re.compile(r"(?<![\d\w])(?:\+34[\s.-]?)?[6789]\d{2}[\s.-]?\d{3}[\s.-]?\d{3}(?!\d)")
    # The password inside a connection url, ``scheme://user:password@host`` (saas#2458): no key
    # names it (the key is ``dsn`` or ``url``) and it is often under the token length. Only the
    # password goes — user, host, port and database say which connection failed. Anchored on
    # ``://`` with no scheme run in front, and neither part crosses a ``/``, so each url is
    # scanned once (linear on hostile lines). The password does not end at ``#``/``?`` the way a
    # url parser would: our plan-role passwords are minted with them; it ends at the last ``@``
    # before the host, or at a quote, so a printed dict keeps its next field.
    URL_PASSWORD_PATTERN = re.compile(r"://(?P<user>[^\s:@/'\"<>]*):(?P<password>[^\s/'\"<>]+)@")
    # A secret assigned inside a message: `password=…`, `token: …`, `api_key "…"`, and the same
    # under a quoted key as JSON and ``repr`` print it (`{"password": "…"}`, `{'password': ['…']}`)
    # or under a field name that ends in one of the words (`cloud_api_token`, `client_secret`).
    # A quoted value goes whole, spaces included; an auth scheme (`Bearer`, `Basic`) stays and the
    # credential after it goes, however short (saas#2445).
    ASSIGNED_SECRET_PATTERN = re.compile(
        r"\b(?:[a-z0-9]+_)*(?:password|passwd|secret_key|secret|api_key|apikey|token|authorization|bearer)\b"
        r"['\"]?\s*[:=]\s*\[?\s*['\"]?(?:(?:bearer|basic|token)\s+)?"
        # A value another rule already redacted (``x-access-token:[SECRET_REDACTED]@host``) is left
        # alone, or this one would take the host with it.
        r"(?!\[?SECRET_REDACTED\])(?P<value>(?<=\")[^\"]+(?=\")|(?<=')[^']+(?=')|[^\s'\",;]{4,})",
        re.IGNORECASE,
    )
    # Opaque credentials: base64url / Fernet-shaped runs. Deliberately AFTER the
    # structured ones, and 24+ so ordinary ids and slugs survive. Bounded by the
    # run's own alphabet, not ``\b``: ``-`` is not a word character, so a token
    # starting or ending in one lost it to the boundary and fell to 23 (saas#2445).
    TOKEN_PATTERN = re.compile(r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{24,}(?![A-Za-z0-9_-])")

    #: A run of only ``-``/``_`` is a separator line, not a token. There is no hex keep-list any
    #: more: a sha256 and ``secrets.token_hex(32)`` (the old SaaS's ``Hub.cloud_api_token``) are the same 64
    #: characters, as are a signed S3 url's ``X-Amz-Signature`` and the custom-domain token's 32.
    #: The code prints hashes truncated (``sha[:8]``, ``sha256[:12]``), under the 24 that redact.
    _SEPARATOR = re.compile(r"^[-_]+$")
    #: Our own event keys — ``period_ended_while_row_says_active`` — are what the alerts grep
    #: for, and they are lowercase words joined by underscores (saas#2140). A credential is not:
    #: the Hub's (``erpk_<env>_`` + base62), ours (``erps_live_`` + base62), Stripe's and any base64url/hex run carry digits or
    #: capitals, or a blob longer than any word. Case-sensitive on purpose, and no bare
    #: "snake_case" rule: that would let ``erpk_live_…`` through.
    #: Known limit: the rule reads shape, not meaning. Anything else spelled as lowercase words
    #: joined by underscores — a passphrase, a person's name in a file name — survives as well.
    #: So those are covered where they enter, not by shape (saas#2445): a passphrase goes by its
    #: key (``ASSIGNED_SECRET_PATTERN``), and the assistant's document reader logs the mime type
    #: and the failure, never the file name. A closed list of event keys was the alternative, and
    #: it fails the way saas#2140 did: a new key nobody registers is silently eaten and its
    #: alert never fires.
    _EVENT_KEY = re.compile(r"^[a-z]{1,20}(?:_[a-z]{1,20})*$")
    #: An id as Python prints a UUID: every key of this project is a ``uuid.uuid7()`` and no credential is UUID-shaped
    #: (no ``UUIDField`` but primary keys), so ``user=<id>`` stays for the team to follow (ACCOUNTS-F40). Only this
    #: exact form: with underscores, capitals or anything more it is a blob like any other.
    _ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

    def format(self, record):
        return self._sanitize(super().format(record))

    def _sanitize(self, message: str) -> str:
        # First: with a dotted host the e-mail rule reads ``password@host.tld`` as an address and
        # takes the host with it.
        message = self.URL_PASSWORD_PATTERN.sub(self._redact_url_password, message)
        message = self.JWT_PATTERN.sub(self._keep_unless("rest", "[TOKEN_REDACTED]"), message)
        message = self.IBAN_PATTERN.sub("[IBAN_REDACTED]", message)
        message = self.CC_PATTERN.sub("[CC_REDACTED]", message)
        message = self.EMAIL_PATTERN.sub(self._keep_unless("domain", "[EMAIL_REDACTED]"), message)
        message = self.ASSIGNED_SECRET_PATTERN.sub(self._redact_assigned, message)
        # Tokens before the phone pattern: its digit lookarounds let it bite the first nine
        # digits off a hex token (``612345678a…``) and leave the rest in clear (saas#2445).
        message = self.TOKEN_PATTERN.sub(self._redact_token, message)
        message = self.NIF_PATTERN.sub("[ID_REDACTED]", message)
        message = self.PHONE_PATTERN.sub("[PHONE_REDACTED]", message)
        return message

    @staticmethod
    def _keep_unless(group: str, label: str):
        return lambda match: label if match.group(group) is not None else match.group(0)

    @staticmethod
    def _redact_url_password(match: re.Match) -> str:
        return f"://{match.group('user')}:[SECRET_REDACTED]@"

    @staticmethod
    def _redact_assigned(match: re.Match) -> str:
        # Only the value goes: the key, the quotes and the scheme still say what the line was.
        start, end = match.span("value")
        whole = match.group(0)
        return whole[: start - match.start()] + "[SECRET_REDACTED]" + whole[end - match.start() :]

    def _redact_token(self, match: re.Match) -> str:
        value = match.group(0)
        if self._SEPARATOR.match(value) or self._EVENT_KEY.match(value) or self._ID.match(value):
            return value
        return "[TOKEN_REDACTED]"
