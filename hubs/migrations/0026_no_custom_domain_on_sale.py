"""Data: Standard's card stops selling a custom domain nobody can connect.

0013 seeded Standard with «For growing businesses: your own domain, …» and the line «Custom domain
(erp.yourbusiness.com)», which 0021 kept. No business could connect a domain then: that needs three pieces at once (the
check in erplora.com, the certificate on the load balancer and the Hub serving the business's public website on it),
and then only for the public website, never the app. The public web, the plan's
detail page and the Store paint these columns, so from here they say only what Standard gives. The gate
(``includes_custom_domain``), the plans, their prices and their limits do not move.

Only the columns of ``COPY`` are written, each only while it still reads 0021's words (0013's for the description,
which 0021 left): what staff wrote in the admin is theirs. Reverse: each goes back to those words while it still reads
this migration's. Idempotent; a database without the row is left as it is. Frozen in literals: a migration is history.
"""

from django.db import migrations

#: slug → column → (0021's words, the words from here).
COPY = {
    "standard": {
        "description_en": (
            "For growing businesses: your own domain, twice the resources and priority support.",
            "For growing businesses: twice the resources and priority support.",
        ),
        "description_es": (
            "Para negocios en crecimiento: dominio propio, el doble de recursos y soporte prioritario.",
            "Para negocios en crecimiento: el doble de recursos y soporte prioritario.",
        ),
        "features_en": (
            [
                "Everything in Starter",
                "Priced per business — every device and user included",
                "Twice the database throughput of Starter, for busy counters",
                "Custom domain (erp.yourbusiness.com)",
                "More capacity as your business grows, automatically",
                "Priority email support (business hours)",
            ],
            [
                "Everything in Starter",
                "Priced per business — every device and user included",
                "Twice the database throughput of Starter, for busy counters",
                "More capacity as your business grows, automatically",
                "Priority email support (business hours)",
            ],
        ),
        "features_es": (
            [
                "Todo lo del plan Starter",
                "Precio por negocio — con todos sus dispositivos y usuarios",
                "El doble de capacidad de base de datos que Starter, para mostradores con mucho movimiento",
                "Dominio propio (erp.tunegocio.com)",
                "Más capacidad a medida que crece tu negocio, automáticamente",
                "Soporte por email prioritario (horario laboral)",
            ],
            [
                "Todo lo del plan Starter",
                "Precio por negocio — con todos sus dispositivos y usuarios",
                "El doble de capacidad de base de datos que Starter, para mostradores con mucho movimiento",
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


def stop_selling_the_custom_domain(apps, schema_editor):
    _rewrite(apps, 0, 1)


def give_back_the_words_of_0021(apps, schema_editor):
    _rewrite(apps, 1, 0)


class Migration(migrations.Migration):

    dependencies = [
        ("hubs", "0025_country_names"),
    ]

    operations = [
        migrations.RunPython(stop_selling_the_custom_domain, give_back_the_words_of_0021),
    ]
