"""An issue of another of our repositories or of the old product, a work item's short label and an id of the
migration's registry are caught in prose, and left alone in data."""

import pytest
from test_no_internal_references import (
    OTHER_REPO_ISSUE,
    REGISTRY_ID,
    WORK_LABEL,
    found_lines,
    internal_references,
    old_tracker_issue,
)


@pytest.mark.parametrize(
    "text",
    [
        "Android has no fallback (hub#984): its only channel is Google Play",
        "FormModal keeps both since ERPlora/ui#112",
        "Meta not answering is said as Meta's (gh:hub#2731)",
        "the plain-language half of the update policy (pm#69)",
        "Canonical = the Hub's develop (ERPlora issue outfitkit#14)",
        "a separator, never as text (ui#56)",
        "the chain of the records, as verifactu#12 left it",
        "the old till's cash_register#7",
        "erplora-old/saas#2536: the address is changed in two steps",
    ],
)
def test_the_scan_catches_an_issue_of_another_repository(text):
    assert OTHER_REPO_ISSUE.search(text)


@pytest.mark.parametrize(
    "text",
    [
        "the doors' spec, which no screen covers (saas#89)",
        "a request is answered for its real path (ERPlora/saas#89)",
        "fixed upstream in capacitor-app#41",
        "the colour #123456 of the border",
        "the business's hub #3 in the list",
        "UTS #46, which also folds the case",
        "fi:saas/orgs-users#informacion-de-facturacion",
        "https://github.com/ERPlora/hub/pull/12#issuecomment-1",
        "the C# client",
    ],
)
def test_the_scan_leaves_this_repository_and_third_parties_alone(text):
    assert not OTHER_REPO_ISSUE.search(text)


@pytest.mark.parametrize(
    "text",
    [
        "the address is changed in two steps (saas#2536)",
        "an address in its plain form, as today's SaaS (ERPlora/saas#1018)",
        "Meta's, never ERPlora's (gh:saas#1958)",
        "Cookie-consent banner (issue #1000)",
        "Issue #2344: the period lives on the item",
    ],
)
def test_the_scan_catches_an_issue_of_the_old_tracker(text):
    assert old_tracker_issue(text)


@pytest.mark.parametrize(
    "text",
    [
        "the doors' spec, which no screen covers (saas#89)",
        "the newest pull request (saas#424)",
        "an issue opened since (saas#510)",
        "the last number below the old tracker's (saas#999)",
        "issue #12 of the list",
        "the grey #999 of the border",
        "the red #1000 of a badge",
    ],
)
def test_the_scan_leaves_this_trackers_issues_alone(text):
    assert not old_tracker_issue(text)


def test_an_old_tracker_issue_is_caught_without_any_history(tmp_path):
    """The CI checks out a commit or two: the rule reads no history, so it holds there as it does here."""
    (tmp_path / "hubs").mkdir()
    (tmp_path / "hubs" / "plans.py").write_text(
        "# Only staff may buy it (saas#1052).\n# The doors' spec (saas#89).\n", encoding="utf-8"
    )
    assert found_lines(internal_references(["hubs/plans.py"], root=tmp_path)) == [1]


@pytest.mark.parametrize(
    "text",
    [
        "ERPlora's staff is refused as a new invitation is (W11b)",
        "the toolbar keeps one row (W8/W10)",
        "until V3 generates them",
        "native buttons styled as the component (L8)",
        "the classes and the feature-card partial of L2;",
        "the four templates of the L3a port",
    ],
)
def test_the_scan_catches_a_work_label(text):
    assert WORK_LABEL.search(text)


@pytest.mark.parametrize(
    "text",
    [
        "the system check ``hubs.W002`` names them",
        "the ALB redirects to HTTPS (W008)",
        "always told to its address (OWASP ASVS V6.3.7)",
        "the type of a rectifying invoice (AEAT, «L3» list)",
        "one of the values of list L2",
        "los valores de la lista L1",
        "a presigned URL signed with SigV4",
        "the Graph API v25.0",
        "since Stripe's ``2025-03-31.basil``",
        "allauth's ``/_allauth/browser/v1/account/email``",
        "a W3C recommendation",
        "a private S3 bucket, VAT regime S1, messages M1 and M2",
    ],
)
def test_the_scan_leaves_standards_versions_and_checks_alone(text):
    assert not WORK_LABEL.search(text)


def test_another_repositorys_issue_or_a_work_label_is_caught_in_prose_but_not_in_data(tmp_path):
    (tmp_path / "public").mkdir()
    (tmp_path / "public" / "downloads.py").write_text(
        '"""Android has no fallback (hub#984): its only channel is Google Play."""\n'
        'ISSUE = "hub#984"\n'
        "LABEL = 'W11b'\n"
        "# The doors' spec, which no screen covers (saas#89).\n"
        "# The address is changed in two steps (saas#2536).\n"
        "# Refused as a new invitation is (W11b).\n"
        "# Treated as VAT-included (TJUE C-249/12); the invoice A-1 of the series A.\n",
        encoding="utf-8",
    )
    spec = tmp_path / "tests" / "e2e" / "panel" / "some.spec.ts"
    spec.parent.mkdir(parents=True)
    spec.write_text(
        "// Android never reads as a download (hub#984).\n"
        "it('paints a separator, never as text (ui#56)', async () => {\n"
        "  await shot('W11b-desktop');\n"
        "  test.info().annotations.push({ type: 'issue', description: 'hub#984' });\n"
        "});\n",
        encoding="utf-8",
    )
    (tmp_path / "public" / "page.html").write_text(
        "{# Never «Download»: on Android the only channel is Play (hub#984). #}\n"
        '<a href="#984">hub#984</a>\n',
        encoding="utf-8",
    )
    (tmp_path / "public" / "theme.css").write_text(
        "/* Canonical = the Hub's develop (outfitkit#14). */\n"
        ".row { color: #999; } /* the grey #999 of the border */\n",
        encoding="utf-8",
    )
    paths = ["public/downloads.py", "tests/e2e/panel/some.spec.ts", "public/page.html", "public/theme.css"]
    found = internal_references(paths, root=tmp_path)
    assert [":".join(line.split(":")[:2]) for line in found] == [
        "public/downloads.py:1",
        "public/downloads.py:5",
        "public/downloads.py:6",
        "tests/e2e/panel/some.spec.ts:1",
        "tests/e2e/panel/some.spec.ts:2",
        "public/page.html:1",
        "public/theme.css:1",
    ]


@pytest.mark.parametrize(
    "text",
    [
        "ACCOUNTS-G93: «Sign out» in the user menu",
        "the accounts nobody used for years are anonymised (ACCOUNTS-G97, G07, G52, G61)",
        "the payer's customer takes the billing details (BILLING-F01; registry BILLING-G26)",
        "no tracker configured, no banner (PUBLIC-G24/G43)",
        "the sparkles of the Hub (BASE" + "-G110)",
        "what waits for the Hub (whatsapp 0002, WHATSAPP_INBOX-G18)",
        "describe('LoginErrorPage: too many jumps (ACCOUNTS-G98, ACCOUNTS-F28)', () => {",
        "Each test names its flow by its registry key: G83=F01, G84=F02",
        "One address, one chat and one reply time (G41).",
        "into a business with a one-time code (G98, and G113: the app)",
    ],
)
def test_the_scan_catches_an_id_of_the_migrations_registry(text):
    assert REGISTRY_ID.search(text)


@pytest.mark.parametrize(
    "text",
    [
        "Trust this browser for 14 days (ACCOUNTS-F05)",
        "the Hub's BASE-F114 gives back what it lost",
        "for the Hub's WHATSAPP_INBOX-F27 (Meta's verdict and reason)",
        "the summit of the G7 countries",
        "a phone on a 4G or 5G network",
        "a G7 summit",
        "the printer model XG12",
        "the key starts with ACCOUNTS-G and its number",
    ],
)
def test_the_scan_leaves_flows_and_other_g_numbers_alone(text):
    assert not REGISTRY_ID.search(text)


def test_a_registry_id_is_caught_in_prose_but_not_in_a_capture_key_or_other_data(tmp_path):
    (tmp_path / "accounts").mkdir()
    (tmp_path / "accounts" / "purge.py").write_text(
        '"""The accounts nobody used for years are anonymised (ACCOUNTS-G97, G07)."""\n'
        'KEY = "ACCOUNTS-G97"\n'
        "# Trust this browser for 14 days (ACCOUNTS-F05).\n"
        "# Reports are braked per address (ACCOUNTS-G78).\n",
        encoding="utf-8",
    )
    spec = tmp_path / "tests" / "e2e" / "panel" / "some.spec.ts"
    spec.parent.mkdir(parents=True)
    spec.write_text(
        "// The accounts nobody used for years (ACCOUNTS-G97).\n"
        "test('ACCOUNTS-G98: too many jumps', async ({ page }) => {\n"
        "  await shot(page, 'ACCOUNTS-G98-desktop');\n"
        "  const atEverySize = captureAtEverySize('HUBS-G65');\n"
        "  await atEverySize(page, 'G108-held', async () => {});\n"
        "});\n"
        "test('ACCOUNTS-F28: too many jumps', async () => {});\n"
        "// One address, one chat and one reply time (G41).\n",
        encoding="utf-8",
    )
    (tmp_path / "accounts" / "page.html").write_text(
        "{# The terms an account accepted (ACCOUNTS-G119). #}\n"
        '<p data-key="ACCOUNTS-G119">ACCOUNTS-F05</p>\n',
        encoding="utf-8",
    )
    paths = ["accounts/purge.py", "tests/e2e/panel/some.spec.ts", "accounts/page.html"]
    found = internal_references(paths, root=tmp_path)
    assert [":".join(line.split(":")[:2]) for line in found] == [
        "accounts/purge.py:1",
        "accounts/purge.py:4",
        "tests/e2e/panel/some.spec.ts:1",
        "tests/e2e/panel/some.spec.ts:2",
        "tests/e2e/panel/some.spec.ts:8",
        "accounts/page.html:1",
    ]
