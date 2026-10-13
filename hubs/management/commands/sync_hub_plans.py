"""Seed of the hub plans: ``python manage.py sync_hub_plans``.

Ported from ERPlora/saas ``hubs/subscriptions/management/commands/sync_hub_plans.py``
(origin/develop, production catalogue of 2026-06-13). Idempotent: creates the plans that are
missing and puts the existing ones back to these values.

Catalogue:

- ``free``: permanent Free plan (0 €, no card, ADR-0154): 1 hub, 1 device, 3 users, no trial. Never
  synced to Stripe.
- ``starter`` / ``standard``: the paid plans sold on the web, with a 15-day trial (ADR-0154). The
  trial is never a ``features`` line: cards paint it from ``trial_period_days`` (saas#2424).
- ``pro`` / ``enterprise`` / ``max``: upgrade-only, never on the public pricing page.
- ``payment-test``: internal plan to exercise the billing chain end to end (saas#1052).

Changed from the original: no container sizing nor suspension price (a plan sizes no container,
PLAN-SAAS §1); the
database limits follow round 9 (PLAN §14.2): Free 1 transaction at a time and 5 s, paid 3 and
15 s; no retired slugs to switch off (saas-next starts from an empty database).

What the commercial copy may say (saas#1760; guarded by ``hubs/tests/test_sync_hub_plans.py``):
the billing unit is the HUB; no infrastructure specs; support is sold as channel and priority,
never as a clock; one recovery window for the whole cluster; no uptime SLA percentage.
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from hubs.models import Plan

FREE_DB_LIMITS = {"max_db_connections": 1, "statement_timeout_seconds": 5}
PAID_DB_LIMITS = {"max_db_connections": 3, "statement_timeout_seconds": 15}

PLANS = [
    {
        "slug": "free",
        "name_en": "Free",
        "name_es": "Gratis",
        "description_en": "Start selling today. No credit card, no server, no maintenance.",
        "description_es": "Empieza a vender hoy. Sin tarjeta, sin servidor, sin mantenimiento.",
        "features_en": [
            "1 device",
            "3 local users",
            "Fully managed cloud",
            "No credit card required",
            "All modules included",
            "Managed PostgreSQL database",
            "Continuous backup with point-in-time recovery (up to 30 days)",
            ".erplora.com subdomain",
            "Community support",
        ],
        "features_es": [
            "1 dispositivo",
            "3 usuarios locales",
            "Cloud gestionado",
            "Sin tarjeta de crédito",
            "Todos los módulos incluidos",
            "Base de datos PostgreSQL gestionada",
            "Copia continua con restauración a un punto en el tiempo (hasta 30 días)",
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
        "included_level": "free",
        "support_level": "community",
        "includes_custom_domain": False,
    },
    {
        "slug": "starter",
        "name_en": "Starter",
        "name_es": "Starter",
        "description_en": "Your business in the cloud. No servers, no maintenance, always available.",
        "description_es": "Tu negocio en la nube. Sin servidores, sin mantenimiento, siempre disponible.",
        "features_en": [
            "Priced per hub — every location, device and user included",
            "Fully managed cloud",
            "No server maintenance",
            "Unlimited users",
            "All modules included",
            "Access from any device",
            "Managed PostgreSQL database",
            "Continuous backup with point-in-time recovery (up to 30 days)",
            "Data encryption (AES-256)",
            "Automatic SSL certificate",
            ".erplora.com subdomain",
            "Email support (business hours)",
        ],
        "features_es": [
            "Precio por hub — con todos sus locales, dispositivos y usuarios",
            "Cloud gestionado",
            "Sin mantenimiento de servidores",
            "Usuarios ilimitados",
            "Todos los módulos incluidos",
            "Acceso desde cualquier dispositivo",
            "Base de datos PostgreSQL gestionada",
            "Copia continua con restauración a un punto en el tiempo (hasta 30 días)",
            "Cifrado de datos (AES-256)",
            "Certificado SSL automático",
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
        "included_level": "basic",
        "support_level": "email",
        "includes_custom_domain": False,
    },
    {
        "slug": "standard",
        "name_en": "Standard",
        "name_es": "Standard",
        "description_en": "More power for growing businesses. Custom domain and automatic scaling.",
        "description_es": "Más potencia para negocios en crecimiento. Dominio propio y escalado automático.",
        "features_en": [
            "Everything in Starter",
            "Priced per hub — every location, device and user included",
            "Custom domain (erp.yourbusiness.com)",
            "Automatic resource scaling",
            "Priority email support (business hours)",
        ],
        "features_es": [
            "Todo lo del plan Starter",
            "Precio por hub — con todos sus locales, dispositivos y usuarios",
            "Dominio propio (erp.tunegocio.com)",
            "Escalado automático de recursos",
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
        **PAID_DB_LIMITS,
        "max_devices": 0,
        "max_users": 0,
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
    },
]


class Command(BaseCommand):
    help = "Create or update the hub plans (the production catalogue)."

    def handle(self, *args, **options):
        created_count = updated_count = 0
        with transaction.atomic():
            for data in PLANS:
                plan, created = Plan.objects.update_or_create(slug=data["slug"], defaults=data)
                if created:
                    created_count += 1
                    self.stdout.write(self.style.SUCCESS(f"  + created: {plan.slug} ({plan.price_monthly} EUR/month)"))
                else:
                    updated_count += 1
                    self.stdout.write(f"  ~ updated: {plan.slug} ({plan.price_monthly} EUR/month)")
        self.stdout.write(
            self.style.SUCCESS(
                f"OK: created {created_count}, updated {updated_count}, "
                f"active {Plan.objects.filter(is_active=True).count()}"
            )
        )
