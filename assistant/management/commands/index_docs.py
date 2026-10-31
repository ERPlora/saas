"""Keep the documentation the panel's assistant searches (ASSISTANT-F27; plan 2026-10-30-asistente-saas §5).

Every excerpt of the four sources of ``assistant.knowledge`` (the public help, the user documentation of the Hub's
apps, the customer's part of the panel's WORKBOOKs and the plans on sale) is kept in ``assistant.DocChunk`` with its
fingerprint, one source at a time (``assistant.docs.index``, one transaction per batch). Idempotent by the hash of each
excerpt: only a new one is embedded, in batches of ``BATCH`` texts by the services' provider
(``ASSISTANT_SERVICE_PROVIDER``), each written before the next is asked for (a run holds one batch of fingerprints:
saas-cron has 512 MB), and one that no longer exists goes with the last batch; a run without changes calls nobody. Its cost is
ERPlora's own, not an account's (no ``AssistantUsage``): each source ends with one line of what it spent, in the log
and on the screen. Daily on ``saas-cron`` and once by hand after the first deploy (``saas/README.md``).

    python manage.py index_docs
    python manage.py index_docs --dry-run   # what would be embedded and deleted; writes and calls nothing
    python manage.py index_docs --full      # every excerpt embedded again (another model of fingerprints)

Without the services' provider (or its key) it ends with exit code 2 and writes nothing; a provider that fails ends
the run with an error, keeping what was embedded before it and every old excerpt (the next run does the rest). Under the advisory lock of its name: a second run
returns at once.
"""

import logging
from decimal import Decimal

from asgiref.sync import async_to_sync
from django.core.management.base import BaseCommand, CommandError
from live.errors import OperationError

from assistant import knowledge, media, queries, services
from assistant.schemas import DocChunkIn, DocsIndexIn, DocsSourceIn, NoInput
from hubs.services import run_exclusively

logger = logging.getLogger("assistant.index_docs")

#: The texts of one call to the provider.
BATCH = 64
#: The exit code of a run without the services' provider: nothing was tried, so retrying changes nothing.
NO_PROVIDER = 2


def unique(chunks: list[knowledge.Chunk]) -> list[knowledge.Chunk]:
    """The excerpts of a source, each once and in order (the same section twice in a file is one excerpt)."""
    return list(dict.fromkeys(chunks))


class Command(BaseCommand):
    help = "Index ERPlora's documentation for the panel's assistant, embedding only what changed (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--full", action="store_true", help="Embed every excerpt again, not only the new ones.")
        parser.add_argument("--dry-run", action="store_true", help="Count what would be embedded and deleted.")

    def handle(self, *args, full, dry_run, **options):
        with run_exclusively("index_docs") as mine:
            if not mine:
                self.stdout.write("index_docs: already running, nothing done.")
                return
            ctx = services.platform_context()
            service = None if dry_run else self._service(ctx)
            for source in knowledge.SOURCES:
                self._index(ctx, service, source, full=full, dry_run=dry_run)

    def _service(self, ctx):
        try:
            return queries.service_connection(ctx, NoInput())
        except OperationError as refused:
            if refused.code != "assistant.provider_not_configured":
                raise CommandError(refused.message) from None
            raise CommandError(
                f"{refused.message} index_docs computes the fingerprints with it: nothing was indexed.",
                returncode=NO_PROVIDER,
            ) from None

    def _index(self, ctx, service, source: str, *, full: bool, dry_run: bool) -> None:
        chunks = unique(knowledge.collect(source))
        known = set(queries.docs_list(ctx, DocsSourceIn(source=source)).hashes)
        wanted = {chunk.content_hash for chunk in chunks}
        new = chunks if full else [chunk for chunk in chunks if chunk.content_hash not in known]
        if dry_run:
            self.stdout.write(
                f"(dry run) assistant.index_docs source={source} chunks={len(chunks)} embedded={len(new)} "
                f"deleted={len(known - wanted)}"
            )
            return
        embedded = deleted = tokens = 0
        # One batch at a time, embedded then written: a run holds one batch of fingerprints, whatever the source has.
        # The last call also says what the source keeps, so its excerpts that no longer exist go only once every new
        # one is written: a run that fails halfway leaves a changed document searchable by its old excerpts (with
        # nothing new, that call alone).
        for start in range(0, max(len(new), 1), BATCH):
            batch = new[start : start + BATCH]
            vectors, spent = self._embed(service, source, batch) if batch else ([], 0)
            out = services.docs_index(
                ctx,
                DocsIndexIn(
                    source=source,
                    keep=sorted(wanted) if start + BATCH >= len(new) else None,
                    chunks=[
                        DocChunkIn(path=chunk.path, lang=chunk.lang, heading=chunk.heading, text=chunk.text, embedding=vector)
                        for chunk, vector in zip(batch, vectors, strict=True)
                    ],
                ),
            )
            embedded, deleted, tokens = embedded + out.embedded, deleted + out.deleted, tokens + spent
        cost = media.embedding_cost(tokens).quantize(Decimal("0.000001"))
        line = (
            f"assistant.index_docs source={source} chunks={out.chunks} embedded={embedded} deleted={deleted} "
            f"tokens={tokens} cost_usd={cost}"
        )
        logger.info(line)
        self.stdout.write(line)

    def _embed(self, service, source: str, batch: list[knowledge.Chunk]) -> tuple[list[list[float]], int]:
        try:
            return async_to_sync(media.embed)(service, [chunk.embedding_text for chunk in batch])
        except media.MediaFailed as problem:
            logger.warning("assistant.index_docs.failed source=%s code=%s", source, problem.code)
            raise CommandError(
                f"{source}: the provider of the embeddings failed ({problem.code}); what was embedded before stays. "
                "Run index_docs again to finish."
            ) from None
