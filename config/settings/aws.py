from django.core.exceptions import ImproperlyConfigured

from config.settings.core import config

# AWS: the region of the platform, Ireland (ECS sets AWS_REGION in every
# task), where `report_seal_expiry` publishes to CloudWatch with the task role (no static keys).
AWS_REGION = config("AWS_REGION", default="eu-west-1")

# A business's own domain for its public website (`aws` README, «Dominio propio de un negocio»). Off unless it is on,
# as in pre and in development: nothing asks for a certificate, nothing looks at a
# domain, and the operations say it is not available. On, the listener that takes the certificates and the name a
# customer's CNAME points at ({hub_id}: one for each business, for good) are required. The most certificates that
# listener holds for customers (`hubs.custom_domain.request` and the hourly check stop asking at it).
CUSTOM_DOMAINS_ENABLED = config("CUSTOM_DOMAINS_ENABLED", default=False, cast=bool)
CUSTOM_DOMAINS_LISTENER_ARN = config("CUSTOM_DOMAINS_LISTENER_ARN", default="").strip()
CUSTOM_DOMAINS_TARGET_TEMPLATE = config("CUSTOM_DOMAINS_TARGET_TEMPLATE", default="").strip()
CUSTOM_DOMAINS_MAX_CERTIFICATES = config("CUSTOM_DOMAINS_MAX_CERTIFICATES", default=24, cast=int)
if CUSTOM_DOMAINS_ENABLED:
    if not CUSTOM_DOMAINS_LISTENER_ARN:
        raise ImproperlyConfigured("CUSTOM_DOMAINS_LISTENER_ARN is required with CUSTOM_DOMAINS_ENABLED=True.")
    if "{hub_id}" not in CUSTOM_DOMAINS_TARGET_TEMPLATE:
        raise ImproperlyConfigured("CUSTOM_DOMAINS_TARGET_TEMPLATE needs {hub_id} with CUSTOM_DOMAINS_ENABLED=True.")
