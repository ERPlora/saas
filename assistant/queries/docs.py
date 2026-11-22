"""The documentation of the panel's assistant.

- ``assistant.docs.search``: the excerpts of ERPlora's documentation nearest to a how-to question, a tool of
  the panel's assistant for every account; ``assistant.docs.list``, the hashes ``index_docs`` already has.
"""

import hashlib
import logging

import httpx
from asgiref.sync import sync_to_async
from django.core.cache import cache
from django.db.models import Q
from django.utils import translation
from django.utils.translation import gettext as _
from live.context import OperationContext, Scope, system_context
from live.errors import Conflict, OperationError
from live.operations import AI, INTERNAL, operation
from pgvector.django import CosineDistance

from assistant import media
from base.surface import sells_nothing
from assistant.models import DocChunk
from assistant.queries.gates import platform_only
from assistant.queries.provider_keys import service_connection, services_provider
from assistant.schemas import DocsListOut, DocsSearchIn, DocsSearchOut, DocsSourceIn, NoInput

logger = logging.getLogger("assistant.queries")


@operation(
    "assistant.docs.list",
    kind="query",
    permission="assistant.manage",
    input=DocsSourceIn,
    output=DocsListOut,
    ai=INTERNAL,  # platform
)
def docs_list(ctx: OperationContext, data: DocsSourceIn) -> dict:
    """The hash of every excerpt ``source`` has in the index: what ``index_docs`` does not embed again (the platform
    only)."""
    platform_only(ctx)
    return {"hashes": list(DocChunk.objects.filter(source=data.source).values_list("content_hash", flat=True))}


#: An excerpt this close to the question (cosine distance: 0 is the same meaning, 1 nothing in common) answers it.
CLOSE = 0.55
#: With fewer close excerpts than this in the person's language, the English ones join.
ENOUGH = 3
#: How long the fingerprint of a question is kept.
QUESTION_CACHE_SECONDS = 60 * 60 * 24
#: The wait for a question's fingerprint: the panel's turn waits on it before its operation runs.
SEARCH_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)
#: The longest question a search takes (``DocsSearchIn``).
QUESTION_MAX = 500


#: The manuals that are about what ERPlora sells (paying, the store, the prices on the web): where nothing is sold they
#: are not read, nor the plans. What they say of invoices has its tools and its screen there.
SELLING_WORKBOOKS = tuple(
    f"{app}/{name}" for app in ("billing", "apps", "public") for name in ("WORKBOOK.md", "WORKBOOK.en.md")
)


def docs_language(language: str) -> str:
    """The language of the documentation a person reads: Spanish for any Spanish, English for any other."""
    return "es" if media.base_language(language or "") == "es" else "en"


def question_key(query: str) -> str:
    """Where the fingerprint of ``query`` is kept: by the hash of the question as it was asked, spaces and case
    aside."""
    asked = " ".join(query.split()).casefold()
    return f"assistant:docs:question:{media.EMBEDDING_MODEL}:{hashlib.sha256(asked.encode()).hexdigest()}"


async def prepare_questions(questions: list[str]) -> None:
    """The fingerprints of ``questions`` not kept yet, computed in one call and kept a day: what
    ``assistant.docs.search`` reads. Called before any transaction opens (the panel's turn does it for every search
    the model asked for), so no connection waits on the provider inside one. It never fails: without the services'
    provider, or when it fails, the search itself says so (409 or 503)."""
    wanted: dict[str, str] = {}
    for question in questions:
        question = (question or "").strip() if isinstance(question, str) else ""
        if question and len(question) <= QUESTION_MAX:
            wanted.setdefault(question_key(question), question)
    if not wanted:
        return
    known = await cache.aget_many(list(wanted))
    missing = {key: question for key, question in wanted.items() if key not in known}
    if not missing:
        return
    try:
        service = await sync_to_async(service_connection)(
            system_context(Scope("platform", "assistant")), NoInput()
        )
    except OperationError as refused:
        logger.warning("assistant.docs.question_not_prepared code=%s", refused.code)
        return
    try:
        vectors, _tokens = await media.embed(service, list(missing.values()), timeout=SEARCH_TIMEOUT)
    except media.MediaFailed as problem:
        logger.warning("assistant.docs.question_not_prepared code=%s", problem.code)
        return
    await cache.aset_many(dict(zip(missing, vectors, strict=True)), QUESTION_CACHE_SECONDS)


def nearest(vector: list[float], language: str, limit: int, *, sells: bool = True) -> list[DocChunk]:
    """The ``limit`` excerpts of ``language`` nearest to ``vector``, exactly: the table has no approximate index, on
    purpose (``DocChunk``), because the excerpts of a language behind 40 nearer ones of the other would be lost. Where
    nothing is sold (``sells``), none of what only sells."""
    excerpts = DocChunk.objects.filter(lang=language)
    if not sells:
        excerpts = excerpts.exclude(
            Q(source=DocChunk.Source.PLANS) | Q(source=DocChunk.Source.WORKBOOK, path__in=SELLING_WORKBOOKS)
        )
    return list(
        excerpts.annotate(distance=CosineDistance("embedding", vector))
        .order_by("distance", "path", "heading")[:limit]
    )


@operation(
    "assistant.docs.search",
    kind="query",
    permission="assistant.ask",
    input=DocsSearchIn,
    output=DocsSearchOut,
    ai=AI(
        description=(
            "Searches ERPlora's help, the documentation of its apps and the plans for how-to questions: returns up to "
            "8 cited excerpts. Not for live data of the account."
        ),
        asks={
            "en": (
                "how do I set up the kitchen printer?",
                "what's the difference between Free and Starter?",
                "is VeriFactu included?",
                "how do I invite someone to my business?",
                "how do I connect WhatsApp to my business?",
            ),
            "es": (
                "¿cómo configuro la impresora de cocina?",
                "¿qué diferencia hay entre el plan Gratis y el Starter?",
                "¿qué es VeriFactu?",
                "¿cómo invito a un empleado?",
            ),
        },
    ),
)
def docs_search(ctx: OperationContext, data: DocsSearchIn) -> dict:
    """The excerpts of ERPlora's documentation nearest to ``query``, in the person's language, with the English ones
    when fewer than ``ENOUGH`` of those are close (``CLOSE``); at most ``limit``. It never calls the provider: the
    question's fingerprint was computed before, outside its transaction (``prepare_questions``). 409
    ``assistant.provider_not_configured`` without the services' provider; 503 ``assistant.provider_unavailable``
    when the fingerprint could not be computed."""
    vector = cache.get(question_key(data.query))
    if vector is None:
        with translation.override(ctx.language):
            if services_provider() is None:
                raise Conflict(
                    _("ERPlora's documentation cannot be searched now: the provider of the embeddings is not configured."),
                    code="assistant.provider_not_configured",
                )
            raise OperationError(
                _("ERPlora's documentation cannot be searched now: try again in a moment."),
                code="assistant.provider_unavailable",
                status=503,
            )
    language = docs_language(ctx.language)
    sells = not sells_nothing(getattr(ctx, "request", None))
    found = nearest(vector, language, data.limit, sells=sells)
    if language != "en" and sum(row.distance < CLOSE for row in found) < ENOUGH:
        found = sorted(
            [*found, *nearest(vector, "en", data.limit, sells=sells)],
            key=lambda row: (row.distance, row.lang != language),
        )[: data.limit]
    return {
        "results": [
            {
                "source": row.source,
                "path": row.path,
                "heading": row.heading,
                "text": row.text,
                "score": round(1 - row.distance, 4),
                "lang": row.lang,
            }
            for row in found
        ]
    }
