from config.settings.core import BASE_DIR, DEBUG, config

# Email: locally a file per mail in .mail/ (EMAIL_FILE_PATH), where the code of every
# password sign-in is read, by a person or by an e2e (also the Hub's); in production the SES API signed
# by the task role (no static keys), or SMTP from EMAIL_* when SES_REGION is unset.
# EMAIL_BACKEND overrides the choice. Same variables and order as the Hub.

smtp_email_backend = "django.core.mail.backends.smtp.EmailBackend"
ses_email_backend = "django_ses.SESBackend"
file_email_backend = "django.core.mail.backends.filebased.EmailBackend"
if DEBUG:
    default_email_backend = file_email_backend
else:
    default_email_backend = (
        ses_email_backend if config("SES_REGION", default="") else smtp_email_backend
    )
email_backend = config("EMAIL_BACKEND", default=default_email_backend)
MAILERS = {"default": {"BACKEND": email_backend}}
if email_backend == ses_email_backend:
    AWS_SES_REGION_NAME = config("SES_REGION")
    AWS_SES_REGION_ENDPOINT = f"email.{AWS_SES_REGION_NAME}.amazonaws.com"
    # The throttle first calls ses:GetSendQuota, which the task role may not (only
    # SendEmail/SendRawEmail).
    AWS_SES_AUTO_THROTTLE = None
    # A sign-in mails its code inside the request: an SES that does not answer fails within seconds, as the SMTP mailer
    # (10 s), never boto3's minutes (60 s to connect, 60 s to read, retried). One try more.
    from botocore.config import Config as _BotoConfig

    AWS_SES_CONFIG = _BotoConfig(connect_timeout=3, read_timeout=10, retries={"total_max_attempts": 2, "mode": "standard"})
elif email_backend == smtp_email_backend:
    MAILERS["default"]["OPTIONS"] = {
        "host": config("EMAIL_HOST", default="localhost"),
        "port": config("EMAIL_PORT", default=587, cast=int),
        "username": config("EMAIL_HOST_USER", default=""),
        "password": config("EMAIL_HOST_PASSWORD", default=""),
        "use_tls": config("EMAIL_USE_TLS", default=True, cast=bool),
        "timeout": 10,
    }
elif email_backend == file_email_backend:
    # The panel's e2e names its own folder (tests/e2e/panel/project.ts); development uses .mail/.
    MAILERS["default"]["OPTIONS"] = {
        "file_path": config("EMAIL_FILE_PATH", default=str(BASE_DIR / ".mail"))
    }
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="noreply@erplora.com")
