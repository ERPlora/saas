"""ASSISTANT-F27 · ``index_docs`` keeps the documentation the panel's assistant searches (plan 2026-10-30-asistente-saas
§5): every excerpt of the four sources (``assistant.knowledge``) in ``assistant.DocChunk`` with its fingerprint.

Idempotent by the hash of each excerpt: a second run embeds nothing, a changed section is the only one embedded again
and an excerpt that no longer exists goes. The fingerprints come from the services' provider
(``ASSISTANT_SERVICE_PROVIDER``), in batches of ``BATCH`` texts, and their cost is ERPlora's own (no
``AssistantUsage``): each source ends with one line of what it cost. Without the provider it ends with exit code 2 and
writes nothing; ``--dry-run`` counts and writes nothing; ``--full`` embeds every excerpt again. A run holds the
advisory lock of its name: a second one returns at once. The provider is the local fake.
"""

import logging
from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from live.models import OutboxEvent

from assistant import knowledge
from assistant.media import EMBEDDING_MODEL
from assistant.models import EMBEDDING_DIMENSIONS, AssistantUsage, DocChunk
from assistant.tests.conftest import answering, fake_provider, provider  # noqa: F401 - the gateway's fixtures
from base.tests.conftest import other_session  # noqa: F401 - a second session, as another saas-cron task
from hubs.tests.conftest import plans  # noqa: F401 - the catalogue of plans

pytestmark = pytest.mark.django_db

EMBEDDINGS = "/v1/embeddings"
LOCK_KEY = "hashtext('erplora.saas.index_docs')"

GUIDE = """# Getting started

Sign in with the email of your account.

## The first time

Open erplora.com and choose Sign in.

## Signing in again

Type your PIN.
"""


def vector(seed: int) -> list[float]:
    return [1.0 if index == seed % EMBEDDING_DIMENSIONS else 0.001 for index in range(EMBEDDING_DIMENSIONS)]


def embeddings_for(body) -> dict:
    """The fake's answer to a batch: one vector per text, ten tokens each."""
    texts = body["input"]
    data = [{"object": "embedding", "index": index, "embedding": vector(index)} for index in range(len(texts))]
    tokens = 10 * len(texts)
    return {"object": "list", "data": data, "model": EMBEDDING_MODEL, "usage": {"prompt_tokens": tokens, "total_tokens": tokens}}


@pytest.fixture
def embedder(answering, fake_provider):
    """OpenAI on the fake, with its key: every batch answered with its vectors."""
    fake_provider.reply("POST", EMBEDDINGS, always=True, answer=embeddings_for)
    return fake_provider


@pytest.fixture
def docs(settings, tmp_path, plans):
    """A project with one guide in English and nothing else to read but the plans of the database."""
    settings.BASE_DIR = tmp_path
    write(tmp_path, "docs/en/help/01-getting-started.md", GUIDE)
    return tmp_path


def write(root, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def batches(fake_provider) -> list[int]:
    """How many texts each call to the provider carried."""
    return [len(seen.body["input"]) for seen in fake_provider.requests if seen.path == EMBEDDINGS]


def run(*args) -> str:
    out = StringIO()
    call_command("index_docs", *args, stdout=out)
    return out.getvalue()


def help_rows() -> list[DocChunk]:
    return list(DocChunk.objects.filter(source="help").order_by("heading"))


def plan_excerpts() -> int:
    return len(knowledge.collect("plans"))


class TestTheFirstRun:
    def test_every_excerpt_is_kept_with_its_fingerprint(self, docs, embedder):
        run()

        rows = help_rows()
        assert [(row.path, row.lang, row.heading, row.text) for row in rows] == [
            ("docs/en/help/01-getting-started.md", "en", "Getting started", "Sign in with the email of your account."),
            ("docs/en/help/01-getting-started.md", "en", "Getting started > Signing in again", "Type your PIN."),
            ("docs/en/help/01-getting-started.md", "en", "Getting started > The first time", "Open erplora.com and choose Sign in."),
        ]
        assert all(len(row.embedding) == EMBEDDING_DIMENSIONS for row in rows)
        assert {row.content_hash for row in rows} == {chunk.content_hash for chunk in knowledge.collect("help")}
        assert DocChunk.objects.filter(source="plans").count() == plan_excerpts() > 0

    def test_what_is_embedded_is_each_excerpt_with_its_headings(self, docs, embedder):
        run()

        [help_batch] = [seen.body for seen in embedder.requests if "Type your PIN." in str(seen.body["input"])]
        assert help_batch["model"] == EMBEDDING_MODEL
        assert "Getting started > Signing in again\nType your PIN." in help_batch["input"]

    def test_each_source_ends_with_what_it_cost(self, docs, embedder, caplog):
        with caplog.at_level(logging.INFO, logger="assistant"):
            output = run()

        line = "assistant.index_docs source=help chunks=3 embedded=3 deleted=0 tokens=30 cost_usd=0.000001"
        assert line in output
        assert line in caplog.text
        for source in ("app_doc", "workbook", "plans"):
            assert f"assistant.index_docs source={source} " in output

    def test_the_cost_is_erploras_own_not_an_accounts(self, docs, embedder):
        run()

        assert not AssistantUsage.objects.exists()

    def test_the_outbox_says_what_each_source_kept(self, docs, embedder):
        run()

        [event] = OutboxEvent.objects.filter(name="assistant.docs.indexed", payload__source="help")
        assert event.payload == {"source": "help", "chunks": 3, "embedded": 3, "deleted": 0}


class TestTheNextRuns:
    def test_a_second_run_embeds_nothing(self, docs, embedder):
        run()
        first = len(batches(embedder))

        output = run()

        assert len(batches(embedder)) == first
        assert "assistant.index_docs source=help chunks=3 embedded=0 deleted=0 tokens=0 cost_usd=0.000000" in output
        assert DocChunk.objects.filter(source="help").count() == 3

    def test_a_changed_section_is_the_only_one_embedded_again_and_its_old_excerpt_goes(self, docs, embedder):
        run()
        kept = {row.heading: row.pk for row in help_rows()}
        write(docs, "docs/en/help/01-getting-started.md", GUIDE.replace("Type your PIN.", "Type your four-digit PIN."))

        output = run()

        assert "source=help chunks=3 embedded=1 deleted=1 " in output
        rows = {row.heading: row for row in help_rows()}
        assert rows["Getting started > Signing in again"].text == "Type your four-digit PIN."
        assert rows["Getting started > Signing in again"].pk != kept["Getting started > Signing in again"]
        assert rows["Getting started > The first time"].pk == kept["Getting started > The first time"]

    def test_the_excerpts_of_a_removed_guide_go(self, docs, embedder):
        write(docs, "docs/es/help/05-faq.md", "# Preguntas\n\n## Acceso\n\nCon tu PIN.\n")
        run()
        (docs / "docs/es/help/05-faq.md").unlink()

        output = run()

        assert "source=help chunks=3 embedded=0 deleted=1 " in output
        assert {row.lang for row in help_rows()} == {"en"}

    def test_the_same_excerpt_twice_in_a_source_is_kept_once(self, docs, embedder):
        write(docs, "docs/en/help/02-twice.md", "## Same\n\nWords.\n\n## Same\n\nWords.\n")

        run()

        assert DocChunk.objects.filter(source="help", path="docs/en/help/02-twice.md").count() == 1
        embedded = [text for seen in embedder.requests for text in seen.body["input"]]
        assert embedded.count("Same\nWords.") == 1

    def test_full_embeds_every_excerpt_again(self, docs, embedder):
        run()
        before = {row.content_hash: row.indexed_at for row in help_rows()}
        calls = len(batches(embedder))

        output = run("--full")

        assert len(batches(embedder)) == calls * 2
        assert "source=help chunks=3 embedded=3 deleted=0 " in output
        after = {row.content_hash: row.indexed_at for row in help_rows()}
        assert after.keys() == before.keys()
        assert all(after[key] > before[key] for key in before)

    def test_full_writes_the_new_fingerprint_over_the_old(self, docs, answering, fake_provider):
        fake_provider.reply("POST", EMBEDDINGS, always=True, answer=embeddings_for)
        run()
        fake_provider.reply(
            "POST", EMBEDDINGS, always=True, answer=lambda body: {**embeddings_for(body), "data": [
                {"object": "embedding", "index": index, "embedding": vector(7)} for index in range(len(body["input"]))
            ]}
        )

        run("--full")

        assert {row.embedding[7] for row in help_rows()} == {1.0}


class TestTheBatches:
    def test_the_provider_gets_at_most_64_texts_a_call(self, docs, embedder):
        sections = "\n\n".join(f"## Section {number}\n\nWords of section {number}." for number in range(130))
        write(docs, "docs/en/help/01-getting-started.md", f"# Long guide\n\n{sections}\n")

        run()

        help_calls = [len(seen.body["input"]) for seen in embedder.requests if seen.body["input"][0].startswith("Long guide")]
        assert help_calls == [64, 64, 2]
        assert DocChunk.objects.filter(source="help").count() == 130
        assert max(batches(embedder)) == 64

    def test_each_batch_is_written_before_the_next_is_embedded(self, docs, embedder, monkeypatch):
        """The memory of a run is one batch of fingerprints, whatever a source has (saas-cron has 512 MB)."""
        from assistant import services

        sections = "\n\n".join(f"## Section {number}\n\nWords of section {number}." for number in range(130))
        write(docs, "docs/en/help/01-getting-started.md", f"# Long guide\n\n{sections}\n")
        written = []
        index = services.docs_index

        def spy(ctx, data):
            if data.source == "help":
                written.append((len(data.chunks), len(batches(embedder)), data.keep is not None))
            return index(ctx, data)

        monkeypatch.setattr(services, "docs_index", spy)

        output = run()

        assert written == [(64, 1, True), (64, 2, False), (2, 3, False)]
        assert "source=help chunks=130 embedded=130 deleted=0 tokens=1300 " in output


class TestWhatStopsIt:
    def test_without_the_services_provider_it_ends_with_code_2_and_writes_nothing(self, docs, provider):
        with pytest.raises(CommandError, match="provider of the embeddings") as refused:
            run()

        assert refused.value.returncode == 2
        assert not DocChunk.objects.exists()

    def test_without_any_provider_too(self, docs):
        with pytest.raises(CommandError) as refused:
            run()

        assert refused.value.returncode == 2

    def test_a_dry_run_counts_and_writes_nothing(self, docs, embedder):
        output = run("--dry-run")

        assert "(dry run) assistant.index_docs source=help chunks=3 embedded=3 deleted=0" in output
        assert not DocChunk.objects.exists()
        assert batches(embedder) == []

    def test_a_dry_run_needs_no_provider(self, docs):
        assert "(dry run) assistant.index_docs source=help chunks=3 embedded=3" in run("--dry-run")

    def test_a_provider_that_fails_stops_the_run(self, docs, answering, fake_provider):
        fake_provider.reply("POST", EMBEDDINGS, always=True, status=500, json={"error": {"message": "down"}})

        with pytest.raises(CommandError, match="help") as failed:
            run()

        assert failed.value.returncode == 1
        assert not DocChunk.objects.exists()

    def test_what_was_embedded_before_a_failure_stays_and_the_next_run_does_the_rest(
        self, docs, answering, fake_provider
    ):
        sections = "\n\n".join(f"## Section {number}\n\nWords of section {number}." for number in range(70))
        write(docs, "docs/en/help/01-getting-started.md", f"# Long guide\n\n{sections}\n")
        fake_provider.reply("POST", EMBEDDINGS, answer=embeddings_for)
        fake_provider.reply("POST", EMBEDDINGS, status=500, json={"error": {"message": "down"}})

        with pytest.raises(CommandError, match="help"):
            run()
        assert DocChunk.objects.filter(source="help").count() == 64

        fake_provider.reply("POST", EMBEDDINGS, always=True, answer=embeddings_for)
        output = run()

        assert "source=help chunks=70 embedded=6 deleted=0 " in output

    def test_a_second_run_returns_at_once_while_one_holds_the_lock(self, docs, embedder, other_session):
        other_session.execute(f"SELECT pg_advisory_lock({LOCK_KEY})")
        try:
            output = run()
        finally:
            other_session.execute(f"SELECT pg_advisory_unlock({LOCK_KEY})")

        assert "already running" in output
        assert not DocChunk.objects.exists() and batches(embedder) == []


class TestTheMigration:
    def test_going_back_drops_the_table_and_the_extension_and_forward_brings_them_back(self, docs, embedder):
        from django.db import connection

        run()
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")

        call_command("migrate", "assistant", "0003", verbosity=0)
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM pg_extension WHERE extname = 'vector'")
            extension_after_back = cursor.fetchone()[0]
        tables_after_back = set(connection.introspection.table_names())
        call_command("migrate", "assistant", verbosity=0)

        assert extension_after_back == 0
        assert "assistant_docchunk" not in tables_after_back
        assert "assistant_docchunk" in connection.introspection.table_names()
        assert not DocChunk.objects.exists()

    def test_the_index_is_hnsw_by_cosine(self):
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute("SELECT indexdef FROM pg_indexes WHERE indexname = 'assistant_docchunk_embedding'")
            [definition] = cursor.fetchone()

        assert "USING hnsw (embedding vector_cosine_ops)" in definition
        assert "m='16'" in definition and "ef_construction='64'" in definition


class TestTheWrite:
    """``assistant.docs.index`` and ``assistant.docs.list``: the platform's, and it computes each hash itself."""

    def test_an_excerpt_the_source_does_not_keep_is_refused(self, db):
        from live.errors import OperationError

        from assistant import services
        from assistant.schemas import DocChunkIn, DocsIndexIn

        chunk = DocChunkIn(path="docs/en/help/01.md", lang="en", heading="Guide", text="Text.", embedding=vector(0))

        with pytest.raises(OperationError) as refused:
            services.docs_index(services.platform_context(), DocsIndexIn(source="help", keep=["0" * 64], chunks=[chunk]))

        assert (refused.value.status, refused.value.code) == (422, "assistant.docs_not_kept")
        assert not DocChunk.objects.exists()

    def test_a_fingerprint_of_another_length_is_refused(self):
        from pydantic import ValidationError

        from assistant.schemas import DocChunkIn

        with pytest.raises(ValidationError):
            DocChunkIn(path="p", lang="en", heading="h", text="t", embedding=[0.1] * 3)

    @pytest.mark.parametrize("operation", ["assistant.docs.index", "assistant.docs.list"])
    def test_only_the_platform_runs_them(self, operation, make_user):
        from live.errors import PermissionDenied
        from live.operations import get

        from hubs.tests.conftest import ctx_for

        op = get(operation)
        ctx = ctx_for(make_user("staff@erplora.com", is_staff=True))
        ctx = type(ctx)(scope=ctx.scope, actor=ctx.actor, permissions=frozenset({"assistant.manage"}), language="en")

        with pytest.raises(PermissionDenied):
            op(ctx, op.input(source="help"))
