from config.settings.core import DEBUG, config

# The public web of erplora.com (`public/`): Django templates for SEO, its own CSP
# (public/csp.py), crawlers, cookie consent, IndexNow and the app downloads.

# The Hub serves the apps' documentation images: the SaaS rewrites their paths
# to this base and the public CSP adds its origin to `img-src`. Only for that.
HUB_STATIC_BASE_URL = config(
    "HUB_STATIC_BASE_URL",
    default="http://hubs.localhost:8000/static/"
    if DEBUG
    else "https://hubs.erplora.com/static/",
)

# Google Analytics 4 and Microsoft Clarity, loaded only after the analytical consent and never on a
# page that shows credentials. Empty by default: production sets them, local stays out.
GA_MEASUREMENT_ID = config("GA_MEASUREMENT_ID", default="")
CLARITY_PROJECT_ID = config("CLARITY_PROJECT_ID", default="")

# django-cookie-consent (GDPR): its groups are seeded by `init_cookie_groups`.
COOKIE_CONSENT_NAME = "cookie_consent"
COOKIE_CONSENT_MAX_AGE = 60 * 60 * 24 * 365  # 1 year
COOKIE_CONSENT_SECURE = not DEBUG

# Messages of the contact form per address (django-ratelimit, over the default cache).
CONTACT_FORM_RATELIMIT = config("CONTACT_FORM_RATELIMIT", default="10/h")
# «Report a problem» of the panel per account (django-ratelimit, over the default cache).
SUPPORT_REPORT_RATELIMIT = config("SUPPORT_REPORT_RATELIMIT", default="5/h")
# The browsers' CSP reports per address (/csp-report/, base/csp_report.py).
CSP_REPORT_RATELIMIT = config("CSP_REPORT_RATELIMIT", default="60/h")

# The demo hubs (public/demo.py): one switch, and new demos per address
# (django-ratelimit, over the default cache; a browser re-entering its live demo does not count). The Hub keeps
# the cap of live demos (MAX_CONCURRENT_DEMOS) and the WAF limits /demo per IP too.
DEMO_ENABLED = config("DEMO_ENABLED", default=True, cast=bool)
DEMO_SPAWN_RATELIMIT = config("DEMO_SPAWN_RATELIMIT", default="3/h")
# With Valkey down the per-IP limits of the app cannot count, and they let requests through instead
# of refusing everyone. The ALB's WAF keeps limiting sign-in, sign-up, password, Google and the
# headless API per IP meanwhile (ERPlora/aws README.md, WAF of `stacks/shared`); the contact form has
# no WAF limit, so for that while it lasts only the app's fail-open applies.
RATELIMIT_FAIL_OPEN = True

# IndexNow pushes the public URLs to Bing (and so to ChatGPT search) the day they change. The key
# is public by design (served at `/<key>.txt`, where the search engine checks we own the domain),
# so it ships with the code; the environment may replace it. PUBLIC_HOST is the host of the URLs
# submitted: IndexNow rejects the whole batch if one URL is on another host.
INDEXNOW_KEY = config(
    "INDEXNOW_KEY", default="1e00b99c5f72af2baaba3e383f91725b"
).strip()
PUBLIC_HOST = config("PUBLIC_HOST", default="erplora.com").strip()

# The legal terms promise the exit package of a deleted hub for this many days: a written promise
# to the customer, so it is read here and never quietly lowered.
HUB_EXIT_PACKAGE_TTL_DAYS = config("HUB_EXIT_PACKAGE_TTL_DAYS", default=90, cast=int)

# The installable app (`/app/`): its installers live in a private S3 bucket on AWS (Ireland region,
# ERPlora/aws «s3_downloads.tf»), served by short presigned links; `latest/`, never a version, so a
# cached link keeps delivering the last build. Linux's AppImage is the exception: it comes from the
# latest GitHub release of `ERPlora/app` (`public.downloads.GITHUB_RELEASE_URLS`). No keys here:
# boto3 takes the ECS task's role (or the environment in development); DOWNLOADS_ENDPOINT_URL is
# only for local development (empty = AWS). The stores win when their listing exists: Microsoft
# Store by its Store ID (assigned by Microsoft), Google Play by the package (an override of
# `com.erplora.app`, never a switch to the APK) while its listing is live.
DOWNLOADS_BUCKET = config("DOWNLOADS_BUCKET", default="erplora-saas")
DOWNLOADS_REGION = config("DOWNLOADS_REGION", default="eu-west-1")
DOWNLOADS_ENDPOINT_URL = config("DOWNLOADS_ENDPOINT_URL", default="")
APP_DOWNLOAD_PREFIX = config("APP_DOWNLOAD_PREFIX", default="downloads/app/latest")
DOWNLOAD_URL_TTL = config("DOWNLOAD_URL_TTL", default=300, cast=int)  # seconds
MICROSOFT_STORE_APP_ID = config("MICROSOFT_STORE_APP_ID", default="")
GOOGLE_PLAY_APP_ID = config("GOOGLE_PLAY_APP_ID", default="")
GOOGLE_PLAY_LISTING_LIVE = config("GOOGLE_PLAY_LISTING_LIVE", default=True, cast=bool)
