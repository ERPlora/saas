"""What the store publishes of an app's user documentation.

The Hub registers the customer's part of each WORKBOOK as written, flow keys included. The store
shows of each flow what the Hub's help window shows (its title without the id, its steps and what
happens if it fails), only for the flows that are done, and without the references a customer
cannot follow: issue numbers, sizes in pixels and the names of operations or events. A flow is named
by its title, which the reader sees, never by its id.
"""

import pytest
from live.shared_catalog import DOC_LANGUAGES

from apps.public_doc import WORDS, public_markdown

SPANISH = """\
## Para qué sirve y para quién

Mesas es el plano de la sala.

## Antes de empezar

- Crea las zonas del local (TABLE-F01) antes que las mesas.

## Flujos

| ID | Flujo | Estado |
|---|---|---|
| TABLE-F01 | Crear una zona | hecho |
| TABLE-F02 | Juntar dos zonas | no hecho |

### TABLE-F01 Crear una zona
Estado: hecho — en la tableta y en el móvil
Vertical: restaurante
Actor: responsable
Pantalla: Zonas
Pasos:
1. En **Mesas → Zonas** pulsa «+» y escribe el nombre (TABLE-F06).
2. Colócala con las flechas (8 px; con Mayúsculas, 32 px).
Por el asistente: «crea la zona Terraza».
Entra: el nombre y el color.
Sale: la zona (avisa: `table.zone.created`).
Si falla: sin nombre, el botón no se activa. Un nombre repetido dice
«Ya hay una zona con ese nombre.» (hub#888).
Implicados: TABLE-F02, TABLE-F06

### TABLE-F02 Juntar dos zonas
Estado: no hecho — falta la pantalla
Actor: responsable
Pantalla: Zonas
Pasos:
1. Aún no se puede.
"""

SPANISH_PUBLISHED = """\
## Para qué sirve y para quién

Mesas es el plano de la sala.

## Antes de empezar

- Crea las zonas del local («Crear una zona») antes que las mesas.

## Flujos

### Crear una zona
Pasos:

1. En **Mesas → Zonas** pulsa «+» y escribe el nombre.
2. Colócala con las flechas.

Si falla: sin nombre, el botón no se activa. Un nombre repetido dice
«Ya hay una zona con ese nombre.».
"""


def test_a_done_flow_shows_its_title_its_steps_and_what_happens_if_it_fails():
    assert public_markdown(SPANISH, "es") == SPANISH_PUBLISHED


def test_the_english_document_reads_its_own_words():
    english = """\
## Flows

### TABLE-F01 Create a zone
Status: done (also on the phone)
Actor: manager
Screen: Zones
Steps:
1. Tap «+» and type the name.
2. Tap «Add zone» (ERPlora/hub#888).
In: the name.
Out: the zone (notifies `table.zone.created`).
If it fails: without a name the button stays off (TABLE-F06).
Through the assistant: «create the zone Terrace».
Involved: TABLE-F06

### TABLE-F03 Merge two zones
Status: not done
Steps:
1. Not yet.
"""

    assert public_markdown(english, "en") == (
        "## Flows\n\n"
        "### Create a zone\n"
        "Steps:\n\n"
        "1. Tap «+» and type the name.\n"
        "2. Tap «Add zone».\n\n"
        "If it fails: without a name the button stays off.\n"
    )


def test_a_flow_without_what_happens_if_it_fails_ends_with_its_steps():
    markdown = "### SALE-F01 Cobrar\nEstado: hecho\nPasos:\n1. Pulsa «Cobrar».\nSale: la venta.\n"

    assert public_markdown(markdown, "es") == "### Cobrar\nPasos:\n\n1. Pulsa «Cobrar».\n"


@pytest.mark.parametrize(
    "status",
    ["no hecho", "parcial — falta el móvil", "hechos a medias", "pendiente (hecho en el TPV)"],
)
def test_a_flow_that_does_not_read_as_done_is_not_published(status):
    markdown = f"## Flujos\n\n### SALE-F01 Cobrar\nEstado: {status}\nPasos:\n1. Pulsa «Cobrar».\n"

    assert public_markdown(markdown, "es") == "## Flujos\n"


@pytest.mark.parametrize(
    ("written", "published"),
    [
        ("Pulsa «Guardar» (hub#888).", "Pulsa «Guardar»."),
        ("Pulsa «Guardar» (ERPlora/saas#12, SALE-F02).", "Pulsa «Guardar»."),
        ("Se rechaza (`sale.order_closed`).", "Se rechaza."),
        ("Se rechaza (409 `service_unavailable`; sin guardar nada).", "Se rechaza (sin guardar nada)."),
        ("Se rechaza (sin distinguir mayúsculas, 409 `staff.role_name_taken`).", "Se rechaza (sin distinguir mayúsculas)."),
        ("Sale «Rechazado» (con el mensaje de la AEAT; VERIFACTU-F24).", "Sale «Rechazado» (con el mensaje de la AEAT)."),
        ("Cobra (también desde el TPV, SALE-F05) y cierra.", "Cobra (también desde el TPV) y cierra."),
        ("Sube una foto (un JPG o PNG de hasta 2 MB, como en INVENTORY-F31).", "Sube una foto (un JPG o PNG de hasta 2 MB)."),
        ("Usa una ficha (p. ej. «General», nunca su clave `product.generic`).", "Usa una ficha (p. ej. «General»)."),
        ("Muévela con las flechas (8 px; con Mayúsculas, 32 px).", "Muévela con las flechas."),
        ("Una foto (jpeg o png; hasta 8000 px por lado) por producto.", "Una foto (jpeg o png) por producto."),
        ("Rellena sus variables (`{{1}}`, `{{2}}`…).", "Rellena sus variables (`{{1}}`, `{{2}}`…)."),
        ("El número es `OS-AAAAMMDD-NNNN`.", "El número es `OS-AAAAMMDD-NNNN`."),
    ],
)
def test_the_references_a_customer_cannot_follow_leave_the_published_steps(written, published):
    markdown = f"### SALE-F01 Cobrar\nEstado: hecho\nPasos:\n1. {written}\n"

    assert public_markdown(markdown, "es") == f"### Cobrar\nPasos:\n\n1. {published}\n"


def test_a_reference_wrapped_over_two_lines_leaves_too():
    markdown = "### SALE-F01 Cobrar\nEstado: hecho\nPasos:\n1. Pulsa «Cobrar» (con el\n   importe; SALE-F02).\n"

    assert public_markdown(markdown, "es") == "### Cobrar\nPasos:\n\n1. Pulsa «Cobrar» (con el\n   importe).\n"


def test_a_flow_is_named_by_its_title_when_it_is_published_and_left_out_when_not():
    markdown = (
        "### SALE-F01 Cobrar una venta\nEstado: hecho\nPasos:\n1. Pulsa «Cobrar».\n"
        "Si falla: como en SALE-F02. Vale también en caja (SALE-F03; PRICING-F14) y al anular (SALE-F02).\n\n"
        "### SALE-F02 Anular una venta\nEstado: hecho\nPasos:\n1. Pulsa «Anular».\n\n"
        "### SALE-F03 Dividir la cuenta\nEstado: no hecho\nPasos:\n1. Aún no.\n"
    )

    assert public_markdown(markdown, "es") == (
        "### Cobrar una venta\nPasos:\n\n1. Pulsa «Cobrar».\n\n"
        "Si falla: como en «Anular una venta». Vale también en caja y al anular («Anular una venta»).\n\n"
        "### Anular una venta\nPasos:\n\n1. Pulsa «Anular».\n"
    )


def test_the_short_id_of_a_flow_of_the_same_document_is_named_by_its_title_too():
    markdown = (
        "### INVOICE-F01 Emitir una factura\nEstado: hecho\nPasos:\n1. Emite la F2 de un tique (F02) o la F1 (F09).\n\n"
        "### INVOICE-F02 Sustituir un tique\nEstado: hecho\nPasos:\n1. La F3 sustituye al tique.\n"
    )

    assert public_markdown(markdown, "es") == (
        "### Emitir una factura\nPasos:\n\n1. Emite la F2 de un tique («Sustituir un tique») o la F1.\n\n"
        "### Sustituir un tique\nPasos:\n\n1. La F3 sustituye al tique.\n"
    )


def test_a_reference_wrapped_at_the_end_of_a_parenthesis_leaves_no_separator_behind():
    markdown = "### SALE-F01 Cobrar\nEstado: hecho\nPasos:\n1. Pulsa «Cobrar» (como en el TPV,\n   SALE-F38) y espera.\n"

    assert public_markdown(markdown, "es") == "### Cobrar\nPasos:\n\n1. Pulsa «Cobrar» (como en el TPV) y espera.\n"


def test_only_the_index_of_flows_leaves_and_other_tables_stay():
    markdown = (
        "## Estados\n\n| Estado | Qué ve |\n|---|---|\n| Vacío | Nada (hub#866). |\n\n"
        "## Flujos\n\n| ID | Flujo | Estado |\n|---|---|---|\n| SALE-F01 | Cobrar | hecho |\n"
    )

    assert public_markdown(markdown, "es") == (
        "## Estados\n\n| Estado | Qué ve |\n|---|---|\n| Vacío | Nada. |\n\n## Flujos\n"
    )


def test_a_code_block_is_published_as_written():
    markdown = "## Pantallas\n\n```mermaid\ngraph TD; A[SALE-F01] --> B[hub#1];\n### SALE-F02 No es un flujo\n```\n"

    assert public_markdown(markdown, "es") == markdown


def test_the_flows_after_a_code_block_are_cleaned_too():
    diagram = "## Pantallas\n\n```mermaid\ngraph TD; A[SALE-F01] --> B;\n```\n\n"
    markdown = (
        f"{diagram}## Flujos\n\n| ID | Flujo | Estado |\n|---|---|---|\n| SALE-F01 | Cobrar | hecho |\n\n"
        "### SALE-F01 Cobrar\nEstado: hecho\nActor: empleado\nPasos:\n1. Pulsa «Cobrar» (hub#1).\n"
    )

    assert public_markdown(markdown, "es") == f"{diagram}## Flujos\n\n### Cobrar\nPasos:\n\n1. Pulsa «Cobrar».\n"


def test_a_document_without_flows_is_published_as_written():
    markdown = "# Facturas\n\nFactura a tus **clientes**.\n\n![Pantalla](docs/img/list.png)\n"

    assert public_markdown(markdown, "es") == markdown


def test_every_language_of_the_documentation_has_its_words():
    assert set(WORDS) == set(DOC_LANGUAGES)
