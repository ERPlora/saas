from config.tests.production_settings import PRODUCTION_ENV, _run, development, production, task_settings


# The hubs' fiscal documents: encrypted with a Fernet key, required in production like
# INTERNAL_SHARED_SECRET (a deploy without it must not start and store documents it cannot read later).


def test_production_refuses_to_start_without_the_fiscal_documents_key():
    env = {key: value for key, value in PRODUCTION_ENV.items() if key != "FISCAL_DOCUMENTS_KEY"}

    result = _run("import config.settings", env)

    assert result.returncode != 0
    assert "UndefinedValueError" in result.stderr
    assert "FISCAL_DOCUMENTS_KEY" in result.stderr


def test_production_takes_the_fiscal_documents_key_from_the_environment():
    assert production("s.FISCAL_DOCUMENTS_KEY") == PRODUCTION_ENV["FISCAL_DOCUMENTS_KEY"]


def test_development_has_a_local_fernet_key_for_the_fiscal_documents():
    from cryptography.fernet import Fernet

    key = development("s.FISCAL_DOCUMENTS_KEY")

    assert Fernet(key.encode()).decrypt(Fernet(key.encode()).encrypt(b"ok")) == b"ok"


def test_every_view_keeps_django_s_upload_ceiling():
    """Django's 2.5 MB for every view (allauth, ``/api``, Stripe's webhook): an anonymous body is never buffered
    beyond it. The four documents of an authorisation have their own ceiling, in their view only
    (``fiscal.internal.MAX_BODY_BYTES``)."""
    expression = "getattr(s, 'DATA_UPLOAD_MAX_MEMORY_SIZE', 'django default')"
    assert production(expression) == "django default"
    assert development(expression) == "django default"


def test_the_seal_slots_and_the_region_come_from_the_environment():
    """The two .p12 slots of the fiscal seal (erplora/prod/fiscal/seal-{current,next}), base64 and
    password each, and the region CloudWatch is called in (report_seal_expiry)."""
    assert task_settings(
        "(s.AWS_REGION, s.FISCAL_SEAL_CURRENT_P12_BASE64, s.FISCAL_SEAL_CURRENT_PASSWORD,"
        " s.FISCAL_SEAL_NEXT_P12_BASE64, s.FISCAL_SEAL_NEXT_PASSWORD)",
        "saas-cron",
        AWS_REGION="eu-west-3",
        FISCAL_SEAL_CURRENT_P12_BASE64="Y3VycmVudA==",
        FISCAL_SEAL_CURRENT_PASSWORD="current-password",
        FISCAL_SEAL_NEXT_P12_BASE64="bmV4dA==",
        FISCAL_SEAL_NEXT_PASSWORD="next-password",
    ) == ("eu-west-3", "Y3VycmVudA==", "current-password", "bmV4dA==", "next-password")


def test_development_has_empty_seal_slots_and_the_platform_region():
    assert development(
        "(s.AWS_REGION, s.FISCAL_SEAL_CURRENT_P12_BASE64, s.FISCAL_SEAL_NEXT_P12_BASE64)"
    ) == ("eu-west-1", "", "")
