"""Is this Spanish column written in Spanish, with its accents? (saas#2017, saas#2027)

Ported from ERPlora/saas ``public/blueprints/diacritics.py`` and ``public/catalog/spanish_copy.py``
(origin/develop). Two closed lists measure the ``_es`` columns of the taxonomy, never the ``_en``
ones («salon», «menu» and «cafe» are ordinary English words):

- **Folded Spanish** (``find_stripped_diacritics``): every key of ``SPANISH_WITHOUT_DIACRITICS`` is
  a spelling that is not a Spanish word at all without its diacritic, so a hit is always a defect.
  Words whose unaccented form is a word of its own are left out on purpose: ``unas`` (uñas),
  ``mas`` (más), ``ano`` (año), ``publico``/``articulo``/``deposito`` (verb forms). Their plurals,
  which are not verb forms, do make the list.
- **Untranslated English** (``english_function_words_in``): content words travel between the two
  languages in this catalogue («catering», «food truck», «spa»), function words do not. The list
  was measured against the 389 Spanish strings production served on 2026-09-11 and flags none of
  them; ``in``, ``out``, ``it`` and ``kitchen`` are left out because Spanish copy here uses them
  («check-in/out», «Servicios IT», «dark kitchen»).
"""

import re

from django.utils.translation import gettext

#: folded spelling (lowercase) -> how the word is actually written.
SPANISH_WITHOUT_DIACRITICS: dict[str, str] = {
    # ── trades and shop types: the names of the templates themselves ──
    "barberia": "barbería",
    "barberias": "barberías",
    "peluqueria": "peluquería",
    "peluquerias": "peluquerías",
    "pizzeria": "pizzería",
    "pizzerias": "pizzerías",
    "cafeteria": "cafetería",
    "cafeterias": "cafeterías",
    "panaderia": "panadería",
    "panaderias": "panaderías",
    "pasteleria": "pastelería",
    "pastelerias": "pastelerías",
    "heladeria": "heladería",
    "heladerias": "heladerías",
    "carniceria": "carnicería",
    "carnicerias": "carnicerías",
    "pescaderia": "pescadería",
    "pescaderias": "pescaderías",
    "fruteria": "frutería",
    "fruterias": "fruterías",
    "cerveceria": "cervecería",
    "cervecerias": "cervecerías",
    "floristeria": "floristería",
    "floristerias": "floristerías",
    "ferreteria": "ferretería",
    "ferreterias": "ferreterías",
    "joyeria": "joyería",
    "joyerias": "joyerías",
    "libreria": "librería",
    "librerias": "librerías",
    "papeleria": "papelería",
    "papelerias": "papelerías",
    "perfumeria": "perfumería",
    "perfumerias": "perfumerías",
    "zapateria": "zapatería",
    "zapaterias": "zapaterías",
    "lavanderia": "lavandería",
    "lavanderias": "lavanderías",
    "tintoreria": "tintorería",
    "tintorerias": "tintorerías",
    "salon": "salón",
    # ── the words the four cards actually lost ──
    "categoria": "categoría",
    "categorias": "categorías",
    "duracion": "duración",
    "comision": "comisión",
    "estacion": "estación",
    "facturacion": "facturación",
    "estetica": "estética",
    "esteticas": "estéticas",
    "generico": "genérico",
    "genericos": "genéricos",
    "generica": "genérica",
    "genericas": "genéricas",
    "ademas": "además",
    # ── -ción / -sión: the SINGULAR only. «sesiones» or «comisiones» carry no accent. ──
    "atencion": "atención",
    "autorizacion": "autorización",
    "configuracion": "configuración",
    "conexion": "conexión",
    "declaracion": "declaración",
    "descripcion": "descripción",
    "devolucion": "devolución",
    "direccion": "dirección",
    "division": "división",
    "exportacion": "exportación",
    "formacion": "formación",
    "gestion": "gestión",
    "habitacion": "habitación",
    "importacion": "importación",
    "impresion": "impresión",
    "informacion": "información",
    "integracion": "integración",
    "liquidacion": "liquidación",
    "notificacion": "notificación",
    "numeracion": "numeración",
    "operacion": "operación",
    "produccion": "producción",
    "promocion": "promoción",
    "reparacion": "reparación",
    "seleccion": "selección",
    "sesion": "sesión",
    "suscripcion": "suscripción",
    "ubicacion": "ubicación",
    "validacion": "validación",
    # ── everyday words of a shop window ──
    "analisis": "análisis",
    "articulos": "artículos",
    "automatico": "automático",
    "automatica": "automática",
    "automaticos": "automáticos",
    "automaticas": "automáticas",
    "basico": "básico",
    "basica": "básica",
    "basicos": "básicos",
    "basicas": "básicas",
    "cafe": "café",
    "cafes": "cafés",
    "codigo": "código",
    "codigos": "códigos",
    "credito": "crédito",
    "creditos": "créditos",
    "criticos": "críticos",
    "depositos": "depósitos",
    "dia": "día",
    "dias": "días",
    "economico": "económico",
    "economica": "económica",
    "electronico": "electrónico",
    "electronica": "electrónica",
    "electronicos": "electrónicos",
    "electronicas": "electrónicas",
    "fisico": "físico",
    "fisica": "física",
    "garantia": "garantía",
    "garantias": "garantías",
    "informatica": "informática",
    "logistica": "logística",
    "maximo": "máximo",
    "maximos": "máximos",
    "menu": "menú",
    "menus": "menús",
    "metodo": "método",
    "metodos": "métodos",
    "minimo": "mínimo",
    "minimos": "mínimos",
    "numeros": "números",
    "practicos": "prácticos",
    "proximo": "próximo",
    "proximos": "próximos",
    "publicos": "públicos",
    "rapido": "rápido",
    "rapida": "rápida",
    "rapidos": "rápidos",
    "rapidas": "rápidas",
    "segun": "según",
    "tambien": "también",
    "tecnico": "técnico",
    "tecnica": "técnica",
    "tecnicos": "técnicos",
    "tecnicas": "técnicas",
    "telefono": "teléfono",
    "telefonos": "teléfonos",
    "ultimo": "último",
    "ultimos": "últimos",
    "unico": "único",
    "unica": "única",
    "unicos": "únicos",
    "unicas": "únicas",
    # ── the taxonomy of sectors and activities (saas#2017) ──
    # 189 of its 190 Spanish strings reached production folded: «Barberia», «Panaderia /
    # Pasteleria», «Asesoria Fiscal», «Servicios de Automocion».
    "administracion": "administración",
    "alergenos": "alérgenos",
    "alimentacion": "alimentación",
    "almacen": "almacén",
    "asesoria": "asesoría",
    "asesorias": "asesorías",
    "asiatica": "asiática",
    "asignacion": "asignación",
    "automocion": "automoción",
    "carpinteria": "carpintería",
    "charcuteria": "charcutería",
    "clinica": "clínica",
    "clinicas": "clínicas",
    "clinico": "clínico",
    "comunicacion": "comunicación",
    "conduccion": "conducción",
    "confirmacion": "confirmación",
    "construccion": "construcción",
    "consultoria": "consultoría",
    "consultorias": "consultorías",
    "coordinacion": "coordinación",
    "creacion": "creación",
    "distribucion": "distribución",
    "ebanisteria": "ebanistería",
    "educacion": "educación",
    "electrico": "eléctrico",
    "envios": "envíos",
    "evolucion": "evolución",
    "examenes": "exámenes",
    "fabricacion": "fabricación",
    "fidelizacion": "fidelización",
    "financiacion": "financiación",
    "fisicos": "físicos",
    "fontaneria": "fontanería",
    "guias": "guías",
    "hosteleria": "hostelería",
    "huespedes": "huéspedes",
    "japones": "japonés",
    "loteria": "lotería",
    "matriculacion": "matriculación",
    "mecanico": "mecánico",
    "medicos": "médicos",
    "membresias": "membresías",
    "mensajeria": "mensajería",
    "movil": "móvil",
    "moviles": "móviles",
    "neumaticos": "neumáticos",
    "optimizacion": "optimización",
    "planificacion": "planificación",
    "porcion": "porción",
    "preparacion": "preparación",
    "psicologia": "psicología",
    "recepcion": "recepción",
    "rehabilitacion": "rehabilitación",
    "tabaqueria": "tabaquería",
    "tactiles": "táctiles",
    "teorico": "teórico",
    "tesoreria": "tesorería",
    "turistico": "turístico",
    "turisticos": "turísticos",
    "vehiculo": "vehículo",
    "vehiculos": "vehículos",
    "verduleria": "verdulería",
    # ── the ñ, which folding turns into a plain n ──
    "bano": "baño",
    "banos": "baños",
    "cumpleanos": "cumpleaños",
    "diseno": "diseño",
    "disenos": "diseños",
    "espanol": "español",
    "espanola": "española",
    "espanoles": "españoles",
    "manana": "mañana",
    "nino": "niño",
    "ninos": "niños",
    "pequeno": "pequeño",
    "pequena": "pequeña",
    "senor": "señor",
    "senora": "señora",
    "tamano": "tamaño",
    "tamanos": "tamaños",
}

#: A run of letters. ``\d`` and ``_`` are excluded so «check-in/out» and «hub_id» keep their shape.
_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)

#: English function words that Spanish does not use. Frozen on 2026-09-11.
ENGLISH_FUNCTION_WORDS = frozenset(
    {
        "about",
        "across",
        "after",
        "again",
        "all",
        "along",
        "also",
        "an",
        "and",
        "any",
        "are",
        "at",
        "be",
        "because",
        "been",
        "before",
        "being",
        "between",
        "both",
        "but",
        "by",
        "down",
        "during",
        "each",
        "every",
        "few",
        "for",
        "from",
        "had",
        "has",
        "have",
        "here",
        "how",
        "however",
        "if",
        "included",
        "including",
        "into",
        "is",
        "its",
        "just",
        "many",
        "more",
        "most",
        "much",
        "not",
        "of",
        "off",
        "on",
        "only",
        "onto",
        "or",
        "other",
        "others",
        "our",
        "over",
        "own",
        "same",
        "so",
        "some",
        "still",
        "such",
        "than",
        "that",
        "the",
        "their",
        "them",
        "then",
        "there",
        "therefore",
        "these",
        "they",
        "this",
        "those",
        "through",
        "to",
        "under",
        "up",
        "very",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "while",
        "who",
        "whose",
        "why",
        "with",
        "within",
        "without",
        "yet",
        "you",
        "your",
    }
)


def _matching_case(word: str, correct: str) -> str:
    """``correct`` written the way ``word`` was, so the report reads like the copy it fixes."""
    if word.isupper():
        return correct.upper()
    if word[:1].isupper():
        return correct[:1].upper() + correct[1:]
    return correct


def find_stripped_diacritics(text: str) -> list[tuple[str, str]]:
    """The ``(as written, as it should be)`` pairs of ``text``, in order, each word once."""
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for match in _WORD.finditer(text or ""):
        word = match.group()
        correct = SPANISH_WITHOUT_DIACRITICS.get(word.lower())
        if correct is None or word.lower() in seen:
            continue
        seen.add(word.lower())
        found.append((word, _matching_case(word, correct)))
    return found


def spanish_copy_complaint(text: str) -> str | None:
    """What to tell whoever typed ``text`` in a Spanish column, or ``None`` when its accents are fine."""
    found = find_stripped_diacritics(text)
    if not found:
        return None
    listed = ", ".join(f"«{word}» → «{correct}»" for word, correct in found)
    return gettext("This Spanish copy lost its accents: %(words)s.") % {"words": listed}


def english_function_words_in(text: str) -> set[str]:
    """The English function words ``text`` uses, lowercased. Empty when it reads as Spanish."""
    return {word.lower() for word in _WORD.findall(text or "")} & ENGLISH_FUNCTION_WORDS


def untranslated_copy_complaint(text: str) -> str | None:
    """Why ``text`` does not belong in a Spanish column, or ``None`` when it does."""
    words = english_function_words_in(text)
    if not words:
        return None
    listed = ", ".join(f"«{word}»" for word in sorted(words))
    return gettext("This is English (%(words)s): the Spanish column takes the translation, not the copy.") % {
        "words": listed
    }
