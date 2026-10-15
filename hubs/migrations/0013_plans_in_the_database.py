"""Data: the plans live in the database, with no trial (Ioan, 2026-10-15).

Until this date a command (``sync_hub_plans``) seeded the plans on every deploy, creating the missing ones and
leaving the rest as staff left them. From here the plans live only in the database and staff keep them in the
admin: there is no command that seeds or overwrites them. This migration is the seed of a new database and puts
the rows already in production right, once:

- the seven plans of the seed that day (``CATALOGUE``) are written with its values, created if missing and updated
  in place if not, so the subscriptions that point at them keep pointing at them: ``free``, ``starter`` and
  ``standard`` (on sale at sign-up; the copy and the resource ladder 0011 froze), ``pro``, ``enterprise`` and
  ``max`` (kept by Ioan on 2026-10-15: active and ``upgrade_only``, an upgrade of a business that already pays;
  their prices as production has them) and ``payment-test`` (internal). The messages a month are the ones 0012 gave;
- no plan has a trial any more: Starter and Standard go from 15 days to 0 (the Free plan is the way in, and no
  law asks for a trial). The mechanism stays dormant (``trial_period_days``, the checkout's ``trial_end``): staff
  may give a plan a trial in the admin;
- what staff fill in by hand is theirs: the link of each plan to Stripe (``stripe_product_id``,
  ``stripe_price_id``, ``stripe_price_id_annual``) is never written;
- a plan staff added in the admin under another slug is left as it is.

The «resources» that grow from one plan to the next are the database's input/output capacity, told in plain
words («database throughput»); ``max_db_connections`` and ``statement_timeout_seconds`` are the technical ladder
behind it, each plan twice the one below from Starter (Free 1 and 5 s, Starter 3, Standard 6, Pro 12, Enterprise
24 and Max 48, all at 15 s), and are never shown.

Reverse: Starter and Standard get their 15-day trial back, the one thing this migration took away on purpose.
The rows stay (a subscription may point at them, and the values before this migration are nowhere to be read
back from), which is still a valid catalogue. Idempotent.

The values are literals: a migration is history, so no later change of the code rewrites what this one did.
"""

from decimal import Decimal

from django.db import migrations

#: The trial Starter and Standard carried until this migration, given back by its reverse.
TRIAL_DAYS_BEFORE = {"starter": 15, "standard": 15}

#: The database line of Free and Starter: one sentence with the backups.
MANAGED_DATABASE_EN = (
    "Managed database, replicated across several European data centres, with continuous backups and "
    "point-in-time recovery for 14 days"
)
MANAGED_DATABASE_ES = (
    "Base de datos gestionada, replicada en varios centros de datos europeos, con copias de seguridad "
    "continuas y recuperación a cualquier momento de los últimos 14 días"
)

#: slug → every field of the plan on 2026-10-15, but the link to Stripe (staff's).
CATALOGUE = {
    "free": {
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
        "max_devices": 1,
        "max_users": 3,
        "max_db_connections": 1,
        "statement_timeout_seconds": 5,
        "assistant_messages_per_month": 30,
        "whatsapp_messages_per_month": 30,
        "included_level": "free",
        "support_level": "community",
        "includes_custom_domain": False,
    },
    "starter": {
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
        "trial_period_days": 0,
        "display_order": 30,
        "max_hubs_per_org": 0,
        "max_devices": 0,
        "max_users": 0,
        "max_db_connections": 3,
        "statement_timeout_seconds": 15,
        "assistant_messages_per_month": 300,
        "whatsapp_messages_per_month": 150,
        "included_level": "basic",
        "support_level": "email",
        "includes_custom_domain": False,
    },
    "standard": {
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
        "trial_period_days": 0,
        "display_order": 40,
        "max_hubs_per_org": 0,
        "max_devices": 0,
        "max_users": 0,
        # Twice Starter, as every resource of the plan (Ioan, 2026-10-15).
        "max_db_connections": 6,
        "statement_timeout_seconds": 15,
        "assistant_messages_per_month": 600,
        "whatsapp_messages_per_month": 300,
        "included_level": "basic",
        "support_level": "priority_email",
        "includes_custom_domain": True,
    },
    # The upgrade-only tiers (Ioan, 2026-10-15: kept, not retired), going on up the ladder: each twice the one below
    # (Pro 12, Enterprise 24, Max 48), and a card line that says so. The Store offers them to a business Stripe already
    # bills; the public web does not list them.
    "pro": {
        "name_en": "Pro",
        "name_es": "Pro",
        "description_en": "High performance on isolated infrastructure, with a full API for your integrations.",
        "description_es": "Alto rendimiento en infraestructura aislada, con API completa para tus integraciones.",
        "features_en": [
            "Everything in Standard",
            "Four times the database throughput of Starter",
            "Isolated infrastructure",
            "Priority email support (business hours)",
        ],
        "features_es": [
            "Todo lo del plan Standard",
            "El cuádruple de capacidad de base de datos que Starter",
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
        "max_devices": 0,
        "max_users": 0,
        "max_db_connections": 12,
        "statement_timeout_seconds": 15,
        # The old stack's level pro (ADR-0474); enterprise and max, its level enterprise.
        "assistant_messages_per_month": 1000,
        "whatsapp_messages_per_month": 500,
        "included_level": "pro",
        "support_level": "priority_email",
        "includes_custom_domain": True,
    },
    "enterprise": {
        "name_en": "Enterprise",
        "name_es": "Enterprise",
        "description_en": "Dedicated infrastructure with autoscaling, disaster recovery and contract-backed support.",
        "description_es": (
            "Infraestructura dedicada con autoescalado, recuperación ante desastres y soporte acordado en contrato."
        ),
        "features_en": [
            "Everything in Pro",
            "Eight times the database throughput of Starter",
            "Automatic container autoscaling",
            "Disaster recovery (PITR)",
            "Advanced monitoring",
            "Support channels and escalation agreed in contract",
        ],
        "features_es": [
            "Todo lo del plan Pro",
            "Ocho veces la capacidad de base de datos de Starter",
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
        "max_devices": 0,
        "max_users": 0,
        "max_db_connections": 24,
        "statement_timeout_seconds": 15,
        "assistant_messages_per_month": 3000,
        "whatsapp_messages_per_month": 800,
        "included_level": "enterprise",
        "support_level": "contract",
        "includes_custom_domain": True,
    },
    "max": {
        "name_en": "Max",
        "name_es": "Max",
        "description_en": "Maximum single-node performance, for the most demanding businesses.",
        "description_es": "Máximo rendimiento de un solo nodo, para los negocios más exigentes.",
        "features_en": [
            "Everything in Enterprise",
            "Sixteen times the database throughput of Starter",
            "─────────────────────",
            "Custom integrations",
            "Named technical contact agreed in contract",
        ],
        "features_es": [
            "Todo lo del plan Enterprise",
            "Dieciséis veces la capacidad de base de datos de Starter",
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
        "max_devices": 0,
        "max_users": 0,
        "max_db_connections": 48,
        "statement_timeout_seconds": 15,
        "assistant_messages_per_month": 3000,
        "whatsapp_messages_per_month": 800,
        "included_level": "enterprise",
        "support_level": "contract",
        "includes_custom_domain": True,
    },
    # saas#1052: a REAL subscription (charged through Stripe) with no trial, so a real invoice, its AEAT record and
    # its QR can be seen at once. ``internal_only`` hides it from every public door and only staff may buy it.
    # 1.00 € net → 1.21 € with Spanish VAT.
    "payment-test": {
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
        "trial_period_days": 0,
        "display_order": 999,
        "max_hubs_per_org": 0,
        "max_devices": 0,
        "max_users": 0,
        "max_db_connections": 3,
        "statement_timeout_seconds": 15,
        "assistant_messages_per_month": 300,
        "whatsapp_messages_per_month": 150,
        "included_level": "free",
        "support_level": "community",
        "includes_custom_domain": False,
    },
}


def put_the_catalogue_in(apps, schema_editor):
    Plan = apps.get_model("hubs", "Plan")
    for slug, fields in CATALOGUE.items():
        Plan.objects.update_or_create(slug=slug, defaults=fields)


def give_the_trial_back(apps, schema_editor):
    Plan = apps.get_model("hubs", "Plan")
    for slug, days in TRIAL_DAYS_BEFORE.items():
        Plan.objects.filter(slug=slug).update(trial_period_days=days)


class Migration(migrations.Migration):
    dependencies = [
        ("hubs", "0012_plan_monthly_messages"),
    ]

    operations = [
        migrations.RunPython(put_the_catalogue_in, give_the_trial_back),
    ]
