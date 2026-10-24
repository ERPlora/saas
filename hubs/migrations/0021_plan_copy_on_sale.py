"""Data: the cards on sale say what every plan gives (Ioan, 2026-10-24; PLAN-SAAS §9, round 2026-10-24b, PLAN §32).

0013 seeded Starter and Standard with «Priced per business — every location, device and user included», and Standard
with «… for busy counters and several locations». Multi-location comes from Pro and is charged per location, so those
words promised what the two plans do not sell, on the public web and in the Store. From here the line says devices and
users, which the paid plans do not cap, and Standard's throughput line ends at the counters. Free never named a
location.

0013 also sold tiers of apps: Free «All free apps included», Starter «All apps included, free and premium». Every plan
includes every module now (``included_level`` stays, dormant, for a future ``premium`` module), so both say «All
apps included», the word the public web uses for them (decision 19 of the catalog spec). Standard, Pro, Enterprise and Max say «Everything in …» and never named a tier. The plans, their
prices and their limits do not move.

Only the columns of ``COPY`` are written, each only while it still reads 0013's words: what staff wrote in the admin
is theirs. Reverse: each goes back to 0013's words while it still reads this migration's. Idempotent; a database
without the rows is left as it is. Frozen in literals: a migration is history.
"""

from django.db import migrations

MANAGED_DATABASE_EN = (
    "Managed database, replicated across several European data centres, with continuous backups and "
    "point-in-time recovery for 14 days"
)
MANAGED_DATABASE_ES = (
    "Base de datos gestionada, replicada en varios centros de datos europeos, con copias de seguridad "
    "continuas y recuperación a cualquier momento de los últimos 14 días"
)

#: slug → column → (0013's words, the words from here).
COPY = {
    "free": {
        "features_en": (
            [
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
            [
                "1 device",
                "3 users",
                "Basic database throughput, sized for one device",
                "No credit card required",
                "All apps included",
                "Fully managed cloud on Amazon Web Services, in Europe, with automatic scaling",
                MANAGED_DATABASE_EN,
                "Encrypted data and automatic SSL certificate",
                ".erplora.com subdomain",
                "Community support",
            ],
        ),
        "features_es": (
            [
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
            [
                "1 dispositivo",
                "3 usuarios",
                "Capacidad de base de datos básica, a la medida de un dispositivo",
                "Sin tarjeta de crédito",
                "Todas las apps incluidas",
                "Cloud gestionado en Amazon Web Services, en Europa, con autoescalado",
                MANAGED_DATABASE_ES,
                "Datos cifrados y certificado SSL automático",
                "Subdominio .erplora.com",
                "Soporte de la comunidad",
            ],
        ),
    },
    "starter": {
        "features_en": (
            [
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
            [
                "Priced per business — every device and user included",
                "Unlimited devices — sell from several at once",
                "Unlimited users",
                "Full database throughput, for several devices at once",
                "All apps included",
                "Access from any device, always up to date",
                "Fully managed cloud on Amazon Web Services, in Europe, with automatic scaling",
                MANAGED_DATABASE_EN,
                "Encrypted data and automatic SSL certificate",
                ".erplora.com subdomain",
                "Email support (business hours)",
            ],
        ),
        "features_es": (
            [
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
            [
                "Precio por negocio — con todos sus dispositivos y usuarios",
                "Dispositivos ilimitados: vende desde varios a la vez",
                "Usuarios ilimitados",
                "Capacidad de base de datos completa, para varios dispositivos a la vez",
                "Todas las apps incluidas",
                "Acceso desde cualquier dispositivo, siempre actualizado",
                "Cloud gestionado en Amazon Web Services, en Europa, con autoescalado",
                MANAGED_DATABASE_ES,
                "Datos cifrados y certificado SSL automático",
                "Subdominio .erplora.com",
                "Soporte por email (horario laboral)",
            ],
        ),
    },
    "standard": {
        "features_en": (
            [
                "Everything in Starter",
                "Priced per business — every location, device and user included",
                "Twice the database throughput of Starter, for busy counters and several locations",
                "Custom domain (erp.yourbusiness.com)",
                "More capacity as your business grows, automatically",
                "Priority email support (business hours)",
            ],
            [
                "Everything in Starter",
                "Priced per business — every device and user included",
                "Twice the database throughput of Starter, for busy counters",
                "Custom domain (erp.yourbusiness.com)",
                "More capacity as your business grows, automatically",
                "Priority email support (business hours)",
            ],
        ),
        "features_es": (
            [
                "Todo lo del plan Starter",
                "Precio por negocio — con todos sus locales, dispositivos y usuarios",
                "El doble de capacidad de base de datos que Starter, para mostradores con mucho movimiento y varios locales",
                "Dominio propio (erp.tunegocio.com)",
                "Más capacidad a medida que crece tu negocio, automáticamente",
                "Soporte por email prioritario (horario laboral)",
            ],
            [
                "Todo lo del plan Starter",
                "Precio por negocio — con todos sus dispositivos y usuarios",
                "El doble de capacidad de base de datos que Starter, para mostradores con mucho movimiento",
                "Dominio propio (erp.tunegocio.com)",
                "Más capacidad a medida que crece tu negocio, automáticamente",
                "Soporte por email prioritario (horario laboral)",
            ],
        ),
    },
}


def _rewrite(apps, source: int, target: int) -> None:
    Plan = apps.get_model("hubs", "Plan")
    for slug, columns in COPY.items():
        for column, words in columns.items():
            Plan.objects.filter(slug=slug, **{column: words[source]}).update(**{column: words[target]})


def describe_the_cards_on_sale(apps, schema_editor):
    _rewrite(apps, 0, 1)


def give_back_the_words_of_0013(apps, schema_editor):
    _rewrite(apps, 1, 0)


class Migration(migrations.Migration):

    dependencies = [
        ("hubs", "0020_paid_plan_copy"),
    ]

    operations = [
        migrations.RunPython(describe_the_cards_on_sale, give_back_the_words_of_0013),
    ]
