"""``/robots.txt`` and ``/llms.txt`` (spec §8.2), ported from ERPlora/saas ``landing/views.py`` and
its ``test_ai_crawlers.py`` and ``test_llms_txt.py`` (origin/develop c5ca8ca).

robots.txt: the answer engines reach the public web and nothing else. A robots.txt client obeys
exactly ONE group, the most specific that matches its token, so a named group REPLACES ``*``: each
named group repeats every private path, asserted agent by agent and by a real parser.

llms.txt: what ERPlora is, then the pages that answer what buyers ask. Adapted: it links only pages
that exist (each batch of the port adds its own to ``LLMS_SECTIONS``) and has no apps section until
the store reads the catalogue (L6; spec §5.3 omits the block with no listed app). The original's
links to ``/compliance/`` and ``/solutions/`` are gone with those pages (spec §8.3, §11).
"""

import re
from urllib.robotparser import RobotFileParser

import pytest

from public import seo
from public.crawlers import ANSWER_ENGINE_AGENTS, private_prefixes

HOST = "localhost:8001"
ORIGIN = f"https://{HOST}"


def _groups(body: str) -> dict[str, list[str]]:
    """robots.txt as ``{user-agent: [directive lines]}``; consecutive ``User-agent:`` lines share
    one group, as a real client reads it."""
    groups: dict[str, list[str]] = {}
    current: list[str] = []
    pending: list[str] = []
    for raw in body.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        field, _, value = line.partition(":")
        field, value = field.strip().lower(), value.strip()
        if field == "user-agent":
            if current:
                current, pending = [], []
            pending.append(value)
            groups.setdefault(value, [])
            continue
        if not pending:
            continue  # a site-wide line (Sitemap:) belongs to no group
        current = [line]
        for agent in pending:
            groups[agent].append(line)
    return groups


@pytest.fixture
def robots(client, db):
    response = client.get("/robots.txt", HTTP_HOST=HOST)
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/plain")
    return response.content.decode()


@pytest.fixture
def parser(robots):
    robot_parser = RobotFileParser()
    robot_parser.parse(robots.splitlines())
    return robot_parser


@pytest.mark.parametrize("agent", ANSWER_ENGINE_AGENTS)
def test_each_answer_engine_has_its_own_group_and_may_crawl(robots, agent):
    groups = _groups(robots)

    assert agent in groups
    assert "Allow: /" in groups[agent]


@pytest.mark.parametrize("agent", [*ANSWER_ENGINE_AGENTS, "*"])
@pytest.mark.parametrize("prefix", private_prefixes())
def test_every_group_disallows_every_private_prefix(robots, agent, prefix):
    assert f"Disallow: {prefix}" in _groups(robots)[agent]


def test_the_sitemap_is_advertised_on_the_requests_host(robots):
    assert f"Sitemap: {ORIGIN}/sitemap.xml" in robots


def test_the_public_web_itself_is_crawlable(robots):
    assert "Disallow: /\n" not in robots


@pytest.mark.parametrize("agent", [*ANSWER_ENGINE_AGENTS, "*", "Googlebot"])
def test_a_real_parser_lets_every_agent_onto_the_public_web(parser, agent):
    assert parser.can_fetch(agent, f"{ORIGIN}/")
    assert parser.can_fetch(agent, f"{ORIGIN}/pricing/")
    assert parser.can_fetch(agent, f"{ORIGIN}/apps/inventory/")


@pytest.mark.parametrize("agent", [*ANSWER_ENGINE_AGENTS, "*", "Googlebot"])
@pytest.mark.parametrize(
    "path",
    [
        "/admin/",
        "/accounts/login/",
        "/api/me",
        "/_allauth/browser/v1/auth/session",
        "/internal/auth/redeem",
        "/hub-login/",
        "/launch",
        "/login",
        "/2fa",
    ],
)
def test_a_real_parser_keeps_every_agent_out_of_the_private_half(parser, agent, path):
    assert not parser.can_fetch(agent, f"{ORIGIN}{path}")


def test_the_check_would_catch_the_regression(robots):
    """Strip the repeated ``Disallow:`` lines from the named groups (the mistake this guards) and
    the parser must let GPTBot into the admin, or the assertions above prove nothing."""
    naive = []
    in_star_group = False
    for line in robots.splitlines():
        if line.startswith("User-agent:"):
            in_star_group = line.strip() == "User-agent: *"
        if line.startswith("Disallow:") and not in_star_group:
            continue
        naive.append(line)
    robot_parser = RobotFileParser()
    robot_parser.parse(naive)

    assert robot_parser.can_fetch("GPTBot", f"{ORIGIN}/admin/")


# llms.txt


@pytest.fixture
def llms(client, db):
    response = client.get("/llms.txt", HTTP_HOST=HOST)
    assert response.status_code == 200
    return response


def test_llms_is_plain_text_in_utf8(llms):
    assert llms["Content-Type"] == "text/plain; charset=utf-8"


def test_llms_opens_with_the_product_name_as_an_h1(llms):
    assert llms.content.decode().splitlines()[0] == "# ERPlora"


def test_llms_says_what_erplora_is_before_linking_anything(llms):
    summary = llms.content.decode().splitlines()[2]

    assert summary.startswith("> ")
    assert "ERP" in summary and "POS" in summary


@pytest.mark.parametrize("prefix", private_prefixes())
def test_llms_never_mentions_the_private_half(llms, prefix):
    """A reading list: a private path here is an invitation."""
    assert prefix not in llms.content.decode()


def test_llms_has_no_apps_section_without_the_catalogue(llms):
    """Spec §5.3: without listed apps the block is omitted (the store brings it, L6)."""
    assert "## Apps" not in llms.content.decode()


@pytest.mark.django_db
def test_a_registered_page_is_listed_with_an_absolute_url(client, monkeypatch):
    monkeypatch.setattr(
        seo,
        "LLMS_SECTIONS",
        (("Start here", (("public:robots_txt", "Robots", "who may crawl."),)),),
    )

    body = client.get("/llms.txt", HTTP_HOST=HOST).content.decode()

    assert "## Start here" in body
    assert f"- [Robots]({ORIGIN}/robots.txt): who may crawl." in body


@pytest.mark.django_db
def test_an_empty_section_is_omitted(client, monkeypatch):
    monkeypatch.setattr(seo, "LLMS_SECTIONS", (("Start here", ()),))

    assert (
        "## Start here" not in client.get("/llms.txt", HTTP_HOST=HOST).content.decode()
    )


@pytest.mark.django_db
def test_every_linked_page_exists(client, llms):
    """A link in llms.txt is quoted verbatim by a model: it must answer 200."""
    links = re.findall(r"\]\((https://[^)]+)\)", llms.content.decode())

    for link in links:
        assert link.startswith(f"{ORIGIN}/"), link
        assert (
            client.get(link.removeprefix(ORIGIN), HTTP_HOST=HOST).status_code == 200
        ), link
