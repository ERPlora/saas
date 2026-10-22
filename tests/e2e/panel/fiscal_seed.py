"""The rows the fiscal review spec opens (fiscal-review.spec.ts: FISCAL-F03 and FISCAL-F05).

``uv run python tests/e2e/panel/fiscal_seed.py seed|clear`` from the SaaS, against the run's database (development
only: known passwords, refused without ``DEBUG``). ``seed`` starts from ``clear``, so a run always finds the same
rows; ``clear`` removes every account ``e2e-fiscal-*@example.com`` and every business one of them owns.

- ``e2e-fiscal-reviewer``: a member of ERPlora's staff who may decide on authorisations
  (``fiscal.change_representationgrant``, which the review page and the services ask) and change ERPlora's stamp
  as representative (``fiscal.change_representativestamp``, FISCAL-F06). ``clear`` removes the stamp one of these
  accounts uploaded.
- ``e2e-fiscal-owner``: owner of Bar Fiscal, reading Spanish. The business and its people are written with the ORM
  (nothing is pushed to the Hub); its signed authorisation goes through ``fiscal.representation.submit``, the
  operation the Hub's upload runs, so it mails the review desk and the owner after its COMMIT, as in production.

Prints the id of the authorisation it filed.
"""

import base64
import os
import sys
from datetime import timedelta
from pathlib import Path

SAAS_DIR = Path(__file__).resolve().parents[3]
PASSWORD = os.environ.get("QA_PANEL_PASSWORD", "e2e-panel")
DOMAIN = "@example.com"
PREFIX = "e2e-fiscal-"


def pdf(text: str) -> bytes:
    """A valid one-page PDF that says ``text``, so the review page shows a document (the upload only checks the
    magic number; a viewer wants the whole file)."""
    stream = f"BT /F1 24 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = b"%PDF-1.4\n", []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return out


def setup_django() -> None:
    sys.path.insert(0, str(SAAS_DIR))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def clear() -> None:
    from django.contrib.auth import get_user_model
    from django.db.models import Q

    from accounts.models import HubMembership
    from fiscal.models import RepresentativeStamp
    from hubs.models import BillingProfile, Hub, HubMember

    users = get_user_model().objects.filter(
        email__startswith=PREFIX, email__endswith=DOMAIN
    )
    # Before the accounts: their deletion would leave the stamp without its uploader (SET_NULL).
    RepresentativeStamp.objects.filter(uploaded_by__in=users).delete()
    owned = HubMember.objects.filter(
        user__in=users, role=HubMember.Role.OWNER
    ).values_list("hub_id", flat=True)
    hubs = Hub.objects.filter(Q(slug__startswith=PREFIX) | Q(pk__in=list(owned)))
    slugs = list(hubs.values_list("slug", flat=True))
    profiles = list(hubs.values_list("billing_profile_id", flat=True))
    hubs.delete()
    BillingProfile.objects.filter(Q(pk__in=profiles) | Q(owner__in=users)).delete()
    HubMembership.objects.filter(Q(hub_slug__in=slugs) | Q(user__in=users)).delete()
    users.delete()


def main(action: str) -> None:
    setup_django()
    from django.conf import settings
    from django.db import transaction

    if not settings.DEBUG:
        sys.exit("fiscal_seed.py only runs with DEBUG=True")
    with transaction.atomic():
        clear()
        hub_id = _business() if action == "seed" else None
    if hub_id is not None:
        # Its own transaction, as the Hub's upload: the mails leave once it commits.
        print(_submit(hub_id))
    else:
        print(f"{action}: fiscal e2e accounts")


def _account(local: str, language: str, **extra):
    from allauth.account.models import EmailAddress
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.create_user(
        email=f"{PREFIX}{local}{DOMAIN}", password=PASSWORD, language=language, **extra
    )
    # Proven address: every account proves it before its first session (the code a sign-up mails).
    EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
    return user


def _business():
    from django.contrib.auth.models import Permission
    from django.utils import timezone

    from accounts.models import HubMembership
    from hubs.models import BillingProfile, Hub, HubMember, Plan, Subscription

    now = timezone.now()
    reviewer = _account("reviewer", "en", first_name="Rita", is_staff=True)
    reviewer.user_permissions.add(
        *Permission.objects.filter(
            content_type__app_label="fiscal",
            codename__in=[
                "view_representationgrant",
                "change_representationgrant",
                "view_representativestamp",
                "change_representativestamp",
            ],
        )
    )
    owner = _account("owner", "es", first_name="Olga")
    profile = BillingProfile.objects.create(
        owner=owner, billing_email=owner.email, billing_country="ES"
    )
    hub = Hub.objects.create(
        slug=f"{PREFIX}bar",
        name="Bar Fiscal",
        country="ES",
        timezone="Europe/Madrid",
        language="es",
        billing_profile=profile,
        status=Hub.Status.ACTIVE,
        ready_at=now - timedelta(days=30),
    )
    Subscription.objects.create(
        hub=hub,
        plan=Plan.objects.get(slug="free"),
        status=Subscription.Status.ACTIVE,
        current_period_start=now - timedelta(days=10),
    )
    HubMember.objects.create(
        hub=hub,
        user=owner,
        role=HubMember.Role.OWNER,
        joined_at=now - timedelta(days=30),
        accepted_at=now - timedelta(days=30),
    )
    HubMembership.objects.create(user=owner, hub_slug=hub.slug, role=HubMember.Role.OWNER)
    return hub.pk


def _submit(hub_id) -> str:
    from fiscal import services
    from fiscal.schemas import RepresentationSubmitIn
    from hubs.services import system_ctx_for

    def encoded(text: str) -> str:
        return base64.b64encode(pdf(text)).decode()

    result = services.representation_submit(
        system_ctx_for(hub_id),
        RepresentationSubmitIn(
            hub_id=hub_id,
            taxpayer_tax_id="12345678Z",
            taxpayer_name="Olga Fiscal",
            signer_tax_id="12345678Z",
            signer_name="Olga Fiscal",
            signer_document_type="dni",
            documents={
                "signed_model": encoded("Signed model (e2e)"),
                "id_copy": encoded("Identity document (e2e)"),
            },
        ),
    )
    from fiscal.models import RepresentationGrant

    return str(
        RepresentationGrant.objects.get(hub_id=hub_id, version=result.version).pk
    )


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "seed")
