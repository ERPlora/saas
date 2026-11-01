// The panel assistant's QA with the REAL model, layer 2 (plan docs/plans/2026-10-31-asistente-conocimiento-y-qa.md of
// erplora-next, §1.5 and §4 T3): every probe of the corpus (tests/e2e/qa/probes/, or the files and folders of
// `QA_PROBES`, comma-separated) is a NEW natural phrase for one tool of the exported catalogue, typed in the real panel
// chat, and its automatic verdict (assistant-probes.ts, `probeVerdict`): «read» → its tool ran, no card; «card» → the
// card of its tool, cancelled (nothing in the outbox) or confirmed (it ran); «refused» → no card nor write, its tool
// not run and the answer says it cannot; «docs» → the documentation search ran and the answer cites it, or the manual
// of a Hub app was read (`apps.app.doc`; its documents come from the Hub's `register_apps`). Before it is
// asked, a probe is checked against the catalogue of its language and surface (`probeProblems`): a phrase equal to
// one of the tool's asks, or an expectation the catalogue contradicts, is not asked (n.a.) and fails.
//
// Only with `QA_REAL_PROVIDER=1` (never in the CI), on a stack and e2e database of its own, from the same seed as the
// battery (`assistant_seed.py real`: the real providers, «QA Base» on the Free plan, the documentation index). The
// account's language follows each probe's (Cuenta → Preferencias) and its surface too: `?surface=account` is the app's
// account surface, which sells nothing; `?surface=web` the web. The month's messages are reset when spent (the probes
// do not check the quota; the battery's C35 does). Each probe in a new conversation; what it showed goes to
// `.artifacts/qa/probes/<run>/` (its JSON and screenshots) and the run's report, `report.md` there, is written after
// each probe, keys redacted. Recipe: tests/e2e/README.md, «Sondas del asistente».
// flow: ASSISTANT-F25 — the account asks the panel's assistant: reads alone, writes after the card.
// flow: ASSISTANT-F27 — the panel's assistant answers how-to questions from ERPlora's documentation.
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import type { BrowserContext, Page } from '@playwright/test';

import { realProviderMode } from '../assistant-battery';
import {
  type CatalogTool,
  decisionFor,
  loadProbes,
  type Probe,
  probeFiles,
  probeProblems,
  type ProbeObserved,
  type ProbeResult,
  probeVerdict,
  redact,
  renderProbeReport,
} from '../assistant-probes';
import { AssistantChat, type RealSeed, seedRealAssistant, TURN_MS, uvRun } from './assistant-chat';
import { apiPost, djangoPrint, expect, signIn, test } from './fixtures';
import { PANEL_URL } from './project';

const HERE = dirname(fileURLToPath(import.meta.url));
const SAAS_DIR = resolve(HERE, '..', '..', '..');
const QA_DIR = join(HERE, '..', '.artifacts', 'qa');
const CORPUS = join(HERE, '..', 'qa', 'probes');
const RUN = process.env.PW_RUN_ID ?? 'local';
const OUT = join(QA_DIR, 'probes', RUN);
const REPORT = join(OUT, 'report.md');
const OWNER = { email: 'e2e-assistant-qa-battery@example.com', password: process.env.QA_PANEL_PASSWORD ?? 'e2e-panel' };
/** Only to redact them from what is written: the seed reads them, never this spec. */
const SECRETS = [process.env.QA_QWEN_API_KEY, process.env.QA_OPENAI_API_KEY];

const REAL = realProviderMode(process.env);
/** Read when the spec loads, also when it is skipped: a broken probe file stops any run (the CI's Vitest checks the
 *  corpus too, assistant-probes.test.ts). */
const FILES = probeFiles(process.env.QA_PROBES || CORPUS);
/** Each probe with its file, named from the SaaS (`tests/e2e/qa/probes/…`). */
const PROBES = loadProbes(FILES).map(({ probe, source }) => ({ probe, source: relative(SAAS_DIR, resolve(source)) }));

test.skip(!REAL, 'only with QA_REAL_PROVIDER=1: the real model with real keys (tests/e2e/README.md)');
test.describe.configure({ timeout: TURN_MS + 120_000 });

interface Seeded extends RealSeed {
  indexed: string[];
}

let context: BrowserContext | undefined;
let page: Page;
let chat: AssistantChat;
let seeded: Seeded | undefined;
/** Where the page is: the surface and the account's language of the last probe asked. */
let place = { surface: '', language: '' };
let resets = 0;
const catalogs = new Map<string, CatalogTool[]>();

/** The seed, once per run (a new worker after a failure reads what the first one made). */
function seedOnce(): Seeded {
  const marker = join(OUT, 'seed.json');
  if (existsSync(marker)) return JSON.parse(readFileSync(marker, 'utf8')) as Seeded;
  mkdirSync(OUT, { recursive: true });
  const { seed, indexed } = seedRealAssistant('es');
  const made = { ...seed, indexed };
  writeFileSync(marker, JSON.stringify(made, null, 2));
  return made;
}

/** The catalogue the panel offers the account on `surface` in `language` (`manage.py export_assistant_catalog`). */
function catalog(language: string, surface: string): CatalogTool[] {
  const key = `${language}-${surface}`;
  const cached = catalogs.get(key);
  if (cached) return cached;
  const tools = JSON.parse(
    uvRun(['python', 'manage.py', 'export_assistant_catalog', '--language', language, '--surface', surface, '--role', 'account']),
  ) as CatalogTool[];
  catalogs.set(key, tools);
  return tools;
}

const fileOf = (probe: Probe, suffix = ''): string => join(OUT, `${probe.id.replace(/[^A-Za-z0-9._-]+/g, '-')}${suffix}`);

function readResults(): ProbeResult[] {
  if (!existsSync(OUT)) return [];
  const order = PROBES.map((entry) => entry.probe.id);
  return readdirSync(OUT)
    .filter((name) => name.endsWith('.result.json'))
    .map((name) => JSON.parse(readFileSync(join(OUT, name), 'utf8')) as ProbeResult)
    .sort((a, b) => order.indexOf(a.probe.id) - order.indexOf(b.probe.id));
}

function writeReport(): void {
  if (!seeded) return;
  const meta = {
    started: RUN,
    model: seeded.model,
    fallback: seeded.fallback,
    files: FILES.map((file) => relative(SAAS_DIR, resolve(file))),
    notes: [
      `Account ${seeded.owner}, owner of «${seeded.business}» on the Free plan; its language and surface follow each probe`,
      `The month's messages reset ${resets} time(s) in this worker (the probes do not check the quota)`,
      ...seeded.indexed.map((line) => `index_docs this run: ${line.replace(/^assistant\.index_docs /, '')}`),
      'Verdicts check the tools, cards, notices and the outbox; the wording only to hear a refusal',
    ],
  };
  mkdirSync(OUT, { recursive: true });
  writeFileSync(REPORT, renderProbeReport(meta, readResults(), SECRETS));
}

function record(result: ProbeResult): void {
  mkdirSync(OUT, { recursive: true });
  writeFileSync(fileOf(result.probe, '.result.json'), redact(JSON.stringify(result, null, 2), SECRETS));
  writeReport();
}

/** How many outbox events there are: what a probe recorded comes after. */
const outboxMark = (): number => Number(djangoPrint('from live.models import OutboxEvent\nprint(OutboxEvent.objects.count())'));

/** The outbox events recorded after `mark`, but the assistant's own (each turn records its message and usage). */
function outboxSince(mark: number): string[] {
  const names = djangoPrint(
    [
      'import json',
      'from live.models import OutboxEvent',
      `rows = OutboxEvent.objects.order_by("created_at", "id")[${mark}:]`,
      'print(json.dumps([row.name for row in rows if not row.name.startswith("assistant.")]))',
    ].join('\n'),
  );
  return JSON.parse(names) as string[];
}

/** The account's language and the page's surface as the probe asks, the assistant's panel open. */
async function placeFor(probe: Probe): Promise<void> {
  if (place.surface === probe.surface && place.language === probe.language) return;
  if (place.language !== probe.language) {
    const response = await apiPost(page.request, '/api/accounts/preferences', { language: probe.language });
    expect(response.status(), 'POST /api/accounts/preferences').toBe(200);
  }
  await page.goto(`/dashboard/businesses?surface=${probe.surface === 'app' ? 'account' : 'web'}`);
  await expect(page.getByText(seeded?.business ?? '').first()).toBeVisible();
  await chat.open();
  place = { surface: probe.surface, language: probe.language };
}

/** A message left for the probe: the month's are reset when spent. */
async function keepMessages(): Promise<void> {
  const { used, limit } = await chat.usage();
  if (used === null || limit === null || used < limit) return;
  djangoPrint(
    `from assistant.models import AssistantUsage\nAssistantUsage.objects.filter(user__email=${JSON.stringify(OWNER.email)}).delete()`,
  );
  resets += 1;
}

/** The probe asked in a new conversation, in its language and on its surface, its cards decided, and what showed. */
async function ask(probe: Probe): Promise<ProbeObserved> {
  await placeFor(probe);
  await keepMessages();
  await chat.newConversation();
  const mark = outboxMark();
  await chat.send(probe.phrase);
  await chat.settle(probe.id, async (card) => {
    await page.screenshot({ path: fileOf(probe, '-card.png') });
    await chat.resolveCard(card, decisionFor(probe, await chat.lastCard()));
  });
  const shown = await chat.shown();
  const screenshot = fileOf(probe, '.png');
  await page.screenshot({ path: screenshot });
  return {
    answer: shown.answer,
    links: shown.links,
    notices: shown.notices,
    failures: shown.failures,
    turns: await chat.turns(),
    events: outboxSince(mark),
    screenshot: relative(SAAS_DIR, screenshot),
  };
}

test.beforeAll(async ({ browser }) => {
  test.setTimeout(900_000);
  if (!REAL) return;
  seeded = seedOnce();
  context = await browser.newContext({ baseURL: PANEL_URL, locale: 'es-ES', viewport: { width: 1440, height: 900 } });
  page = await context.newPage();
  chat = new AssistantChat(page);
  await signIn(page.request, OWNER);
});

test.afterAll(async () => {
  writeReport();
  await context?.close();
});

for (const { probe, source } of PROBES) {
  test(`${probe.id} ${probe.phrase}`, async () => {
    const problems = probeProblems(probe, { web: catalog(probe.language, 'web'), surface: catalog(probe.language, probe.surface) });
    if (problems.length) {
      record({ probe, source, observed: null, verdict: 'n.a.', reasons: problems });
      expect(problems, `${probe.id} was not asked`).toEqual([]);
      return;
    }
    let observed: ProbeObserved;
    try {
      observed = await ask(probe);
    } catch (error) {
      // A turn that never ended, a page that did not load: the report still names the probe and why.
      record({ probe, source, observed: null, verdict: 'fail', reasons: [`did not finish: ${(error as Error).message.split('\n')[0]}`] });
      throw error;
    }
    const { verdict, reasons } = probeVerdict(probe, observed);
    record({ probe, source, observed, verdict, reasons });
    expect(verdict, `${probe.id}: ${reasons.join('; ')}`).toBe('pass');
  });
}
