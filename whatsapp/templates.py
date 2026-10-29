"""A business's template as Meta takes it and as Meta gives it back (WHATSAPP-G15, WHATSAPP-G17).

Meta answers a malformed template with a generic error the business reads as «it did not work», so its rules
are checked here before the call (``check``), each one refused with a sentence that names what is wrong; the
Hub shows it as the reason of its 409 ``whatsapp.template_invalid``. Only what the Hub's door 8 can write
travels: a text header without variables or a header with a photo, a video or a document (its sample file), a
body numbered ``{{1}}…{{n}}`` or named ``{{name}}`` with one example each, a footer and quick reply, link or call
buttons. An authentication template (Meta's one-time codes) needs parts this door has no field for, so it is
refused by name rather than half-registered.

A header's file is told by its first bytes, never by its name or a declared type (``sniff``): a JPEG or PNG photo up
to 5 MB and an MP4 video up to 16 MB, Meta's limits; a PDF document up to 25 MB, the Hub's ceiling for a file it
keeps (``base.files.MAX_FILE_BYTES``; Meta takes up to 100 MB). Anything else Meta answers with a generic error.

``mirror`` and ``from_meta`` give a template as the mirror (``models.Template``) keeps it: the one Meta just took,
and one of Meta's list.
"""

import base64
import binascii
import re
from dataclasses import dataclass, field
from itertools import pairwise

from whatsapp import parse
from whatsapp.schemas import TemplateIn

#: Meta's rule for a template's name and for a named variable: lowercase letters, digits and underscores.
NAME_RE = re.compile(r"^[a-z0-9_]{1,512}$")
PARAM_NAME_RE = re.compile(r"^[a-z0-9_]+$")
#: Meta's language codes: ``es``, ``en_US``, ``zh_HK``, ``pt_BR``…
LANGUAGE_RE = re.compile(r"^[a-z]{2,3}(_[A-Za-z]{2,4})?$")
#: Any ``{{…}}``: a number is a positional variable, anything else a named one.
PLACEHOLDER_RE = re.compile(r"\{\{([^{}]*)\}\}")
CATEGORIES = ("UTILITY", "MARKETING")
MAX_HEADER = 60
MAX_BODY = 1024
MAX_FOOTER = 60
MAX_BUTTONS = 10
MAX_URL_BUTTONS = 2
MAX_PHONE_BUTTONS = 1
MAX_BUTTON_TEXT = 25
MAX_BUTTON_URL = 2000
CALL_TO_ACTION = ("URL", "PHONE_NUMBER")
#: A call button's number as Meta takes it: country code first, digits only once spaces are gone.
PHONE_RE = re.compile(r"^\+[1-9]\d{6,14}$")
MB = 1024 * 1024
#: The headers that carry a file, and what each takes: the file types a person reads and the largest file.
FILE_HEADERS = ("IMAGE", "VIDEO", "DOCUMENT")
SAMPLE_TYPES = {"IMAGE": "JPEG or PNG", "VIDEO": "MP4", "DOCUMENT": "PDF"}
MAX_SAMPLE = {"IMAGE": 5 * MB, "VIDEO": 16 * MB, "DOCUMENT": 25 * MB}
#: The heaviest file a header carries (door 8's body is sized for it in base64).
MAX_SAMPLE_BYTES = max(MAX_SAMPLE.values())
#: The MP4 brands of an ``ftyp`` box; a 3GPP file shares the box, but Meta's sample must be MP4.
MP4_BRANDS = (b"isom", b"iso2", b"iso4", b"iso5", b"iso6", b"mp41", b"mp42", b"avc1", b"dash", b"M4V ", b"MSNV")


class Invalid(ValueError):
    """The template breaks one of Meta's rules; the message says which, for the business."""


@dataclass(frozen=True)
class Sample:
    """A header's file as Meta's upload takes it: the name it shows, its type and its bytes."""

    name: str
    mime_type: str
    content: bytes


@dataclass(frozen=True)
class Clean:
    name: str
    language: str
    category: str
    header: str
    body: str
    examples: list[str]
    footer: str
    buttons: list[dict]
    #: How many distinct variables the body has.
    variables: int
    #: Whether they are named (``{{name}}``) rather than numbered.
    named: bool
    #: For a named body: each distinct name, in the order the body first uses it, paired with ``examples``.
    param_names: list[str] = field(default_factory=list)
    #: ``""``, ``TEXT`` or one of ``FILE_HEADERS``; the file of a file header.
    header_format: str = ""
    sample: Sample | None = None


def check(template: TemplateIn) -> Clean:
    """Refuse here everything Meta would refuse there, cheap identity checks first, so a template that breaks two
    rules is reported by the one the business can act on first."""
    name = template.name.strip()
    if not NAME_RE.match(name):
        raise Invalid("The template's name takes lowercase letters, digits and underscores only.")
    category = template.category.strip().upper()
    if category == "AUTHENTICATION":
        raise Invalid("Meta's authentication templates (one-time codes) cannot be registered from here.")
    if category not in CATEGORIES:
        raise Invalid("The category is UTILITY or MARKETING.")
    language = template.language.strip()
    if not LANGUAGE_RE.match(language):
        raise Invalid("The language is one of Meta's codes (es, en_US…).")

    body = template.body.strip()
    if not body:
        raise Invalid("The template needs its text.")
    if len(body) > MAX_BODY:
        raise Invalid(f"The text is at most {MAX_BODY} characters.")
    header = template.header.strip()
    header_format = template.header_format.strip().upper()
    sample = None
    if header_format in FILE_HEADERS:
        if header:
            raise Invalid("A header with a photo, a video or a document has no text.")
        sample = _sample(template.header_sample, header_format)
    elif header_format in ("", "TEXT"):
        if len(header) > MAX_HEADER:
            raise Invalid(f"The header is at most {MAX_HEADER} characters.")
        if PLACEHOLDER_RE.search(header):
            raise Invalid("The header takes no variables.")
        header_format = "TEXT" if header else ""
    else:
        raise Invalid("The header is a text, a photo, a video or a document.")
    footer = template.footer.strip()
    if len(footer) > MAX_FOOTER:
        raise Invalid(f"The footer is at most {MAX_FOOTER} characters.")
    if PLACEHOLDER_RE.search(footer):
        raise Invalid("The footer takes no variables.")

    tokens = [token.strip() for token in PLACEHOLDER_RE.findall(body)]
    numbers = [int(token) for token in tokens if token.isdigit()]
    names = [token for token in tokens if not token.isdigit()]
    if numbers and names:
        raise Invalid("Use {{1}}…{{n}} or {{name}} for the variables, not both.")
    if any(not PARAM_NAME_RE.match(name) for name in names):
        raise Invalid("Variable names take lowercase letters, digits and underscores only.")
    distinct = sorted(set(numbers))
    if distinct != list(range(1, len(distinct) + 1)):
        raise Invalid("Variables are numbered {{1}}, {{2}}… without gaps.")
    param_names = list(dict.fromkeys(names))
    count = len(param_names) if names else len(distinct)
    examples = [example.strip() for example in template.body_examples]
    if len(examples) != count or not all(examples):
        raise Invalid("Meta needs one example per variable, and no more.")

    return Clean(
        name=name,
        language=language,
        category=category,
        header=header,
        body=body,
        examples=examples,
        footer=footer,
        buttons=_buttons(template.buttons),
        variables=count,
        named=bool(names),
        param_names=param_names,
        header_format=header_format,
        sample=sample,
    )


def sniff(head: bytes) -> tuple[str, str] | None:
    """The header kind and the type of a file Meta takes as a sample that these first bytes start, or None."""
    if head.startswith(b"\xff\xd8\xff"):
        return "IMAGE", "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "IMAGE", "image/png"
    if head.startswith(b"%PDF-"):
        return "DOCUMENT", "application/pdf"
    if head[4:8] == b"ftyp" and head[8:12] in MP4_BRANDS:
        return "VIDEO", "video/mp4"
    return None


def _sample(raw, header_format: str) -> Sample:
    """The header's file, if it is one Meta takes for ``header_format``."""
    if raw is None or not raw.content_base64:
        raise Invalid("A header with a photo, a video or a document needs its file.")
    try:
        content = base64.b64decode(raw.content_base64, validate=True)
    except (binascii.Error, ValueError):
        raise Invalid("The header's file did not arrive whole.") from None
    kind = sniff(content[:16])
    types = SAMPLE_TYPES[header_format]
    if kind is None or kind[0] != header_format:
        raise Invalid(f"This header takes a {types} file.")
    limit = MAX_SAMPLE[header_format]
    if len(content) > limit:
        raise Invalid(f"The header's {types} file is {limit // MB} MB at most.")
    return Sample(name=_file_name(raw.name), mime_type=kind[1], content=content)


def _file_name(name: str) -> str:
    """The name Meta shows for the sample: the base name, without a path or control characters."""
    base = (name or "").replace("\\", "/").rsplit("/", 1)[-1]
    return "".join(ch for ch in base if ch.isprintable())[:200] or "sample"


def _buttons(raw: list[dict]) -> list[dict]:
    if len(raw) > MAX_BUTTONS:
        raise Invalid(f"At most {MAX_BUTTONS} buttons.")
    buttons: list[dict] = []
    for item in raw:
        kind = str(item.get("type") or "").strip().upper()
        if kind not in ("QUICK_REPLY", *CALL_TO_ACTION):
            raise Invalid("Buttons are QUICK_REPLY, URL or PHONE_NUMBER.")
        text = str(item.get("text") or "").strip()
        if not text or len(text) > MAX_BUTTON_TEXT:
            raise Invalid(f"A button's label is 1 to {MAX_BUTTON_TEXT} characters.")
        button = {"type": kind, "text": text}
        if kind == "URL":
            url = str(item.get("url") or "").strip()
            if (
                not url.lower().startswith(("https://", "http://"))
                or len(url) > MAX_BUTTON_URL
                or PLACEHOLDER_RE.search(url)
            ):
                raise Invalid(f"A link button takes a fixed http(s) address of up to {MAX_BUTTON_URL} characters.")
            button["url"] = url
        elif kind == "PHONE_NUMBER":
            phone = re.sub(r"[\s().-]", "", str(item.get("phone_number") or ""))
            if not PHONE_RE.match(phone):
                raise Invalid("A call button's number starts with its country code (+34…).")
            button["phone_number"] = phone
        buttons.append(button)
    if sum(button["type"] == "URL" for button in buttons) > MAX_URL_BUTTONS:
        raise Invalid(f"At most {MAX_URL_BUTTONS} link buttons.")
    if sum(button["type"] == "PHONE_NUMBER" for button in buttons) > MAX_PHONE_BUTTONS:
        raise Invalid(f"At most {MAX_PHONE_BUTTONS} call button.")
    groups = [button["type"] in CALL_TO_ACTION for button in buttons]
    if sum(a != b for a, b in pairwise(groups)) > 1:
        raise Invalid("Quick replies go together, and links and calls together.")
    return buttons


def components(clean: Clean, header_handle: str = "") -> list[dict]:
    """The ``components`` Meta documents for a template, with the examples its review asks for: a file header's is
    the ``header_handle`` of its sample, uploaded first (``meta.upload_sample``)."""
    result: list[dict] = []
    if clean.header_format in FILE_HEADERS:
        result.append({"type": "HEADER", "format": clean.header_format, "example": {"header_handle": [header_handle]}})
    elif clean.header:
        result.append({"type": "HEADER", "format": "TEXT", "text": clean.header})
    body: dict = {"type": "BODY", "text": clean.body}
    if clean.named:
        body["example"] = {
            "body_text_named_params": [
                {"param_name": name, "example": example}
                for name, example in zip(clean.param_names, clean.examples, strict=True)
            ]
        }
    elif clean.examples:
        body["example"] = {"body_text": [clean.examples]}
    result.append(body)
    if clean.footer:
        result.append({"type": "FOOTER", "text": clean.footer})
    if clean.buttons:
        result.append({"type": "BUTTONS", "buttons": clean.buttons})
    return result


def mirror(clean: Clean, *, meta_id: str, status: str, category: str) -> dict:
    """A template Meta took (``meta_id``, its verdict and the category it settled on) as the mirror keeps it: what
    was sent, until Meta's list or its webhook says otherwise. An edit goes back to review, so no old reason stays."""
    return {
        "name": clean.name,
        "language": clean.language,
        "category": (category or clean.category).upper(),
        "status": parse.hub_verdict(status) or "PENDING",
        "rejected_reason": "",
        "meta_id": meta_id,
        "header_format": clean.header_format,
        "header": clean.header,
        "body": clean.body,
        "body_examples": clean.examples,
        "footer": clean.footer,
        "buttons": clean.buttons,
        "variables": clean.variables,
    }


def from_meta(item: dict) -> dict | None:
    """One template of Meta's list (``id, name, language, category, status, rejected_reason, components``) as the
    mirror keeps it; ``None`` when it has no name or language, or Meta no longer has it."""
    name = str(item.get("name") or "").strip()
    language = str(item.get("language") or "").strip()
    status = parse.hub_verdict(str(item.get("status") or ""))
    if not name or not language or status is None:
        return None
    parts = {
        str(component.get("type") or "").upper(): component
        for component in item.get("components") or []
        if isinstance(component, dict)
    }
    header, body = parts.get("HEADER", {}), parts.get("BODY", {})
    header_format = str(header.get("format") or "").upper()
    text = str(body.get("text") or "")
    tokens = [token.strip() for token in PLACEHOLDER_RE.findall(text)]
    reason = str(item.get("rejected_reason") or "")
    return {
        "name": name,
        "language": language,
        "category": str(item.get("category") or "UTILITY").upper(),
        "status": status,
        "rejected_reason": "" if reason.upper() == "NONE" else reason[:500],
        "meta_id": str(item.get("id") or ""),
        "header_format": header_format,
        "header": str(header.get("text") or "") if header_format == "TEXT" else "",
        "body": text,
        "body_examples": _examples(body.get("example")),
        "footer": str(parts.get("FOOTER", {}).get("text") or ""),
        "buttons": [
            {key: str(button[key]) for key in ("type", "text", "url", "phone_number") if key in button}
            for button in parts.get("BUTTONS", {}).get("buttons") or []
            if isinstance(button, dict)
        ],
        "variables": len(set(tokens)),
    }


def _examples(example) -> list[str]:
    if not isinstance(example, dict):
        return []
    named = example.get("body_text_named_params")
    if isinstance(named, list):
        return [str(param.get("example") or "") for param in named if isinstance(param, dict)]
    rows = example.get("body_text")
    if isinstance(rows, list) and rows and isinstance(rows[0], list):
        return [str(value) for value in rows[0]]
    return []
