"""ACCOUNTS-F36 · The audit trail of the fiscal documentation (django-auditlog; PLAN-SAAS §1.1: «en los modelos de
cuenta, cobro y fiscal»).

Ported from ERPlora/saas ``apps/dashboard/fiscal/auditlog.py`` (#970): who sent, approved, returned or withdrew a
business's signed authorisation (Anexo I) and who replaced ERPlora's stamp, with only the logged fields serialized
(#957). Changed: the old models were the certificate and its password (``VerifactuConfig``) and each record sent to the
AEAT; here the documents of an authorisation and the stamp are encrypted files that are never copied into the trail
(``fiscal.crypto`` keeps them out of the clear, and a copy would outlive the row), nor is ``updated_at``.
"""

from datetime import timedelta
from io import StringIO

import pytest
from auditlog.models import LogEntry
from auditlog.registry import auditlog
from django.apps import apps
from django.core.management import call_command
from django.utils import timezone

from fiscal import crypto
from fiscal.models import RepresentationGrant, RepresentativeStamp
from fiscal.tests.conftest import make_grant, stamp_png

pytestmark = pytest.mark.django_db

DOCUMENTS = {"signed_model", "id_copy", "signature_sample", "representation_proof"}


def _entries_for(instance):
    return LogEntry.objects.get_for_object(instance)


def _fields_written(entry) -> set[str]:
    return set(entry.changes_dict) | set(entry.serialized_data["fields"])


def test_every_fiscal_model_is_audited_with_only_its_logged_fields():
    fiscal_models = set(apps.get_app_config("fiscal").get_models())

    assert fiscal_models == {RepresentationGrant, RepresentativeStamp}
    assert all(auditlog.contains(model) for model in fiscal_models)
    assert all(auditlog.get_serialize_options(model)["serialize_auditlog_fields_only"] for model in fiscal_models)


def test_an_authorisation_and_its_review_are_logged_without_its_documents(business, reviewer):
    grant = make_grant(business, signature_sample=crypto.encrypt(b"sample"), representation_proof=crypto.encrypt(b"proof"))

    grant.status, grant.reviewed_by, grant.reviewed_at = "approved", reviewer, timezone.now()
    grant.save()

    review = _entries_for(grant).get(action=LogEntry.Action.UPDATE)
    assert review.changes_dict["status"] == ["submitted", "approved"]
    assert review.changes_dict["reviewed_by"][1] == str(reviewer.pk)
    for entry in _entries_for(grant):
        assert not (DOCUMENTS | {"updated_at"}) & _fields_written(entry)


def test_the_representatives_stamp_is_logged_without_its_image(reviewer):
    stamp = RepresentativeStamp.objects.create(
        image=crypto.encrypt(stamp_png()), size=1234, uploaded_at=timezone.now(), uploaded_by=reviewer
    )

    entry = _entries_for(stamp).get()

    assert entry.changes_dict["uploaded_by"][1] == str(reviewer.pk)
    assert "image" not in _fields_written(entry)


def test_cleanup_old_logs_prunes_the_fiscal_entries_too(business, other_business):
    """The same table as the account's: ``cleanup_old_logs`` keeps 90 days of these as well (ACCOUNTS-F37)."""
    old, recent = make_grant(business), make_grant(other_business)
    _entries_for(old).update(timestamp=timezone.now() - timedelta(days=91))

    call_command("cleanup_old_logs", stdout=StringIO())

    assert (_entries_for(old).exists(), _entries_for(recent).exists()) == (False, True)
