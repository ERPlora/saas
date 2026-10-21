"""WHATSAPP-G15 · A template is checked against Meta's rules before Meta is called, and written in Meta's shape.

Cases of the old product's ``test_templates.py`` (``services/templates.py``: name, category, language, body,
placeholders numbered without gaps or named, one example each, buttons and their limits), on the Hub's door 8 body
(``{name, language, category, header, body, body_examples, footer, buttons, meta_id}``), plus Meta's lengths the old
one left to Meta (header 60, body 1024, footer 60). And the way back: Meta's template as the mirror keeps it.
"""

import pytest

from whatsapp import templates
from whatsapp.schemas import TemplateIn


def template(**fields) -> TemplateIn:
    base = {
        "hub": "bar-manolo",
        "name": "recordatorio",
        "language": "es",
        "category": "UTILITY",
        "header": "Tu cita",
        "body": "Hola {{1}}, te esperamos el {{2}}.",
        "body_examples": ["Ana", "viernes"],
        "footer": "Peluquería Ana",
        "buttons": [{"type": "QUICK_REPLY", "text": "Confirmar"}],
        "meta_id": "",
    }
    return TemplateIn(**{**base, **fields})


def reason(**fields) -> str:
    with pytest.raises(templates.Invalid) as invalid:
        templates.check(template(**fields))
    return str(invalid.value)


def test_a_good_template_becomes_metas_components():
    clean = templates.check(template())

    assert templates.components(clean) == [
        {"type": "HEADER", "format": "TEXT", "text": "Tu cita"},
        {"type": "BODY", "text": "Hola {{1}}, te esperamos el {{2}}.", "example": {"body_text": [["Ana", "viernes"]]}},
        {"type": "FOOTER", "text": "Peluquería Ana"},
        {"type": "BUTTONS", "buttons": [{"type": "QUICK_REPLY", "text": "Confirmar"}]},
    ]
    assert (clean.variables, clean.named) == (2, False)


def test_a_body_without_variables_carries_no_example():
    clean = templates.check(template(body="Gracias por venir.", body_examples=[], header="", footer="", buttons=[]))

    assert templates.components(clean) == [{"type": "BODY", "text": "Gracias por venir."}]


def test_named_variables_pair_each_name_with_its_example():
    """saas#2281: a template of WhatsApp Manager with ``{{nombre}}`` can be edited from ERPlora."""
    clean = templates.check(template(body="Hola {{nombre}}, el {{dia}}. Hasta el {{dia}}.", body_examples=["Ana", "viernes"]))

    body = templates.components(clean)[1]
    assert body["example"] == {
        "body_text_named_params": [{"param_name": "nombre", "example": "Ana"}, {"param_name": "dia", "example": "viernes"}]
    }
    assert clean.named is True


@pytest.mark.parametrize(
    ("fields", "says"),
    [
        ({"name": "Recordatorio"}, "name"),
        ({"name": "con espacio"}, "name"),
        ({"category": "SALES"}, "category"),
        ({"language": ""}, "language"),
        ({"language": "español"}, "language"),
        ({"body": "  "}, "text"),
        ({"body": "x" * 1025, "body_examples": []}, "1024"),
        ({"header": "x" * 61}, "60"),
        ({"footer": "x" * 61}, "60"),
        ({"header": "Hola {{1}}"}, "header"),
        ({"footer": "Pie {{1}}"}, "footer"),
        ({"body": "Hola {{1}} y {{3}}", "body_examples": ["a", "b"]}, "{{1}}"),
        ({"body": "Hola {{1}}", "body_examples": []}, "example"),
        ({"body": "Hola {{1}}", "body_examples": ["a", "b"]}, "example"),
        ({"body": "Hola {{1}}", "body_examples": ["  "]}, "example"),
        ({"body": "Hola {{1}} y {{nombre}}", "body_examples": ["a", "b"]}, "both"),
        ({"body": "Hola {{Nombre}}", "body_examples": ["a"]}, "name"),
        ({"buttons": [{"type": "QUICK_REPLY", "text": "x" * 26}]}, "25"),
        ({"buttons": [{"type": "QUICK_REPLY", "text": ""}]}, "25"),
        ({"buttons": [{"type": "COPY_CODE", "text": "a"}]}, "QUICK_REPLY"),
        ({"buttons": [{"type": "URL", "text": "Web", "url": "ftp://x.example"}]}, "http"),
        ({"buttons": [{"type": "URL", "text": "Web", "url": "https://x.example/{{1}}"}]}, "http"),
        ({"buttons": [{"type": "PHONE_NUMBER", "text": "Llamar", "phone_number": "600111222"}]}, "+34"),
        ({"buttons": [{"type": "URL", "text": f"W{n}", "url": "https://x.example"} for n in range(3)]}, "2 link"),
        ({"buttons": [{"type": "PHONE_NUMBER", "text": f"L{n}", "phone_number": "+34600111222"} for n in range(2)]}, "1 call"),
        ({"buttons": [{"type": "QUICK_REPLY", "text": f"Q{n}"} for n in range(11)]}, "10"),
        (
            {"buttons": [{"type": "QUICK_REPLY", "text": "A"}, {"type": "URL", "text": "W", "url": "https://x.example"},
                         {"type": "QUICK_REPLY", "text": "B"}]},
            "together",
        ),
        ({"category": "AUTHENTICATION"}, "authentication"),
    ],
)
def test_each_rule_of_meta_says_what_is_wrong(fields, says):
    assert says in reason(**fields)


def test_the_buttons_keep_only_what_meta_reads():
    clean = templates.check(
        template(buttons=[{"type": "URL", "text": "Web", "url": "https://x.example", "extra": "x"},
                          {"type": "PHONE_NUMBER", "text": "Llamar", "phone_number": "+34600111222"}])
    )

    assert clean.buttons == [
        {"type": "URL", "text": "Web", "url": "https://x.example"},
        {"type": "PHONE_NUMBER", "text": "Llamar", "phone_number": "+34600111222"},
    ]


def test_metas_template_reads_back_as_the_mirror_keeps_it():
    item = {
        "id": "594425479261596",
        "name": "recordatorio",
        "language": "es",
        "category": "UTILITY",
        "status": "APPROVED",
        "components": [
            {"type": "HEADER", "format": "TEXT", "text": "Tu cita"},
            {"type": "BODY", "text": "Hola {{1}}, el {{2}}.", "example": {"body_text": [["Ana", "viernes"]]}},
            {"type": "FOOTER", "text": "Pie"},
            {"type": "BUTTONS", "buttons": [{"type": "QUICK_REPLY", "text": "Sí"}, {"type": "URL", "text": "Web", "url": "https://x.example"}]},
        ],
    }

    assert templates.from_meta(item) == {
        "name": "recordatorio", "language": "es", "category": "UTILITY", "status": "APPROVED", "rejected_reason": "",
        "meta_id": "594425479261596", "header_format": "TEXT", "header": "Tu cita", "body": "Hola {{1}}, el {{2}}.",
        "body_examples": ["Ana", "viernes"], "footer": "Pie",
        "buttons": [{"type": "QUICK_REPLY", "text": "Sí"}, {"type": "URL", "text": "Web", "url": "https://x.example"}],
        "variables": 2,
    }


def test_a_media_header_and_named_examples_read_back_too():
    item = {
        "id": "1", "name": "promo", "language": "es", "category": "MARKETING", "status": "REJECTED",
        "rejected_reason": "INVALID_FORMAT",
        "components": [
            {"type": "HEADER", "format": "IMAGE", "example": {"header_handle": ["4::aW1h"]}},
            {"type": "BODY", "text": "Hola {{nombre}}", "example": {"body_text_named_params": [{"param_name": "nombre", "example": "Ana"}]}},
        ],
    }

    mirror = templates.from_meta(item)

    assert (mirror["header_format"], mirror["header"], mirror["body_examples"], mirror["variables"]) == ("IMAGE", "", ["Ana"], 1)
    assert (mirror["status"], mirror["rejected_reason"]) == ("REJECTED", "INVALID_FORMAT")


def test_metas_none_reason_reads_as_no_reason():
    """Meta answers ``"rejected_reason": "NONE"`` for a template it did not reject."""
    item = {"id": "1", "name": "a", "language": "es", "status": "APPROVED", "rejected_reason": "NONE",
            "components": [{"type": "BODY", "text": "Hola"}]}

    assert templates.from_meta(item)["rejected_reason"] == ""


def test_a_template_meta_no_longer_has_reads_as_none():
    assert templates.from_meta({"id": "1", "name": "a", "language": "es", "status": "DELETED"}) is None
    assert templates.from_meta({"id": "1", "language": "es", "status": "APPROVED"}) is None
