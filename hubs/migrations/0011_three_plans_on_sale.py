"""Data: three plans on sale at sign-up, their copy and their resource ladder (Ioan, 2026-10-15).

``sync_hub_plans`` runs on every deploy but never overwrites a row (``--update`` is a hand run), so the
plans seeded before this date kept what the old seed said, a database line naming the engine under it
(«Managed PostgreSQL database») included. From here Free, Starter and Standard read the copy the seed carried
that day (``COPY``) — description and features, in both languages — and the resource ladder of 2026-10-15
(``max_db_connections``, ``statement_timeout_seconds``: each plan up doubles the one below, so Standard has
twice Starter's), and keep everything else as staff left it (prices, trial, seat caps, Stripe ids).

The upgrade-only tiers (``pro``, ``enterprise``, ``max``) are not touched: Ioan kept them on 2026-10-15, active
and ``upgrade_only``, as production has them. (A first draft of this migration, never deployed, took them off
sale; that was dropped before it left the branch.)

Reverse: nothing to undo. The copy stays (its old wording is nowhere to be read back from), which is still a
valid catalogue. Idempotent; a database without the rows is left as it is.
"""

from django.db import migrations

#: The copy and the resource ladder the seed (``sync_hub_plans``) carried on 2026-10-15, frozen here: a
#: migration is history, so a later change of the seed never rewrites what this one did.
COPY = {
    "free": {
        "description_en": "Start selling today. No credit card, no server, no maintenance.",
        "description_es": "Empieza a vender hoy. Sin tarjeta, sin servidor, sin mantenimiento.",
        "features_en": [
            "1 device",
            "3 users",
            "Basic database throughput, sized for one device",
            "No credit card required",
            "All free apps included",
            "Fully managed cloud on Amazon Web Services, in Europe, with automatic scaling",
            "Managed database, replicated across several European data centres, with continuous backups and point-in-time recovery for 14 days",
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
            "Base de datos gestionada, replicada en varios centros de datos europeos, con copias de seguridad continuas y recuperación a cualquier momento de los últimos 14 días",
            "Datos cifrados y certificado SSL automático",
            "Subdominio .erplora.com",
            "Soporte de la comunidad",
        ],
        "max_db_connections": 1,
        "statement_timeout_seconds": 5,
    },
    "starter": {
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
            "Managed database, replicated across several European data centres, with continuous backups and point-in-time recovery for 14 days",
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
            "Base de datos gestionada, replicada en varios centros de datos europeos, con copias de seguridad continuas y recuperación a cualquier momento de los últimos 14 días",
            "Datos cifrados y certificado SSL automático",
            "Subdominio .erplora.com",
            "Soporte por email (horario laboral)",
        ],
        "max_db_connections": 3,
        "statement_timeout_seconds": 15,
    },
    "standard": {
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
        "max_db_connections": 6,
        "statement_timeout_seconds": 15,
    },
}


def refresh_the_copy(apps, schema_editor):
    Plan = apps.get_model("hubs", "Plan")
    for slug, copy in COPY.items():
        Plan.objects.filter(slug=slug).update(**copy)


class Migration(migrations.Migration):
    dependencies = [
        ("hubs", "0010_hub_usage_daily"),
    ]

    operations = [
        migrations.RunPython(refresh_the_copy, migrations.RunPython.noop),
    ]
