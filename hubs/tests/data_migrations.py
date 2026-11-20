"""What the tests of the data migrations of hubs share: running a ``RunPython`` function by hand, checking
that a migration reads nothing of the code, and the plan catalogue each migration leaves (0013) with the
cards the later ones rewrite (0020, 0021, 0026 and 0029)."""

from decimal import Decimal
from importlib import import_module

from django.db import connection

from hubs.tests.test_plan_catalogue import MANAGED_DATABASE


class _SchemaEditor:
    """What a ``RunPython`` function reads from the schema editor: the connection."""

    connection = connection


def _imported_modules(module) -> set[str]:
    import ast
    from pathlib import Path

    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    names = {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    names |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    return names


# --- 0011: three plans on sale at sign-up, their copy and ladder -----------------------------------

THREE_PLANS = "0011_three_plans_on_sale"


def _three_plans():
    return import_module(f"hubs.migrations.{THREE_PLANS}")


# --- 0013: the plans live in the database; no trial -----------------------------------------------

#: What every paid plan shares on the axes the cards do not compare.
_UNCAPPED = {"max_hubs_per_org": 0, "max_devices": 0, "max_users": 0}
#: The catalogue 0013 leaves, field by field: three plans on sale at sign-up, the three upgrade-only tiers (kept,
#: active, going on up the ladder: each twice the one below, Pro 12, Enterprise 24, Max 48) and the internal one, none with a trial (the Free plan is the way in). The copy
#: of Free, Starter and Standard is the one 0011 froze (``COPY``), the messages the ones 0012 gave; history of the
#: same day, so the three migrations must agree.
CATALOGUE_0013 = {
    "free": {
        "name_en": "Free", "name_es": "Gratis", "featured_label_en": "", "featured_label_es": "",
        "price_monthly": Decimal("0"), "price_annual": Decimal("0"),
        "is_active": True, "upgrade_only": False, "internal_only": False, "trial_period_days": 0, "display_order": 10,
        "max_hubs_per_org": 1, "max_devices": 1, "max_users": 3, "max_db_connections": 1, "statement_timeout_seconds": 5,
        "assistant_messages_per_month": 30, "whatsapp_messages_per_month": 30,
        "included_level": "free", "support_level": "community", "includes_custom_domain": False,
    },
    "starter": {
        "name_en": "Starter", "name_es": "Starter", "featured_label_en": "", "featured_label_es": "",
        "price_monthly": Decimal("29.99"), "price_annual": Decimal("299.90"),
        "is_active": True, "upgrade_only": False, "internal_only": False, "trial_period_days": 0, "display_order": 30,
        **_UNCAPPED, "max_db_connections": 3, "statement_timeout_seconds": 15,
        "assistant_messages_per_month": 300, "whatsapp_messages_per_month": 150,
        "included_level": "basic", "support_level": "email", "includes_custom_domain": False,
    },
    "standard": {
        "name_en": "Standard", "name_es": "Standard", "featured_label_en": "Recommended", "featured_label_es": "Recomendado",
        "price_monthly": Decimal("54.99"), "price_annual": Decimal("549.90"),
        "is_active": True, "upgrade_only": False, "internal_only": False, "trial_period_days": 0, "display_order": 40,
        **_UNCAPPED, "max_db_connections": 6, "statement_timeout_seconds": 15,
        "assistant_messages_per_month": 600, "whatsapp_messages_per_month": 300,
        "included_level": "basic", "support_level": "priority_email", "includes_custom_domain": True,
    },
    "pro": {
        "name_en": "Pro", "name_es": "Pro", "featured_label_en": "", "featured_label_es": "",
        "description_en": "High performance on isolated infrastructure, with a full API for your integrations.",
        "description_es": "Alto rendimiento en infraestructura aislada, con API completa para tus integraciones.",
        "features_en": [
            "Everything in Standard", "Four times the database throughput of Starter", "Isolated infrastructure",
            "Priority email support (business hours)",
        ],
        "features_es": [
            "Todo lo del plan Standard", "El cuádruple de capacidad de base de datos que Starter", "Infraestructura aislada",
            "Soporte por email prioritario (horario laboral)",
        ],
        "price_monthly": Decimal("109.99"), "price_annual": Decimal("1099.90"),
        "is_active": True, "upgrade_only": True, "internal_only": False, "trial_period_days": 0, "display_order": 50,
        **_UNCAPPED, "max_db_connections": 12, "statement_timeout_seconds": 15,
        "assistant_messages_per_month": 1000, "whatsapp_messages_per_month": 500,
        "included_level": "pro", "support_level": "priority_email", "includes_custom_domain": True,
    },
    "enterprise": {
        "name_en": "Enterprise", "name_es": "Enterprise", "featured_label_en": "", "featured_label_es": "",
        "description_en": "Dedicated infrastructure with autoscaling, disaster recovery and contract-backed support.",
        "description_es": "Infraestructura dedicada con autoescalado, recuperación ante desastres y soporte acordado en contrato.",
        "features_en": [
            "Everything in Pro", "Eight times the database throughput of Starter", "Automatic container autoscaling",
            "Disaster recovery (PITR)", "Advanced monitoring", "Support channels and escalation agreed in contract",
        ],
        "features_es": [
            "Todo lo del plan Pro", "Ocho veces la capacidad de base de datos de Starter",
            "Autoescalado automático de contenedores", "Recuperación ante desastres (PITR)", "Monitoreo avanzado",
            "Canales de soporte y escalado acordados en contrato",
        ],
        "price_monthly": Decimal("209.99"), "price_annual": Decimal("2099.90"),
        "is_active": True, "upgrade_only": True, "internal_only": False, "trial_period_days": 0, "display_order": 60,
        **_UNCAPPED, "max_db_connections": 24, "statement_timeout_seconds": 15,
        "assistant_messages_per_month": 3000, "whatsapp_messages_per_month": 800,
        "included_level": "enterprise", "support_level": "contract", "includes_custom_domain": True,
    },
    "max": {
        "name_en": "Max", "name_es": "Max", "featured_label_en": "", "featured_label_es": "",
        "description_en": "Maximum single-node performance, for the most demanding businesses.",
        "description_es": "Máximo rendimiento de un solo nodo, para los negocios más exigentes.",
        "features_en": [
            "Everything in Enterprise", "Sixteen times the database throughput of Starter", "─────────────────────",
            "Custom integrations", "Named technical contact agreed in contract",
        ],
        "features_es": [
            "Todo lo del plan Enterprise", "Dieciséis veces la capacidad de base de datos de Starter",
            "─────────────────────", "Integraciones a medida", "Responsable técnico acordado en contrato",
        ],
        "price_monthly": Decimal("419.99"), "price_annual": Decimal("4199.90"),
        "is_active": True, "upgrade_only": True, "internal_only": False, "trial_period_days": 0, "display_order": 70,
        **_UNCAPPED, "max_db_connections": 48, "statement_timeout_seconds": 15,
        "assistant_messages_per_month": 3000, "whatsapp_messages_per_month": 800,
        "included_level": "enterprise", "support_level": "contract", "includes_custom_domain": True,
    },
    "payment-test": {
        "name_en": "Payment Test (internal)", "name_es": "Prueba de pago (interno)",
        "description_en": "Internal plan for end-to-end billing verification. Not for sale.",
        "description_es": "Plan interno para verificar la facturación de punta a punta. No está a la venta.",
        "features_en": ["Internal use only"], "features_es": ["Solo uso interno"],
        "featured_label_en": "", "featured_label_es": "",
        "price_monthly": Decimal("1.00"), "price_annual": Decimal("0"),
        "is_active": True, "upgrade_only": False, "internal_only": True, "trial_period_days": 0, "display_order": 999,
        **_UNCAPPED, "max_db_connections": 3, "statement_timeout_seconds": 15,
        "assistant_messages_per_month": 300, "whatsapp_messages_per_month": 150,
        "included_level": "free", "support_level": "community", "includes_custom_domain": False,
    },
}  # fmt: skip
#: The copy fields 0011 froze for the three plans on sale.
COPY_FIELDS = ("description_en", "description_es", "features_en", "features_es")


def _expected_0013() -> dict[str, dict]:
    copy = _three_plans().COPY
    return {
        slug: {**fields, **{name: copy[slug][name] for name in COPY_FIELDS if slug in copy}}
        for slug, fields in CATALOGUE_0013.items()
    }


def _row(plan, fields) -> dict:
    return {name: getattr(plan, name) for name in fields}


def _snapshot(Plan) -> dict[str, dict]:
    fields = [field.name for field in Plan._meta.concrete_fields if field.name != "updated_at"]
    return {plan.slug: _row(plan, fields) for plan in Plan.objects.all()}


# --- 0020: the paid cards stop promising infrastructure --------------------------------------------

#: What 0020 writes, by plan and column: only what each row gives (``max_db_connections`` 12 / 24 / 48 against
#: Starter's 3, the messages of a month, no cap on devices or users, its ``support_level``).
COPY_0020 = {
    "pro": {
        "description_en": (
            "Four times the database capacity of Starter, for businesses with many devices and users, with priority "
            "email support."
        ),
        "description_es": (
            "El cuádruple de capacidad de base de datos que Starter, para negocios con muchos dispositivos y usuarios, "
            "con soporte por email prioritario."
        ),
        "features_en": [
            "Everything in Standard", "Four times the database throughput of Starter",
            "Priority email support (business hours)",
        ],
        "features_es": [
            "Todo lo del plan Standard", "El cuádruple de capacidad de base de datos que Starter",
            "Soporte por email prioritario (horario laboral)",
        ],
    },
    "enterprise": {
        "description_en": (
            "Twice the database throughput of Pro and more assistant and WhatsApp messages, for businesses with many "
            "devices and users, with support agreed in contract."
        ),
        "description_es": (
            "El doble de capacidad de base de datos que Pro y más mensajes del asistente y de WhatsApp, para negocios "
            "con muchos dispositivos y usuarios, con soporte acordado en contrato."
        ),
        "features_en": [
            "Everything in Pro", "Eight times the database throughput of Starter",
            "Support channels and escalation agreed in contract",
        ],
        "features_es": [
            "Todo lo del plan Pro", "Ocho veces la capacidad de base de datos de Starter",
            "Canales de soporte y escalado acordados en contrato",
        ],
    },
    "max": {
        "description_en": (
            "Sixteen times the database capacity of Starter and a named technical contact, for the most demanding "
            "businesses."
        ),
        "description_es": (
            "Dieciséis veces la capacidad de base de datos que Starter y un responsable técnico asignado, para los "
            "negocios más exigentes."
        ),
    },
}  # fmt: skip


# --- 0021: the cards on sale say what every plan gives ---------------------------------------------

#: The lines of the cards a business can sign up on that 0013 seeded and 0021 rewrites. «Every location included» and
#: «several locations» promised what Starter and Standard do not sell: multi-location comes from Pro and is charged per
#: location. «All free apps» and «free and premium» sold tiers of apps: every plan includes every module. Devices and
#: users stay, which the paid plans do not cap.
LINES_0021 = {
    "Priced per business — every location, device and user included": "Priced per business — every device and user included",
    "Twice the database throughput of Starter, for busy counters and several locations": (
        "Twice the database throughput of Starter, for busy counters"
    ),
    "Precio por negocio — con todos sus locales, dispositivos y usuarios": (
        "Precio por negocio — con todos sus dispositivos y usuarios"
    ),
    "El doble de capacidad de base de datos que Starter, para mostradores con mucho movimiento y varios locales": (
        "El doble de capacidad de base de datos que Starter, para mostradores con mucho movimiento"
    ),
    "All free apps included": "All apps included",
    "Todas las apps gratuitas incluidas": "Todas las apps incluidas",
    "All apps included, free and premium": "All apps included",
    "Todas las apps incluidas, gratuitas y premium": "Todas las apps incluidas",
}
#: The columns 0021 writes: the features of Free, Starter and Standard, in both languages.
CARD_COLUMNS_0021 = {slug: ("features_en", "features_es") for slug in ("free", "starter", "standard")}
#: What 0013 seeded in those columns (the copy 0011 froze), and 0021 gives back on reverse.
CARDS_0013 = {
    slug: {column: list(_three_plans().COPY[slug][column]) for column in columns}
    for slug, columns in CARD_COLUMNS_0021.items()
}
#: What 0021 writes: the same lists, each rewritten line in its place.
COPY_0021 = {
    slug: {column: [LINES_0021.get(line, line) for line in lines] for column, lines in columns.items()}
    for slug, columns in CARDS_0013.items()
}


# --- 0026: no card sells a custom domain nobody can connect ----------------------------------------

#: The features 0026 writes: 0021's, without the custom-domain line.
FEATURES_0026 = {
    column: [line for line in lines if not line.startswith(("Custom domain", "Dominio propio"))]
    for column, lines in COPY_0021["standard"].items()
}
#: What 0026 writes on Standard, and only there.
COPY_0026 = {
    "standard": {
        "description_en": "For growing businesses: twice the resources and priority support.",
        "description_es": "Para negocios en crecimiento: el doble de recursos y soporte prioritario.",
        **FEATURES_0026,
    }
}


# --- 0029: the database line says what a recovery keeps --------------------------------------------

#: The database line 0013 seeded on Free and Starter and 0021 kept: the window alone, a whole return to any moment that
#: a business invoicing with VeriFactu never gets (what it sent to the tax agency stays; the Hub's BASE-F114).
LINES_0013 = {
    "features_en": (
        "Managed database, replicated across several European data centres, with continuous backups and "
        "point-in-time recovery for 14 days"
    ),
    "features_es": (
        "Base de datos gestionada, replicada en varios centros de datos europeos, con copias de seguridad "
        "continuas y recuperación a cualquier momento de los últimos 14 días"
    ),
}
#: The line 0029 writes in its place, in each language: the window and what a recovery keeps.
LINES_0029 = {"features_en": MANAGED_DATABASE["en"], "features_es": MANAGED_DATABASE["es"]}
#: The plans whose cards carry the database line (Standard, Pro, Enterprise and Max say «Everything in …»).
DATABASE_LINE_PLANS = ("free", "starter")
#: What 0029 writes: the features of Free and Starter as 0021 leaves them, the database line rewritten in its place.
COPY_0029 = {
    slug: {
        column: [LINES_0029[column] if line == LINES_0013[column] else line for line in COPY_0021[slug][column]]
        for column in LINES_0013
    }
    for slug in DATABASE_LINE_PLANS
}
