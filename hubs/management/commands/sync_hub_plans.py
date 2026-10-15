"""Seed of the hub plans: ``python manage.py sync_hub_plans [--update]``.

Ported from ERPlora/saas ``hubs/subscriptions/management/commands/sync_hub_plans.py``
(origin/develop, production catalogue of 2026-06-13). It runs in the ``saas-migrate`` task on every
deploy, so by default it only creates the plans missing by ``slug`` and leaves the existing ones as
staff left them in the admin («N created, M existing»). ``--update`` puts every field of every plan
back to these values («N created, M updated»). Idempotent; one short transaction per plan, so it is
safe next to the running web.

Catalogue (Ioan, 2026-10-15: three plans on sale at sign-up, dedicated infrastructure by contact, and the
upgrade-only tiers kept):

- ``free``: permanent Free plan (0 €, no card, ADR-0154): 1 hub, 1 device, 3 users, no trial. Never
  synced to Stripe.
- ``starter`` / ``standard``: the paid plans sold on the web, with a 15-day trial (ADR-0154). The
  trial is never a ``features`` line: cards paint it from ``trial_period_days`` (saas#2424).
- ``payment-test``: ``internal_only`` plan to exercise the billing chain end to end (saas#1052).

- ``pro`` / ``enterprise`` / ``max``: ``upgrade_only``, bought from the Store as an upgrade of a paying
  business, never at sign-up. Kept as they were (Ioan, 2026-10-15: not retired): the Store offers them
  only to a business Stripe already bills and the checkout refuses them to a Free one
  (``billing.queries.offered_plans``, 409 ``billing.plan_upgrade_only``; audit 2 S-03, 2026-10-14). The
  public web does not list them: ``/pricing/`` sells the three plans a visitor signs up for and, above
  them, dedicated infrastructure from 400 € a month, agreed by contact (``public/pricing.py``).

Visibility: ``Plan.objects.public()`` (active and not ``internal_only``) is what the panel reads;
``/pricing/`` lists of it only the plans a visitor can sign up for; ``internal_only`` = never shown.

Changed from the original: no container sizing nor suspension price (a plan sizes no container,
PLAN-SAAS §1); the
database limits follow round 9 (PLAN §14.2): Free 1 transaction at a time and 5 s, paid 3 and
15 s; since 2026-10-15 (Ioan) each plan up doubles the resources of the one below, so Standard has
twice Starter's (``STANDARD_DB_LIMITS``), and the cards say it in words («twice the resources»), never
as a number.

Messages a month (Ioan, 2026-10-15; PLAN-SAAS §3.6): each plan includes a number of requests to the AI
assistant (one request of the user = one message) and of WhatsApp messages, Free 30 / 30, Starter 300 / 150
(ADR-0474) and Standard twice Starter, 600 / 300; ``payment-test`` reads as Starter. 0 = none. No pack nor
overage: more messages, a plan up. The figures keep at least ``MIN_MARGIN_PERCENT`` of the net monthly price
of every paid plan when its customer uses up both quotas, at ``ASSISTANT_COST_PER_MESSAGE`` and
``WHATSAPP_COST_PER_MESSAGE`` (guarded by ``hubs/tests/test_sync_hub_plans.py``); the cards paint them from the
fields, never as a ``features`` line. Migration ``hubs/0012`` gives them to the rows already in production.

What the commercial copy may say (saas#1760; guarded by ``hubs/tests/test_sync_hub_plans.py``):
the billing unit is the HUB, called what the panel calls it, a business (audit 2 S-12); no infrastructure specs; support is sold as channel and priority,
never as a clock; one recovery window for the whole cluster, the 14 days Aurora keeps
(``backup_retention_period``, ``aws-next/stacks/prod/aurora.tf``), in one sentence with the managed
database; no uptime SLA percentage; no technology names (PostgreSQL…), only what the customer gets:
where their data lives (Amazon Web Services, in Europe, on the cloud line) and that the database is
replicated, in plain words.
"""

from decimal import Decimal

from django.core.management.base import BaseCommand

from hubs.models import Plan

FREE_DB_LIMITS = {"max_db_connections": 1, "statement_timeout_seconds": 5}
#: The full tier (Starter; PLAN §14.2). Each plan up doubles it (Ioan, 2026-10-15): Standard has twice Starter's.
PAID_DB_LIMITS = {"max_db_connections": Plan.PAID_BASE_DB_CONNECTIONS, "statement_timeout_seconds": 15}
STANDARD_DB_LIMITS = {"max_db_connections": 2 * Plan.PAID_BASE_DB_CONNECTIONS, "statement_timeout_seconds": 15}

#: What one message costs us at most, net (ADR-0474, saas#1952): the model's tokens of one assistant request, and
#: Meta's dearest billable WhatsApp message (marketing, Spain).
ASSISTANT_COST_PER_MESSAGE = Decimal("0.02")
WHATSAPP_COST_PER_MESSAGE = Decimal("0.0509")
#: The share of a paid plan's net monthly price left when its customer uses up both quotas (Ioan's condition:
#: never pay the model provider or Meta more than half of what the plan charges).
MIN_MARGIN_PERCENT = 50

MANAGED_DATABASE_EN = (
    "Managed database, replicated across several European data centres, with continuous backups and "
    "point-in-time recovery for 14 days"
)
MANAGED_DATABASE_ES = (
    "Base de datos gestionada, replicada en varios centros de datos europeos, con copias de seguridad "
    "continuas y recuperación a cualquier momento de los últimos 14 días"
)

PLANS = [
    {
        "slug": "free",
        "name_en": "Free",
        "name_es": "Gratis",
        "description_en": "Start selling today. No credit card, no server, no maintenance.",
        "description_es": "Empieza a vender hoy. Sin tarjeta, sin servidor, sin mantenimiento.",
        "features_en": [
            "1 device",
            "3 users",
            "Basic database throughput, sized for one device",
            "No credit card required",
            "All free apps included",
            "Fully managed cloud on Amazon Web Services, in Europe, with automatic scaling",
            MANAGED_DATABASE_EN,
            "Encrypted data and automatic SSL certificate",
            ".erplora.com subdomain",
            "Community support",
        ],
        "features_es": [
            "1 dispositivo",
            "3 usuarios",
            "Capacidad de base de datos básica, a la medida de un dispositivo",
            "Sin tarjeta de crédito",
            "Todas las apps gratuitas incluidas",
            "Cloud gestionado en Amazon Web Services, en Europa, con autoescalado",
            MANAGED_DATABASE_ES,
            "Datos cifrados y certificado SSL automático",
            "Subdominio .erplora.com",
            "Soporte de la comunidad",
        ],
        "featured_label_en": "",
        "featured_label_es": "",
        "price_monthly": Decimal("0"),
        "price_annual": Decimal("0"),
        "is_active": True,
        "upgrade_only": False,
        "internal_only": False,
        "trial_period_days": 0,
        "display_order": 10,
        "max_hubs_per_org": 1,
        **FREE_DB_LIMITS,
        "max_devices": 1,
        # The number this card has always promised ("3 local users"), held to it (saas#2022).
        "max_users": 3,
        "assistant_messages_per_month": 30,
        "whatsapp_messages_per_month": 30,
        "included_level": "free",
        "support_level": "community",
        "includes_custom_domain": False,
    },
    {
        "slug": "starter",
        "name_en": "Starter",
        "name_es": "Starter",
        "description_en": "Your whole business in the cloud: nothing to install, nothing to maintain, always available.",
        "description_es": "Todo tu negocio en la nube: nada que instalar, nada que mantener, siempre disponible.",
        "features_en": [
            "Priced per business — every location, device and user included",
            "Unlimited devices — sell from several at once",
            "Unlimited users",
            "Full database throughput, for several devices at once",
            "All apps included, free and premium",
            "Access from any device, always up to date",
            "Fully managed cloud on Amazon Web Services, in Europe, with automatic scaling",
            MANAGED_DATABASE_EN,
            "Encrypted data and automatic SSL certificate",
            ".erplora.com subdomain",
            "Email support (business hours)",
        ],
        "features_es": [
            "Precio por negocio — con todos sus locales, dispositivos y usuarios",
            "Dispositivos ilimitados: vende desde varios a la vez",
            "Usuarios ilimitados",
            "Capacidad de base de datos completa, para varios dispositivos a la vez",
            "Todas las apps incluidas, gratuitas y premium",
            "Acceso desde cualquier dispositivo, siempre actualizado",
            "Cloud gestionado en Amazon Web Services, en Europa, con autoescalado",
            MANAGED_DATABASE_ES,
            "Datos cifrados y certificado SSL automático",
            "Subdominio .erplora.com",
            "Soporte por email (horario laboral)",
        ],
        "featured_label_en": "",
        "featured_label_es": "",
        "price_monthly": Decimal("29.99"),
        "price_annual": Decimal("299.90"),  # 10 × monthly = 2 months free (ADR-0006)
        "is_active": True,
        "upgrade_only": False,
        "internal_only": False,
        "trial_period_days": 15,
        "display_order": 30,
        "max_hubs_per_org": 0,
        **PAID_DB_LIMITS,
        "max_devices": 0,
        "max_users": 0,
        "assistant_messages_per_month": 300,
        "whatsapp_messages_per_month": 150,
        "included_level": "basic",
        "support_level": "email",
        "includes_custom_domain": False,
    },
    {
        "slug": "standard",
        "name_en": "Standard",
        "name_es": "Standard",
        "description_en": "For growing businesses: your own domain, twice the resources and priority support.",
        "description_es": "Para negocios en crecimiento: dominio propio, el doble de recursos y soporte prioritario.",
        "features_en": [
            "Everything in Starter",
            "Priced per business — every location, device and user included",
            "Twice the database throughput of Starter, for busy counters and several locations",
            "Custom domain (erp.yourbusiness.com)",
            "More capacity as your business grows, automatically",
            "Priority email support (business hours)",
        ],
        "features_es": [
            "Todo lo del plan Starter",
            "Precio por negocio — con todos sus locales, dispositivos y usuarios",
            "El doble de capacidad de base de datos que Starter, para mostradores con mucho movimiento y varios locales",
            "Dominio propio (erp.tunegocio.com)",
            "Más capacidad a medida que crece tu negocio, automáticamente",
            "Soporte por email prioritario (horario laboral)",
        ],
        "featured_label_en": "Recommended",
        "featured_label_es": "Recomendado",
        "price_monthly": Decimal("54.99"),
        "price_annual": Decimal("549.90"),
        "is_active": True,
        "upgrade_only": False,
        "internal_only": False,
        "trial_period_days": 15,
        "display_order": 40,
        "max_hubs_per_org": 0,
        **STANDARD_DB_LIMITS,
        "max_devices": 0,
        "max_users": 0,
        # Twice Starter, as every resource of the plan (Ioan, 2026-10-15).
        "assistant_messages_per_month": 600,
        "whatsapp_messages_per_month": 300,
        "included_level": "basic",
        "support_level": "priority_email",
        "includes_custom_domain": True,
    },
    {
        "slug": "pro",
        "name_en": "Pro",
        "name_es": "Pro",
        "description_en": "High performance on isolated infrastructure, with a full API for your integrations.",
        "description_es": "Alto rendimiento en infraestructura aislada, con API completa para tus integraciones.",
        "features_en": [
            "Everything in Standard",
            # No "Full API with no usage limits" (saas#1956): the limiter has no plan axis.
            "Isolated infrastructure",
            "Priority email support (business hours)",
        ],
        "features_es": [
            "Todo lo del plan Standard",
            "Infraestructura aislada",
            "Soporte por email prioritario (horario laboral)",
        ],
        "featured_label_en": "",
        "featured_label_es": "",
        "price_monthly": Decimal("109.99"),
        "price_annual": Decimal("1099.90"),
        "is_active": True,
        "upgrade_only": True,
        "internal_only": False,
        "trial_period_days": 0,
        "display_order": 50,
        "max_hubs_per_org": 0,
        **PAID_DB_LIMITS,
        "max_devices": 0,
        "max_users": 0,
        # The old stack's level pro (ADR-0474); enterprise and max, its level enterprise.
        "assistant_messages_per_month": 1000,
        "whatsapp_messages_per_month": 500,
        "included_level": "pro",
        "support_level": "priority_email",
        "includes_custom_domain": True,
    },
    {
        "slug": "enterprise",
        "name_en": "Enterprise",
        "name_es": "Enterprise",
        "description_en": "Dedicated infrastructure with autoscaling, disaster recovery and contract-backed support.",
        "description_es": (
            "Infraestructura dedicada con autoescalado, recuperación ante desastres y soporte acordado en contrato."
        ),
        "features_en": [
            "Everything in Pro",
            "Automatic container autoscaling",
            "Disaster recovery (PITR)",
            "Advanced monitoring",
            "Support channels and escalation agreed in contract",
        ],
        "features_es": [
            "Todo lo del plan Pro",
            "Autoescalado automático de contenedores",
            "Recuperación ante desastres (PITR)",
            "Monitoreo avanzado",
            "Canales de soporte y escalado acordados en contrato",
        ],
        "featured_label_en": "",
        "featured_label_es": "",
        "price_monthly": Decimal("209.99"),
        "price_annual": Decimal("2099.90"),
        "is_active": True,
        "upgrade_only": True,
        "internal_only": False,
        "trial_period_days": 0,
        "display_order": 60,
        "max_hubs_per_org": 0,
        **PAID_DB_LIMITS,
        "max_devices": 0,
        "max_users": 0,
        "assistant_messages_per_month": 3000,
        "whatsapp_messages_per_month": 800,
        "included_level": "enterprise",
        "support_level": "contract",
        "includes_custom_domain": True,
    },
    {
        "slug": "max",
        "name_en": "Max",
        "name_es": "Max",
        "description_en": "Maximum single-node performance, for the most demanding businesses.",
        "description_es": "Máximo rendimiento de un solo nodo, para los negocios más exigentes.",
        "features_en": [
            "Everything in Enterprise",
            "─────────────────────",
            "Custom integrations",
            "Named technical contact agreed in contract",
        ],
        "features_es": [
            "Todo lo del plan Enterprise",
            "─────────────────────",
            "Integraciones a medida",
            "Responsable técnico acordado en contrato",
        ],
        "featured_label_en": "",
        "featured_label_es": "",
        "price_monthly": Decimal("419.99"),
        "price_annual": Decimal("4199.90"),
        "is_active": True,
        "upgrade_only": True,
        "internal_only": False,
        "trial_period_days": 0,
        "display_order": 70,
        "max_hubs_per_org": 0,
        **PAID_DB_LIMITS,
        "max_devices": 0,
        "max_users": 0,
        "assistant_messages_per_month": 3000,
        "whatsapp_messages_per_month": 800,
        "included_level": "enterprise",
        "support_level": "contract",
        "includes_custom_domain": True,
    },
    {
        # saas#1052: a REAL subscription (charged through Stripe) with no trial, so a real invoice,
        # its AEAT record and its QR can be seen without waiting two weeks. ``internal_only`` hides
        # it from every public door and only staff may buy it. 1.00 € net → 1.21 € with Spanish VAT.
        "slug": "payment-test",
        "name_en": "Payment Test (internal)",
        "name_es": "Prueba de pago (interno)",
        "description_en": "Internal plan for end-to-end billing verification. Not for sale.",
        "description_es": "Plan interno para verificar la facturación de punta a punta. No está a la venta.",
        "features_en": ["Internal use only"],
        "features_es": ["Solo uso interno"],
        "featured_label_en": "",
        "featured_label_es": "",
        "price_monthly": Decimal("1.00"),
        "price_annual": Decimal("0"),
        "is_active": True,
        "upgrade_only": False,
        "internal_only": True,
        "trial_period_days": 0,  # the reason the plan exists
        "display_order": 999,
        "max_hubs_per_org": 0,
        **PAID_DB_LIMITS,
        "max_devices": 0,
        "max_users": 0,
        "assistant_messages_per_month": 300,
        "whatsapp_messages_per_month": 150,
    },
]


class Command(BaseCommand):
    help = "Create the missing hub plans (the production catalogue); --update also overwrites the existing ones."

    def add_arguments(self, parser):
        parser.add_argument(
            "--update",
            action="store_true",
            help="Also put every field of the existing plans back to the seed, overwriting admin edits.",
        )

    def handle(self, *args, **options):
        update = options["update"]
        # get_or_create / update_or_create each run in their own short transaction and are safe
        # against a concurrent insert of the same slug (unique), so the web keeps serving meanwhile.
        write = Plan.objects.update_or_create if update else Plan.objects.get_or_create
        created_count = 0
        for data in PLANS:
            plan, created = write(slug=data["slug"], defaults=data)
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"  + created: {plan.slug} ({plan.price_monthly} EUR/month)"))
            elif update:
                self.stdout.write(f"  ~ updated: {plan.slug} ({plan.price_monthly} EUR/month)")
        others = len(PLANS) - created_count
        self.stdout.write(
            self.style.SUCCESS(f"Plans: {created_count} created, {others} {'updated' if update else 'existing'}")
        )
