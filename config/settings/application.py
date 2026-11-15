from config.settings.core import BASE_DIR

# Application definition

INSTALLED_APPS = [
    # Before daphne: its runserver (daphne + Vite, `--novite` skips Vite) must win.
    "live",
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "django.contrib.sitemaps",
    # The HNSW index migration assistant/0004 creates and 0005 removes (pgvector): its index classes need it.
    "django.contrib.postgres",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "allauth.headless",
    # Always installed, so its table always exists: ACCOUNTS_MFA_ENABLED decides whether it is used.
    "allauth.mfa",
    # The account's active sessions (Account → Security): one row per signed-in browser.
    "allauth.usersessions",
    "ninja",
    "base",
    "accounts",
    # Who changed an account, its access to a business, its keys and its sessions.
    "auditlog",
    # The app catalog: before hubs and public, which read it.
    "apps",
    "hubs",
    # The EU VAT engine and Stripe: after hubs, whose payer it reads.
    "billing",
    # The documentation a business sends so ERPlora files its VeriFactu records: after
    # hubs, whose businesses it reads and whose snapshot carries its outcome.
    "fiscal",
    # The fiscal gateway: presents the Hub's VeriFactu envelopes to the AEAT.
    "fiscal_gateway",
    # WhatsApp, erplora.com's side: after hubs, whose businesses it serves
    # and whose snapshot carries its channel.
    "whatsapp",
    # The AI gateway: the providers ERPlora pays, their keys and
    # models, which model answers and the clients of each provider's API (assistant/README.md).
    "assistant",
    "public",
    # After `public`: its templates override the package's (public/templates/cookie_consent/).
    "cookie_consent",
]

MIDDLEWARE = [
    # First: answers /healthz before the Host is validated (the ALB probes each task by its IP).
    "base.health.HealthCheckMiddleware",
    # Then: a cut of the database waits and repeats the whole request, when it may (live.database_cut; Django turns an
    # exception into a response at every layer, so only the outermost sees it all).
    "live.database_cut.DatabaseCutMiddleware",
    "django.middleware.security.SecurityMiddleware",
    # The visitor's address behind the ALB in REMOTE_ADDR, before anything reads it.
    "public.client_ip.ClientIpMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
    # After Django's: the public web's own policy, set before Django's builds the header.
    "public.csp.PublicCSPMiddleware",
    # And the admin's: the panel's policy without Trusted Types, which Django's admin cannot run under.
    "base.csp.AdminCSPMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    # A mail allauth cannot send (SES in its sandbox) answers a handled 503, not a 500 (saas#391).
    "accounts.mail_outage.MailOutageMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # On the panel, a signed-in account speaks its own language (User.language), not the cookie's.
    "base.language.AccountLanguageMiddleware",
    # The maintenance mode of «Site settings» in the admin: every visitor gets the 503 page but the staff, the health
    # checks, the admin and its sign-in, /internal and the webhooks.
    "base.maintenance.MaintenanceModeMiddleware",
    # With ACCOUNTS_MFA_ENABLED off, the 2FA endpoints answer 404 (accounts/mfa.py).
    "accounts.mfa.MFAFlagMiddleware",
    # The code tries per address and reCAPTCHA before allauth.headless's public doors, after the CSRF check
    # (accounts/bot_check.py).
    "accounts.bot_check.BotCheckMiddleware",
    # API 404/405 that never reach a route (unknown path, wrong method) answer the JSON envelope.
    "live.api_errors.ApiErrorEnvelopeMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    # Records each signed-in session's address, browser and last use (allauth.usersessions), at most once
    # every few minutes: Account → Security → Active sessions.
    "accounts.session_tracking.SessionActivityMiddleware",
    # The actor and the address of each audit log entry (after AuthenticationMiddleware and
    # public.client_ip).
    "accounts.auditlog.AuditActorMiddleware",
    # Deletes the cookies of a group that was declined or never accepted (django-cookie-consent),
    # skipping the requests that carry no cookie (public/cookies.py).
    "public.cookies.CleanCookiesMiddleware",
    # `X-Robots-Tag: noindex` on everything that is not the public web (public/crawlers.py).
    "public.crawlers.NoIndexPrivatePathsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.i18n",
                "django.template.context_processors.csp",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                # The shell's colour mode (`theme` cookie) for the template pages.
                "base.context_processors.theme",
                "public.context_processors.public_site",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
