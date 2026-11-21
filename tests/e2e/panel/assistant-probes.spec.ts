// The panel assistant's QA with the REAL model: every probe of the corpus (tests/e2e/qa/probes/, or the files and
// folders of `QA_PROBES`, comma-separated) is a NEW natural phrase for one tool of the exported catalogue, typed in the
// real panel chat, and its automatic verdict (assistant-probes.ts, `probeVerdict`): «read» → its tool is the first the
// model runs (past the always offered ones and the probe's `lookups`), no card; «card» → the first card is its tool's
// and no other shows, cancelled (nothing in the outbox) or confirmed (it ran); «refused» → no card nor write, its tool
// not run, and the answer says why it cannot (a permission, a role, the app, erplora.com in the browser); «docs» → the
// documentation search returned excerpts the answer names, and no tool of the account ran. Before it is asked, a probe
// is checked against the catalogues (`probeProblems`): a phrase equal to one of the tool's asks in any language (case,
// accents and punctuation aside), or an expectation the catalogue of its surface contradicts, is not asked (n.a.) and
// fails.
//
// Only with `QA_REAL_PROVIDER=1` (never in the CI), on a stack and e2e database of its own, from the same seed as the
// battery (`assistant_seed.py real`: the real providers, «QA Base» on the Free plan, the documentation index), in every
// worker, and every worker ends with `assistant_seed.py clear` (also after a failure): no QA account stays behind. The
// account's language follows each probe's (Account → Preferences) and its surface too: `?surface=account` is the app's
// account surface, which sells nothing; `?surface=web` the web. The month's messages are reset when spent (the probes
// do not check the quota; the battery does). Each probe in a new conversation; what it showed goes to
// `.artifacts/qa/probes/<run>/` (its JSON and screenshots) and the run's report, `report.md` there, is written after
// each probe, keys redacted, with `bench.json`, the record of each turn that compares models (assistant-bench.ts; the
// QA_ANSWER_* variables choose the model that answers, assistant_seed.py `answer_choice`). Recipe: tests/e2e/README.md,
// «Sondas del asistente».
// flow: ASSISTANT-F25 — the account asks the panel's assistant: reads alone, writes after the card.
// flow: ASSISTANT-F27 — the panel's assistant answers how-to questions from ERPlora's documentation.
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import type { BrowserContext, Page } from '@playwright/test';

import { realProviderMode } from '../assistant-battery';
import {
  benchModel,
  type BenchMeta,
  type BenchReport,
  benchTurn,
  type Measured,
  offeredCode,
  parseUsage,
  spentBetween,
  toolKind,
  type Usage,
  usageCode,
  withTurn,
} from '../assistant-bench';
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
import {
  type AssistantChat,
  clearRealAssistant,
  qaChat,
  REAL_SECRETS,
  type RealSeed,
  seedRealAssistant,
  TURN_MS,
  uvRun,
} from './assistant-chat';
import { djangoPrintWarm } from './django';
import { expect, test } from './fixtures';
import { apiPost } from './session';

const HERE = dirname(fileURLToPath(import.meta.url));
const SAAS_DIR = resolve(HERE, '..', '..', '..');
const QA_DIR = join(HERE, '..', '.artifacts', 'qa');
const CORPUS = join(HERE, '..', 'qa', 'probes');
const RUN = process.env.PW_RUN_ID ?? 'local';
const OUT = join(QA_DIR, 'probes', RUN);
const REPORT = join(OUT, 'report.md');
const BENCH = join(OUT, 'bench.json');
const OWNER = { email: 'e2e-assistant-qa-battery@example.com', password: process.env.QA_PANEL_PASSWORD ?? 'e2e-panel' };
/** Only to redact them from what is written: the seed reads them, never this spec. */
const SECRETS = REAL_SECRETS;

const REAL = realProviderMode(process.env);
/** Read when the spec loads, also when it is skipped: a broken probe file stops any run (the CI's Vitest checks the
 *  corpus too, assistant-probes.test.ts). */
const FILES = probeFiles(process.env.QA_PROBES || CORPUS);
/** Each probe with its file, named from the SaaS (`tests/e2e/qa/probes/…`). */
const PROBES = loadProbes(FILES).map(({ probe, source }) => ({ probe, source: relative(SAAS_DIR, resolve(source)) }));
// Every model answers the whole corpus of the panel: a sample is the Hub's (its tests/e2e/assistant-sample.ts).
if (process.env.QA_PROBES_SAMPLE) throw new Error('QA_PROBES_SAMPLE draws a sample of the Hub’s probes only: the panel asks its whole corpus.');

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
let always: string[] = [];
const catalogs = new Map<string, CatalogTool[]>();
/** The tools the panel's turn offers each probe's phrase (`offeredCode`), ranked once per worker. */
let offered: Record<string, string[]> = {};
/** When the probe being asked was sent, and what the account had spent just before. */
let asking: { started: number; before: Usage | null } = { started: 0, before: null };

/** The seed of this worker: the keys and the account again (the worker before forgot them), the index only where it
 *  changed. */
function seed(): Seeded {
  mkdirSync(OUT, { recursive: true });
  const { seed: made, indexed } = seedRealAssistant('es');
  const seeded = { ...made, indexed };
  writeFileSync(join(OUT, 'seed.json'), JSON.stringify(seeded, null, 2));
  return seeded;
}

/** What every turn offers (`base.assistant.ALWAYS`): a read may run them before its own tool. */
const alwaysOffered = async (): Promise<string[]> =>
  JSON.parse(await djangoPrintWarm('import json\nfrom base.assistant import ALWAYS\nprint(json.dumps(list(ALWAYS)))')) as string[];

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

/** The account's spend so far, as its usage rows say it. */
const accountUsage = async (): Promise<Usage> => parseUsage(await djangoPrintWarm(usageCode(OWNER.email)));

/** The probe's turn into the run's bench report: the same run of another worker keeps its meta. */
async function bench(result: ProbeResult, measured: Omit<Measured, 'kind' | 'offered' | 'bodies' | 'usage'>): Promise<void> {
  if (!seeded) return;
  const meta: BenchMeta = {
    product: 'saas',
    run: RUN,
    date: new Date().toISOString(),
    model: benchModel(seeded.answer),
    files: FILES.map((file) => relative(SAAS_DIR, resolve(file))),
    corpus: PROBES.length,
    sample: null,
  };
  const asked = result.verdict !== 'n.a.';
  const usage = asked && asking.before ? spentBetween(asking.before, await accountUsage()) : null;
  const kind = toolKind(result.probe, catalog(result.probe.language, 'web'));
  // Only once the phrase was sent are the chat's bodies this probe's (a new conversation empties them).
  const bodies = asked && asking.started ? await chat.streamed() : [];
  const turn = benchTurn(result, { ...measured, bodies, usage, kind, offered: offered[result.probe.id] ?? null });
  const kept = existsSync(BENCH) ? (JSON.parse(readFileSync(BENCH, 'utf8')) as BenchReport) : null;
  const report = withTurn(kept, meta, turn, PROBES.map((entry) => entry.probe.id));
  writeFileSync(BENCH, redact(JSON.stringify(report, null, 2), SECRETS));
}

/** How many outbox events there are: what a probe recorded comes after. Asked of the warm Django: no boot in a probe. */
const outboxMark = async (): Promise<number> =>
  Number(await djangoPrintWarm('from live.models import OutboxEvent\nprint(OutboxEvent.objects.count())'));

/** The outbox events recorded after `mark`, but the assistant's own (each turn records its message and usage). */
async function outboxSince(mark: number): Promise<string[]> {
  const names = await djangoPrintWarm(
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
  await djangoPrintWarm(
    `from assistant.models import AssistantUsage\nAssistantUsage.objects.filter(user__email=${JSON.stringify(OWNER.email)}).delete()`,
  );
  resets += 1;
}

/** The probe asked in a new conversation, in its language and on its surface, its cards decided, and what showed. */
async function ask(probe: Probe): Promise<ProbeObserved> {
  await placeFor(probe);
  await keepMessages();
  await chat.newConversation();
  const mark = await outboxMark();
  asking = { started: 0, before: await accountUsage() };
  asking.started = Date.now();
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
    events: await outboxSince(mark),
    screenshot: relative(SAAS_DIR, screenshot),
  };
}

test.beforeAll(async ({ browser }) => {
  test.setTimeout(900_000);
  if (!REAL) return;
  seeded = seed();
  // The first call boots this worker's warm Django (the probes ask it for the outbox): here, on no test's clock.
  always = await alwaysOffered();
  // Every catalogue a probe reads (`manage.py export_assistant_catalog`, a Django boot each): here, not in a probe.
  for (const language of ['en', 'es']) catalog(language, 'web');
  for (const { probe } of PROBES) catalog(probe.language, probe.surface);
  offered = JSON.parse(await djangoPrintWarm(offeredCode(PROBES.map((entry) => entry.probe)))) as Record<string, string[]>;
  ({ context, page, chat } = await qaChat(browser, OWNER));
});

test.afterAll(async () => {
  try {
    writeReport();
    await context?.close();
  } finally {
    if (REAL) clearRealAssistant();
  }
});

for (const { probe, source } of PROBES) {
  test(`${probe.id} ${probe.phrase}`, async () => {
    const problems = probeProblems(probe, {
      web: catalog(probe.language, 'web'),
      surface: catalog(probe.language, probe.surface),
      everyLanguage: [...catalog('en', 'web'), ...catalog('es', 'web')],
    });
    if (problems.length) {
      const skipped: ProbeResult = { probe, source, observed: null, verdict: 'n.a.', reasons: problems };
      record(skipped);
      await bench(skipped, { latencyMs: null, error: null });
      expect(problems, `${probe.id} was not asked`).toEqual([]);
      return;
    }
    let observed: ProbeObserved;
    asking = { started: 0, before: null };
    try {
      observed = await ask(probe);
    } catch (error) {
      // A turn that never ended, a page that did not load: the report still names the probe and why.
      const why = `did not finish: ${(error as Error).message.split('\n')[0]}`;
      const failed: ProbeResult = { probe, source, observed: null, verdict: 'fail', reasons: [why] };
      record(failed);
      try {
        await bench(failed, { latencyMs: asking.started ? Date.now() - asking.started : null, error: why });
      } catch (unrecorded) {
        throw new Error(`${why}; its bench record could not be written: ${(unrecorded as Error).message}`, { cause: error });
      }
      throw error;
    }
    const { verdict, reasons } = probeVerdict(probe, observed, always);
    const result: ProbeResult = { probe, source, observed, verdict, reasons };
    record(result);
    await bench(result, { latencyMs: chat.endedAt - asking.started, error: null });
    expect(verdict, `${probe.id}: ${reasons.join('; ')}`).toBe('pass');
  });
}
