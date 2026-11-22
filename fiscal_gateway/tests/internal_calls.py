"""Calls to ``/internal/verifactu/<door>`` signed as the Hub signs them, and what the tests read back."""

import json
import time

from accounts.signing import sign, signed_headers
from fiscal_gateway import internal
from fiscal_gateway.tests.conftest import (
    HUB,
    PASSWORD,
    PLATFORM,
    SECRET,
    b64,
    fixture,
)

PATH = "/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP"
PRE_SEAL = f"https://prewww10.aeat.es{PATH}"
PRE_HOLDER = f"https://prewww1.aeat.es{PATH}"
SENT = fixture("rotation_a_sent_2026-09-22.xml")
ANSWER = fixture("rotation_a_2026-09-22.xml")
ISSUER = "B27593136"
#: A customer's NIF, and the envelope of the Hub naming it.
CUSTOMER = "B12345674"
CUSTOMER_SENT = SENT.replace(ISSUER, CUSTOMER)


def payload(**changes):
    """The platform's hub presenting ERPlora's own records through its seal, unless ``changes`` say."""
    body = {
        "hub": PLATFORM,
        "nif": ISSUER,
        "environment": "testing",
        "route": "erplora",
        "envelope": SENT,
    }
    body.update(changes)
    return body


def own(p12, password=PASSWORD, **changes):
    """The business ``HUB`` presenting with its own certificate."""
    return payload(
        **{
            "hub": HUB,
            "route": "own",
            "certificate": {"p12_base64": b64(p12), "password": password},
            **changes,
        }
    )


def call(client, door, body=None, *, secret=SECRET, signed=True, v2=False, raw=None):
    data = raw if raw is not None else json.dumps(body).encode()
    path = f"/internal/verifactu/{door}"
    timestamp = int(time.time())
    headers = {}
    if signed and v2:
        headers = signed_headers("POST", path, data, timestamp, secret)
    elif signed:
        headers = {
            "X-Erplora-Timestamp": str(timestamp),
            "X-Erplora-Signature": sign(data, timestamp, secret),
        }
    return client.post(path, data, content_type="application/json", headers=headers)


def error_of(response):
    return response.status_code, response.json()["error"]["code"]


def log_text(caplog) -> str:
    """Everything the gateway logged: the messages and their arguments."""
    return caplog.text + "".join(str(record.args) for record in caplog.records)


def assert_certificate_kept_out(caplog, response, p12: bytes, password: str) -> None:
    """Something was logged, and neither the logs nor ``response`` carry ``p12``, its password or a private key."""
    assert caplog.records
    logged = log_text(caplog)
    for secret in (password, b64(p12)[:60], b64(p12)[-60:], "PRIVATE KEY"):
        assert secret not in logged
        assert secret not in response.content.decode()


def probe_body(body):
    return {k: v for k, v in body.items() if k != "envelope"}


def _free_slots() -> int:
    taken = 0
    while internal.SLOTS.acquire(blocking=False):
        taken += 1
    for _ in range(taken):
        internal.SLOTS.release()
    return taken
