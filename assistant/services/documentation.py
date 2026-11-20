"""The documentation of the panel's assistant.

- ``assistant.docs.index``: a batch of what one source of the documentation has now (``index_docs``): its excerpts
  that no longer exist go, the ones just embedded are written with their fingerprint.
"""

from django.utils import timezone, translation
from django.utils.translation import gettext as _
from live.context import OperationContext
from live.errors import OperationError
from live.operations import INTERNAL, operation
from live.outbox import record_event

from assistant import events, queries
from assistant.models import DocChunk, content_hash
from assistant.schemas import DocsIndexIn, DocsIndexOut


@operation(
    "assistant.docs.index",
    kind="command",
    permission="assistant.manage",
    input=DocsIndexIn,
    output=DocsIndexOut,
    ai=INTERNAL,  # platform
)
def docs_index(ctx: OperationContext, data: DocsIndexIn) -> dict:
    """A batch of what ``source`` has now, in one transaction (the platform only: ``index_docs``): with ``keep``, its
    excerpts whose hash is not there go; each of ``chunks`` is written with its fingerprint, new or over the one it
    had (``--full``). The hash of an excerpt is computed here, never taken from the caller."""
    queries.gates.platform_only(ctx)
    keep = None if data.keep is None else set(data.keep)
    deleted = 0
    if keep is not None:
        deleted = DocChunk.objects.filter(source=data.source).exclude(content_hash__in=keep).delete()[0]
    now = timezone.now()
    rows = {}
    for chunk in data.chunks:
        digest = content_hash(data.source, chunk.path, chunk.lang, chunk.heading, chunk.text)
        if keep is not None and digest not in keep:
            with translation.override(ctx.language):
                raise OperationError(
                    _("An excerpt to write is not among the ones the source keeps."), code="assistant.docs_not_kept", status=422
                )
        rows[digest] = DocChunk(
            source=data.source,
            path=chunk.path,
            lang=chunk.lang,
            heading=chunk.heading,
            text=chunk.text,
            content_hash=digest,
            embedding=chunk.embedding,
            indexed_at=now,
        )
    DocChunk.objects.bulk_create(
        rows.values(), update_conflicts=True, unique_fields=["content_hash"], update_fields=["embedding", "indexed_at"]
    )
    counts = {"chunks": DocChunk.objects.filter(source=data.source).count(), "embedded": len(rows), "deleted": deleted}
    record_event(ctx, events.DOCS_INDEXED, {"source": data.source, **counts})
    return {"source": data.source, **counts}
