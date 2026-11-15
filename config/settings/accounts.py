from datetime import timedelta

from django.core.exceptions import ImproperlyConfigured

from config.settings.core import DEBUG, config

# Accounts: email as the identifier, primary key UUIDv7.

AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# allauth: email + password with a code mailed at every sign-in, and Google; the authenticator app behind
# ACCOUNTS_MFA_ENABLED (below). One form in the launcher (/launch) with two tabs: «Sign in» is allauth's
# login, which never creates an account, and «Create account» is allauth's
# signup, which never signs in (an address it already holds gets a mail, not a session: enumeration
# prevention, allauth's default).

SITE_ID = 1
ACCOUNT_ADAPTER = "accounts.adapters.AccountAdapter"
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*"]
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_USER_MODEL_EMAIL_FIELD = "email"
ACCOUNT_UNIQUE_EMAIL = True
# Every account proves its mailbox before its first session: a code typed on the same screen, not a
# link that leaves for the mail app, which then signs in. An account that never proved it
# is asked for the code at its next sign-in. Google's verified addresses need no code
# (SOCIALACCOUNT_EMAIL_VERIFICATION below).
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_EMAIL_VERIFICATION_BY_CODE_ENABLED = True
# Six digits, as the second factor's codes: typed on a phone or a till.
ACCOUNT_EMAIL_VERIFICATION_BY_CODE_FORMAT = {"length": 6, "numeric": True, "dashed": False}
# «Send another code» (allauth: two more, 10 s apart): a lost mail must not strand the person there.
ACCOUNT_EMAIL_VERIFICATION_SUPPORTS_RESEND = True
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
# The second factor by email: every sign-in with a password also asks for a code
# mailed to the account (allauth's login-by-code stage, `POST …/auth/code/confirm`), typed in the app.
# Only the password: Google is a strong sign-in of its own and proves the address itself. One code,
# never two: a sign-up or an address never proven gets the verification code above, the same proof of
# the mailbox (AccountAdapter.is_login_by_code_required). allauth's defaults: 3 tries, 3 minutes.
ACCOUNT_LOGIN_BY_CODE_REQUIRED = {"password"}
ACCOUNT_LOGIN_BY_CODE_FORMAT = ACCOUNT_EMAIL_VERIFICATION_BY_CODE_FORMAT
# Not ACCOUNT_LOGIN_BY_CODE_ENABLED: it would serve `auth/code/request`, a sign-in with the mailed code
# alone (no password), and only with it does allauth resend this code. Signing in again mails a new one.
# Every limit written out (allauth lays this dict over its defaults),
# per address (`ip`: REMOTE_ADDR, the visitor public.client_ip found behind the ALB) and per account (`key`: the
# address typed), on the shared cache (Valkey):
# - `login`: 30 sign-ins a minute per address, right or wrong (allauth's);
# - `login_failed`: 5 wrong passwords in 5 minutes per address and per account; the right one gives its attempt
#   back, so the owner is never locked out by their own sign-ins;
# - `signup`: creating an account mails a code, 10 an hour per address;
# - `reset_password`: «Forgot your password?» mails a link, 10 an hour per address and 5 per account;
# - `reset_password_from_key`: the link's form, 20 a minute per address (allauth's);
# - `confirm_email`: «Send another code», one every 10 s per account (allauth's, with codes);
# - `code_attempts` (ours, accounts/bot_check.py): 10 refused codes in 5 minutes per address, mailed or of the
#   authenticator app (a right one spends nothing), on top of allauth's 3 tries per mailed code.
ACCOUNT_RATE_LIMITS = {
    "login": "30/m/ip",
    "login_failed": "5/5m/ip,5/5m/key",
    "signup": "10/h/ip",
    "reset_password": "10/h/ip,5/h/key",
    "reset_password_from_key": "20/m/ip",
    "confirm_email": "1/10s/key",
    "code_attempts": "10/5m/ip",
}
# The e2e's panel server alone (tests/e2e/panel/project.ts) raises the limits per address of the sign-in and of the
# sign-up: every spec signs in from 127.0.0.1, password and mailed code, and creates its accounts from there too; one
# spec repeated got 429 at the sign-in, and the eleventh «Create account» of a run 429 at the sign-up. The sign-ins,
# the failed passwords, the typed codes and the sign-ups per address, still a limit; each account keeps its own 5
# wrong passwords in 5 minutes, and the reset links and «Send another code» keep theirs (no spec goes past them). The
# name says «login» for history: the panel's project.ts, its test and the README name it. Its own variable, never
# DEBUG (the dev server keeps the limits). Production refuses to start with it.
E2E_RELAX_LOGIN_RATE_LIMIT = config("E2E_RELAX_LOGIN_RATE_LIMIT", default=False, cast=bool)
if E2E_RELAX_LOGIN_RATE_LIMIT and not DEBUG:
    raise ImproperlyConfigured(
        "E2E_RELAX_LOGIN_RATE_LIMIT is only for the e2e's panel server, which runs with DEBUG on."
    )
if E2E_RELAX_LOGIN_RATE_LIMIT:
    ACCOUNT_RATE_LIMITS["login"] = "1000/m/ip"
    ACCOUNT_RATE_LIMITS["login_failed"] = "1000/m/ip,5/5m/key"
    ACCOUNT_RATE_LIMITS["signup"] = "1000/m/ip"
    ACCOUNT_RATE_LIMITS["code_attempts"] = "1000/m/ip"
# A recent sign-in (allauth's reauthentication) before any change of the account's addresses or of its
# Google link through allauth.headless, as the Account page's own «Change email» asks (accounts.email.change).
ACCOUNT_REAUTHENTICATION_REQUIRED = True
# Every sign-in lasts SESSION_COOKIE_AGE: allauth.headless takes no `remember`, and without this a session
# would end when the browser closes.
ACCOUNT_SESSION_REMEMBER = True
# The sign-in lives in the Vue launcher, the entrance (hubs/frontend/pages/LaunchPage.vue with
# accounts/frontend/components/SignInForm.vue), where Django sends a visitor without a session (`?next=`).
# Signing out is allauth.headless's `DELETE …/auth/session`; the page then loads this one.
LOGIN_URL = "/launch"
# The Vue launcher (hubs/frontend/pages/LaunchPage.vue).
LOGIN_REDIRECT_URL = "/launch"
# Absolute links allauth builds (Google's redirect_uri): behind the load balancer the request
# arrives as http, and Google only accepts the https callback registered with it.
ACCOUNT_DEFAULT_HTTP_PROTOCOL = "http" if DEBUG else "https"
# Where an account holder writes when a mail says something they did not do.
SUPPORT_EMAIL = config("SUPPORT_EMAIL", default="support@erplora.com")

# «Continue with Google» (allauth.socialaccount). Credentials
# come from the environment only (no `SocialApp` row). Local development may go without them: the
# button is hidden and `check` says so (accounts.I001). Production refuses to start without them.
# Redirect URIs registered with Google: `<origin>/auth/google/callback/` (README.md).

GOOGLE_OAUTH_CLIENT_ID = (
    config("GOOGLE_OAUTH_CLIENT_ID", default="")
    if DEBUG
    else config("GOOGLE_OAUTH_CLIENT_ID")
)
GOOGLE_OAUTH_CLIENT_SECRET = (
    config("GOOGLE_OAUTH_CLIENT_SECRET", default="")
    if DEBUG
    else config("GOOGLE_OAUTH_CLIENT_SECRET")
)
GOOGLE_OAUTH_ENABLED = bool(GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET)
# Where Google's code is exchanged: Google, unless a development server moves it (the e2e's double,
# tests/e2e/panel/accounts-google.spec.ts). Never in production: allauth believes what that address answers
# without checking its signature, because it is its own call to Google.
GOOGLE_OAUTH_TOKEN_URL = config("GOOGLE_OAUTH_TOKEN_URL", default="") if DEBUG else ""

# reCAPTCHA Enterprise, score-based and invisible (no checkbox, no puzzle), on every public form: the sign-in,
# the sign-up, «Forgot your password?» and its link, the mailed codes, the authenticator app's code, the contact
# form and the demo (live.recaptcha, accounts/bot_check.py, public/). OFF by default: the WAF on the ALB filters the
# suspicious traffic
# and the attempt limits (ACCOUNT_RATE_LIMITS, `code_attempts`, the contact form's and the demo's) stop the brute
# force. Off, no form is checked, the pages load nothing of Google and the CSP names none of its sources.
# RECAPTCHA_ENABLED=True switches it back on (production and development alike) and then requires both keys: the
# site key is public (the page loads Google's enterprise.js with it), the API key asks Google for each token's
# assessment. Below RECAPTCHA_MIN_SCORE (Google's 0.5 by default) a form is refused, as is a token of another form,
# an invalid one and Google unreachable (fail closed). RECAPTCHA_ENDPOINT moves the assessments elsewhere (the e2e's
# double, tests/e2e/recaptcha-double.ts).
RECAPTCHA_SITE_KEY = config("RECAPTCHA_SITE_KEY", default="")
RECAPTCHA_API_KEY = config("RECAPTCHA_API_KEY", default="")
RECAPTCHA_PROJECT = config("RECAPTCHA_PROJECT", default="erplora")
RECAPTCHA_ENABLED = config("RECAPTCHA_ENABLED", default=False, cast=bool)
if RECAPTCHA_ENABLED:
    for _name, _value in (("RECAPTCHA_SITE_KEY", RECAPTCHA_SITE_KEY), ("RECAPTCHA_API_KEY", RECAPTCHA_API_KEY)):
        if not _value:
            raise ImproperlyConfigured(
                f"{_name} is required with RECAPTCHA_ENABLED=True: reCAPTCHA checks every public form."
            )
try:
    RECAPTCHA_MIN_SCORE = float(config("RECAPTCHA_MIN_SCORE", default="0.5"))
except ValueError:
    RECAPTCHA_MIN_SCORE = -1.0
if not 0 <= RECAPTCHA_MIN_SCORE <= 1:
    raise ImproperlyConfigured("RECAPTCHA_MIN_SCORE must be a number from 0 to 1.")
RECAPTCHA_ENDPOINT = config("RECAPTCHA_ENDPOINT", default="") or None

# Refuses allauth's «connect» process and tells the owner when Google gets linked; an
# unknown Google email creates its account (SOCIALACCOUNT_AUTO_SIGNUP).
SOCIALACCOUNT_ADAPTER = "accounts.adapters.SocialAccountAdapter"
SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "APP": {
            "client_id": GOOGLE_OAUTH_CLIENT_ID,
            "secret": GOOGLE_OAUTH_CLIENT_SECRET,
            "key": "",
        },
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online"},
        "OAUTH_PKCE_ENABLED": True,
        # No "VERIFIED_EMAIL": Google's own `email_verified` claim decides whether the address is
        # proven. Forcing True would only matter when Google says the address is NOT verified, the one
        # case in which signing in by email must not happen.
        **({"ACCESS_TOKEN_URL": GOOGLE_OAUTH_TOKEN_URL} if GOOGLE_OAUTH_TOKEN_URL else {}),
    }
}
# Google already proved the address it vouches for (`email_verified`): no code on top. An address it
# does not vouch for creates no account (SocialAccountAdapter.is_open_for_signup).
SOCIALACCOUNT_EMAIL_VERIFICATION = "none"
# An unknown Google email creates the account and signs in, with no form in between.
SOCIALACCOUNT_AUTO_SIGNUP = True
# A Google that proves an account's email signs in to it and is linked to it:
# allauth only does it for an address Google verified, the guard against account takeover.
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True
# Sign-in only: no Google API is called afterwards.
SOCIALACCOUNT_STORE_TOKENS = False

# Second factor (allauth.mfa): an authenticator app (TOTP) and recovery codes, and «Trust this
# browser for 14 days»; no passkeys. Off by default: with ACCOUNTS_MFA_ENABLED=False no login asks for
# a code and the 2FA endpoints answer 404 (accounts/mfa.py); turned on, an account with an authenticator app is
# asked for its code after the first factor and the staff's jump to the Hub admin (`hub-admin`) needs it
# (accounts/README.md, «Segundo factor»).

ACCOUNTS_MFA_ENABLED = config("ACCOUNTS_MFA_ENABLED", default=False, cast=bool)
MFA_SUPPORTED_TYPES = ["totp", "recovery_codes"]
MFA_TOTP_ISSUER = "ERPlora"
# Accept ±1 period (30 s) of clock drift between the phone and the server.
MFA_TOTP_TOLERANCE = 1
MFA_PASSKEY_LOGIN_ENABLED = False
MFA_ADAPTER = "accounts.mfa.MFAAdapter"
# «Trust this browser»: after the app's code the login asks once; a trusted browser
# skips the app's code (never the mailed one) for 14 days. allauth's own signed cookie, bound to the password and the
# authenticators: a new one of either ends every trust. Only for erplora.com, never the businesses' subdomains, even
# if the session cookie one day has a domain.
MFA_TRUST_ENABLED = True
MFA_TRUST_COOKIE_AGE = timedelta(days=14)
MFA_TRUST_COOKIE_DOMAIN = None
# Ending a session (Account → Security, or allauth.headless `auth/sessions`) also asks the account's
# businesses to end theirs (accounts.signals.sessions_ended).
USERSESSIONS_ADAPTER = "accounts.session_tracking.UserSessionsAdapter"

# allauth.headless: the API of the Ionic Vue account pages, browser client only
# (same-origin session cookie + Django's CSRF), mounted at /_allauth/. Headless only: allauth serves no
# template page; every screen of the sign-in is a page of the SPA (accounts/frontend/routes.ts).
HEADLESS_ONLY = True
HEADLESS_CLIENTS = ("browser",)
# Where the links allauth mails lead, by URL name: pages of the SPA. The «no account here» mail of a
# password reset invites to sign up, which the launcher's sign-in does. Not
# account_confirm_email: the address is proven by a code typed on /verify-email, and allauth
# builds no link with codes on. Not socialaccount_login_error: the SocialAccountAdapter sends every
# failure of Google's round trip to the Vue page /login/error before allauth would read it.
HEADLESS_FRONTEND_URLS = {
    "account_reset_password": "/password/reset",
    "account_reset_password_from_key": "/password/reset/key/{key}",
    # The launcher's «Create account» tab: allauth's mail to an address with no account links there.
    "account_signup": "/launch?tab=signup",
}
# openapi.yaml/.json of the headless API in development; not its HTML page (Redoc from a CDN).
HEADLESS_SERVE_SPECIFICATION = DEBUG
HEADLESS_SPECIFICATION_TEMPLATE_NAME = None
