import ast

from config.tests.production_settings import AWS_ENV, PRODUCTION_ENV, SAAS_NEXT, _run, development, production


# Email: a file per mail in .mail/ in development (the sign-in code is read there, also by
# the Hub's e2e); in production the SES API signed by the task role when ECS passes SES_REGION, SMTP
# configured by the environment otherwise, or any backend EMAIL_BACKEND names. Same variables and
# order as the Hub.

SMTP = "django.core.mail.backends.smtp.EmailBackend"
SES = "django_ses.SESBackend"
CONSOLE = "django.core.mail.backends.console.EmailBackend"
FILE = "django.core.mail.backends.filebased.EmailBackend"
#: Where development writes every mail: the code of every password sign-in is read there.
DEV_MAIL_DIR = str(SAAS_NEXT / ".mail")


def test_development_writes_every_mail_to_a_file_in_saas_next_mail():
    assert development("s.MAILERS['default']") == {"BACKEND": FILE, "OPTIONS": {"file_path": DEV_MAIL_DIR}}
    # Even with production's SES region in the environment, DEBUG never sends real mail.
    assert development("s.MAILERS['default']", SES_REGION="eu-west-1") == {
        "BACKEND": FILE,
        "OPTIONS": {"file_path": DEV_MAIL_DIR},
    }


def test_development_takes_the_backend_and_the_folder_from_the_environment(tmp_path):
    """The panel's e2e names its own folder; any other backend (the console) is still one variable away."""
    assert development("s.MAILERS['default']", EMAIL_FILE_PATH=str(tmp_path)) == {
        "BACKEND": FILE,
        "OPTIONS": {"file_path": str(tmp_path)},
    }
    assert development("s.MAILERS['default']", EMAIL_BACKEND=CONSOLE) == {"BACKEND": CONSOLE}


def test_the_development_mail_folder_is_never_versioned():
    ignored = (SAAS_NEXT / ".gitignore").read_text().splitlines()

    assert ".mail/" in ignored


def test_production_mail_goes_through_the_ses_api_with_the_task_role():
    """ECS passes SES_REGION and the task role may ses:SendRawEmail: no SMTP, no static keys."""
    mailer, region, endpoint, throttle, static_keys = production(
        "(s.MAILERS['default'], s.AWS_SES_REGION_NAME, s.AWS_SES_REGION_ENDPOINT,"
        " s.AWS_SES_AUTO_THROTTLE,"
        " sorted({'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SES_ACCESS_KEY_ID'} & set(dir(s))))",
        **AWS_ENV,
        EMAIL_HOST="smtp.example.com",
    )

    assert mailer == {"BACKEND": SES}
    assert (region, endpoint) == ("eu-west-1", "email.eu-west-1.amazonaws.com")
    # The throttle would first call ses:GetSendQuota, which the task role may not.
    assert throttle is None
    assert static_keys == []


def test_the_ses_backend_builds_from_the_settings_so_its_library_is_installed():
    """Built the way Django 6.1 builds a mailer; building neither connects nor signs."""
    result = _run(
        "import django\ndjango.setup()\nfrom django.core.mail import mailers\n"
        "b = mailers.default\n"
        "print(repr((f'{type(b).__module__}.{type(b).__name__}', b._region_name, b._endpoint_url,"
        " b._throttle, b._access_key_id, b._access_key, b._session_token)))",
        {**PRODUCTION_ENV, **AWS_ENV, "DJANGO_SETTINGS_MODULE": "config.settings"},
    )

    assert result.returncode == 0, result.stderr
    assert ast.literal_eval(result.stdout.strip()) == (
        SES,
        "eu-west-1",
        "https://email.eu-west-1.amazonaws.com",
        None,
        # No keys of its own: boto3 signs with the task role.
        None,
        None,
        None,
    )


def test_a_mail_to_ses_waits_seconds_never_minutes():
    """A sign-in mails its code inside the request; with boto3's defaults (60 s to connect, 60 s to read, retried) an
    SES that does not answer would hold the person there for minutes. As the SMTP mailer (10 s): 3 s to connect,
    10 s to read and one try more, so a failure reaches the page (and the log) within half a minute."""
    result = _run(
        "import django\ndjango.setup()\nfrom django.core.mail import mailers\n"
        "c = mailers.default._config\n"
        "print(repr((c.connect_timeout, c.read_timeout, c.retries)))",
        {**PRODUCTION_ENV, **AWS_ENV, "DJANGO_SETTINGS_MODULE": "config.settings"},
    )

    assert result.returncode == 0, result.stderr
    assert ast.literal_eval(result.stdout.strip()) == (3, 10, {"total_max_attempts": 2, "mode": "standard"})


def test_a_ses_backend_named_by_the_environment_needs_its_region():
    result = _run("import config.settings", {**PRODUCTION_ENV, "EMAIL_BACKEND": SES})

    assert result.returncode != 0
    assert "UndefinedValueError" in result.stderr
    assert "SES_REGION" in result.stderr


def test_production_sends_mail_by_smtp_from_noreply():
    mailer, sender = production("(s.MAILERS['default'], s.DEFAULT_FROM_EMAIL)")

    assert mailer == {
        "BACKEND": SMTP,
        "OPTIONS": {
            "host": "localhost",
            "port": 587,
            "username": "",
            "password": "",
            "use_tls": True,
            "timeout": 10,
        },
    }
    assert sender == "noreply@erplora.com"


def test_the_smtp_server_and_the_sender_come_from_the_environment():
    mailer, sender = production(
        "(s.MAILERS['default'], s.DEFAULT_FROM_EMAIL)",
        EMAIL_HOST="email-smtp.eu-west-1.amazonaws.com",
        EMAIL_PORT="2587",
        EMAIL_HOST_USER="smtp-user",
        EMAIL_HOST_PASSWORD="smtp-password",
        EMAIL_USE_TLS="False",
        DEFAULT_FROM_EMAIL="hello@erplora.com",
    )

    assert mailer["OPTIONS"] == {
        "host": "email-smtp.eu-west-1.amazonaws.com",
        "port": 2587,
        "username": "smtp-user",
        "password": "smtp-password",
        "use_tls": False,
        "timeout": 10,
    }
    assert sender == "hello@erplora.com"


def test_email_backend_names_another_backend():
    assert production(
        "s.MAILERS['default']",
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    ) == {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}


def test_a_file_backend_writes_where_email_file_path_says(tmp_path):
    """The panel's e2e (tests/e2e/panel/project.ts) reads what the SaaS mails from files: Django's
    MAILERS gives the file backend its folder in OPTIONS, never through EMAIL_FILE_PATH itself."""
    folder = str(tmp_path / "mail")
    assert development(
        "s.MAILERS['default']", EMAIL_BACKEND=FILE, EMAIL_FILE_PATH=folder
    ) == {
        "BACKEND": FILE,
        "OPTIONS": {"file_path": folder},
    }

    result = _run(
        "import django\ndjango.setup()\nfrom django.core.mail import send_mail\n"
        "send_mail('Subject', 'Body', None, ['someone@example.com'])",
        {
            "DEBUG": "True",
            "EMAIL_BACKEND": FILE,
            "EMAIL_FILE_PATH": folder,
            "DJANGO_SETTINGS_MODULE": "config.settings",
        },
    )

    assert result.returncode == 0, result.stderr
    (written,) = (tmp_path / "mail").iterdir()
    assert "To: someone@example.com" in written.read_text()


def test_the_production_smtp_mailer_can_be_built():
    """Without SES_REGION, Django's MAILERS accepts the SMTP options (no connection until it sends)."""
    result = _run(
        "import django\ndjango.setup()\nfrom django.core.mail import mailers\n"
        "print(type(mailers.default).__module__)",
        {**PRODUCTION_ENV, "DJANGO_SETTINGS_MODULE": "config.settings"},
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "django.core.mail.backends.smtp"
