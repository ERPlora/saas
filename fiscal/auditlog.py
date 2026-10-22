"""The audit trail of the fiscal documentation (django-auditlog; ACCOUNTS-F36, PLAN-SAAS §1.1). Registered from
``FiscalConfig.ready``.

Who sent, approved, returned or withdrew a business's signed authorisation (Anexo I) and who replaced ERPlora's stamp.
Never logged: the documents of an authorisation and the stamp, encrypted files (``fiscal.crypto``) a copy in the trail
would keep after the row, nor ``updated_at``.
"""

from accounts.auditlog import audit
from fiscal.models import RepresentationGrant, RepresentativeStamp


def register() -> None:
    audit(
        RepresentationGrant,
        exclude=["signed_model", "id_copy", "signature_sample", "representation_proof", "updated_at"],
    )
    audit(RepresentativeStamp, exclude=["image"])
