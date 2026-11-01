// The assistant's QA battery with the REAL model and the REAL documentation index (plan
// docs/plans/2026-10-31-qa-asistente.md of erplora-next: block A, the panel's side of C35 and C36, and C38), in the
// panel as an account asks it. Only with `QA_REAL_PROVIDER=1` (never in the CI: `realProviderMode` refuses on GitHub
// Actions), on a stack of its own (`E2E_SAAS_PORT`, its own e2e database): `assistant_seed.py real` keeps the real
// providers with the keys of `QA_QWEN_API_KEY` and `QA_OPENAI_API_KEY` (read there, never here), the panel's Django
// sends the embeddings to the real «openai» and gives production's 30 messages (panel/project.ts), and `index_docs`
// keeps the documentation the search reads. Recipe: tests/e2e/README.md, «El asistente con el modelo de verdad».
//
// One test per item, each in a new conversation: the question typed in Spanish, the turn followed to its end (a card
// of the expected write is confirmed with the word it asks for; any other card is cancelled), then what the panel
// showed — the answer, the tools that ran (the turn's frames), the card, the excerpts the documentation search
// returned, the receipts, the notices, the failures, the month's messages — and a screenshot under
// `.artifacts/qa/`. The automatic verdict (assistant-battery.ts, `verdictOf`) asserts only what is objective; the
// model's wording is never asserted. Every result goes to `.artifacts/qa/results/<run>/` and the report the supervising
// chat reads, `.artifacts/qa/assistant-battery-A.md`, is written again after every worker.
// flow: ASSISTANT-F25 — the account asks the panel's assistant: reads alone, writes after the card.
// flow: ASSISTANT-F26 — the account's messages of the month.
// flow: ASSISTANT-F27 — the panel's assistant answers how-to questions from ERPlora's documentation.
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import type { BrowserContext, Locator, Page } from '@playwright/test';

import {
  BATTERY_A,
  BATTERY_C,
  type Check,
  type Item,
  type ItemResult,
  type Observed,
  realProviderMode,
  renderReport,
  type ReportMeta,
  verdictOf,
} from '../assistant-battery';
import { AssistantChat, seedRealAssistant, TURN_MS } from './assistant-chat';
import { djangoPrint, expect, signIn, test } from './fixtures';
import { PANEL_URL } from './project';

const HERE = dirname(fileURLToPath(import.meta.url));
const QA_DIR = join(HERE, '..', '.artifacts', 'qa');
const RESULTS = join(QA_DIR, 'results', process.env.PW_RUN_ID ?? 'local');
const REPORT = join(QA_DIR, 'assistant-battery-A.md');
const PASSWORD = process.env.QA_PANEL_PASSWORD ?? 'e2e-panel';
const OWNER = { email: 'e2e-assistant-qa-battery@example.com', password: PASSWORD };
const ADMIN = { email: 'e2e-assistant-admin@example.com', password: PASSWORD };
const BASE_BUSINESS = 'QA Base';
const NEW_BUSINESS = 'QA Asistente 31';
const RENAMED = 'QA Asistente 31b';
const CANCELLED_NAME = 'QA Base cancelada';
/** The panel's foot speaks of the month's messages from 80 % (`usageNote` of @erplora/ui). */
const FOOT_FROM = 0.8;
/** The question C35 repeats to bring the month to the foot's 80 %: a read, cheap and always the same. */
const QUOTA_QUESTION = '¿Qué negocios tengo?';

const REAL = realProviderMode(process.env);

interface Seeded {
  owner: string;
  business: string;
  model: string;
  fallback: string;
  chunks: ReportMeta['chunks'];
  appDocs: { lang: string; count: number }[];
  indexed: string[];
}

test.skip(!REAL, 'only with QA_REAL_PROVIDER=1: the real model with real keys (tests/e2e/README.md)');
test.describe.configure({ timeout: TURN_MS + 60_000 });

let context: BrowserContext | undefined;
let page: Page;
let chat: AssistantChat;
let seeded: Seeded;

/** The real providers, the account and the documentation index, once per run (a new worker after a failure reads what
 *  the first one did: the battery goes on with its businesses). */
function seedOnce(): Seeded {
  const marker = join(RESULTS, 'seed.json');
  if (existsSync(marker)) return JSON.parse(readFileSync(marker, 'utf8')) as Seeded;
  mkdirSync(RESULTS, { recursive: true });
  const { seed: made, indexed } = seedRealAssistant('es');
  const counts = JSON.parse(
    djangoPrint(
      [
        'import json',
        'from django.db.models import Count',
        'from apps.models import AppDoc',
        'from assistant.models import DocChunk',
        'chunks = list(DocChunk.objects.values("source", "lang").annotate(count=Count("id")).order_by("source", "lang"))',
        'docs = list(AppDoc.objects.values("lang").annotate(count=Count("id")).order_by("lang"))',
        'print(json.dumps({"chunks": chunks, "appDocs": docs}))',
      ].join('\n'),
    ),
  ) as Pick<Seeded, 'chunks' | 'appDocs'>;
  const result = { ...made, ...counts, indexed };
  writeFileSync(marker, JSON.stringify(result, null, 2));
  return result;
}

function readResults(): ItemResult[] {
  if (!existsSync(RESULTS)) return [];
  const order = [...BATTERY_A, ...BATTERY_C].map((item) => item.id);
  return readdirSync(RESULTS)
    .filter((name) => name !== 'seed.json' && name.endsWith('.json'))
    .map((name) => JSON.parse(readFileSync(join(RESULTS, name), 'utf8')) as ItemResult)
    .sort((a, b) => order.indexOf(a.item.id) - order.indexOf(b.item.id));
}

function writeReport(): void {
  if (!seeded) return;
  const meta: ReportMeta = {
    started: process.env.PW_RUN_ID ?? 'local',
    model: seeded.model,
    fallback: seeded.fallback,
    chunks: seeded.chunks,
    notes: [
      `Account ${seeded.owner} (es), one business «${seeded.business}» on the Free plan; 30 messages a month, as production`,
      `Hub app documentation (apps.AppDoc, written by the Hub's register_apps): ${seeded.appDocs.map((row) => `${row.lang} ${row.count}`).join(', ')}`,
      ...seeded.indexed.map((line) => `index_docs this run: ${line.replace(/^assistant\.index_docs /, '')}`),
      'Verdicts check tools, cards, notices and the API only; whether an answer is invented is judged by reading it',
    ],
  };
  mkdirSync(QA_DIR, { recursive: true });
  writeFileSync(REPORT, renderReport(meta, readResults()));
}

/** The month's messages of the account, as the panel's API says them. */
const usageNow = () => chat.usage();

async function businesses(): Promise<{ name: string; status?: string }[]> {
  const response = await page.request.get('/api/hubs/businesses?limit=50&offset=0');
  expect(response.status(), 'GET /api/hubs/businesses').toBe(200);
  return ((await response.json()) as { rows: { name: string; status?: string }[] }).rows;
}

async function apiKeys(): Promise<number> {
  const response = await page.request.get('/api/accounts/api-keys');
  expect(response.status(), 'GET /api/accounts/api-keys').toBe(200);
  const body = (await response.json()) as unknown;
  const rows = Array.isArray(body) ? body : ((body as { rows?: unknown[]; items?: unknown[] }).rows ?? (body as { items?: unknown[] }).items ?? []);
  return rows.length;
}

/** The card on screen: confirmed with the word it asks for when it is the item's expected write, cancelled otherwise. */
async function decide(item: Item, card: Locator): Promise<void> {
  const shown = await chat.lastCard();
  await page.screenshot({ path: join(QA_DIR, `${item.shot}-${item.slug}-card.png`) });
  const expected = item.decision === 'confirm' && shown !== undefined && (item.operations ?? []).includes(shown.operation);
  await chat.resolveCard(card, expected ? 'confirm' : 'cancel');
}

/** Follows the question's turns to their end, each card decided as the item says. */
const settle = (item: Item): Promise<void> => chat.settle(item.id, (card) => decide(item, card));

/** What the panel showed for the question: the answer, its links, receipts, notices, failures and foot. */
async function observe(item: Item, before: { used: number | null; limit: number | null }): Promise<Observed> {
  const shown = await chat.shown();
  const after = await usageNow();
  const screenshot = join(QA_DIR, `${item.shot}-${item.slug}.png`);
  await page.screenshot({ path: screenshot });
  return {
    asked: true,
    ...shown,
    turns: await chat.turns(),
    usage: { before: before.used, after: after.used, limit: after.limit ?? before.limit },
    check: null,
    screenshot,
  };
}

/** A new conversation, the question asked and followed to its end, and what the panel showed. */
async function askItem(item: Item, question = item.question): Promise<Observed> {
  await chat.newConversation();
  const before = await usageNow();
  await chat.send(question);
  await settle(item);
  return observe(item, before);
}

/** The item's result kept for the report, then its automatic verdict asserted. */
function record(item: Item, observed: Observed): void {
  const { verdict, reasons } = verdictOf(item, observed);
  mkdirSync(RESULTS, { recursive: true });
  writeFileSync(join(RESULTS, `${item.id}.json`), JSON.stringify({ item, observed, verdict, reasons } satisfies ItemResult, null, 2));
  writeReport();
  expect(verdict, `${item.id}: ${reasons.join('; ')}`).not.toBe('fail');
}

/** What the API shows after a write or a refusal (A2.12, A2.17, A2.18, A2.19, C36). */
async function checkAfter(item: Item, keysBefore: number): Promise<Check | null> {
  const names = (rows: { name: string; status?: string }[]) => rows.map((row) => `${row.name}${row.status ? ` (${row.status})` : ''}`).join(', ');
  switch (item.id) {
    case 'A2.12': {
      const rows = await businesses();
      return { ok: rows.some((row) => row.name === NEW_BUSINESS), detail: `businesses: ${names(rows)}` };
    }
    case 'A2.17': {
      const rows = await businesses();
      const ok = rows.some((row) => row.name === RENAMED) && !rows.some((row) => row.name === NEW_BUSINESS);
      return { ok, detail: `businesses: ${names(rows)}` };
    }
    case 'A2.18': {
      const rows = await businesses();
      const row = rows.find((entry) => entry.name === RENAMED);
      return { ok: !row || /delet/i.test(row.status ?? ''), detail: `businesses: ${names(rows)}` };
    }
    case 'A2.19': {
      const now = await apiKeys();
      return { ok: now === keysBefore, detail: `API keys: ${keysBefore} → ${now}` };
    }
    case 'C36': {
      const rows = await businesses();
      const ok = rows.some((row) => row.name === BASE_BUSINESS) && !rows.some((row) => row.name === CANCELLED_NAME);
      return { ok, detail: `businesses: ${names(rows)}` };
    }
    default:
      return null;
  }
}

test.beforeAll(async ({ browser }) => {
  test.setTimeout(900_000);
  if (!REAL) return;
  seeded = seedOnce();
  context = await browser.newContext({ baseURL: PANEL_URL, locale: 'es-ES', viewport: { width: 1440, height: 900 } });
  page = await context.newPage();
  chat = new AssistantChat(page);
  await signIn(page.request, OWNER);
  await page.goto('/dashboard/businesses');
  await expect(page.getByText(BASE_BUSINESS).first()).toBeVisible();
  await chat.open();
});

test.afterAll(async () => {
  writeReport();
  await context?.close();
});

for (const item of BATTERY_A) {
  test(`${item.id} ${item.question}`, async () => {
    const keysBefore = item.id === 'A2.19' ? await apiKeys() : 0;
    const observed = await askItem(item);
    observed.check = await checkAfter(item, keysBefore);
    record(item, observed);
  });
}

const [C35, C36, C38] = BATTERY_C;

test(`${C36.id} ${C36.question}`, async () => {
  const observed = await askItem(C36);
  observed.check = await checkAfter(C36, 0);
  record(C36, observed);
});

test(`${C35.id} the month's messages go up one per question, and the foot says it from 80 %`, async () => {
  // Every question of this run took one message (the card's answer costs none).
  const asked = readResults().filter((result) => result.observed.asked && result.item.id !== C35.id);
  const steps = asked.map((result) => {
    const { before, after } = result.observed.usage;
    return { id: result.item.id, before, after, ok: before !== null && after === before + 1 };
  });
  const wrong = steps.filter((step) => !step.ok).map((step) => `${step.id} ${step.before} → ${step.after}`);
  // Then the month up to the foot's 80 %, and one more: the foot appears and counts down.
  const feet: string[] = [];
  let usage = await usageNow();
  const limit = usage.limit ?? 0;
  let last: Observed | undefined;
  while (limit && usage.used !== null && usage.used < limit && feet.length < 2) {
    last = await askItem(C35, QUOTA_QUESTION);
    usage = await usageNow();
    if (last.usage.after !== (last.usage.before ?? -2) + 1) wrong.push(`C35 ${last.usage.before} → ${last.usage.after}`);
    if ((usage.used ?? 0) >= Math.ceil(limit * FOOT_FROM)) feet.push(last.footer || '(no foot)');
  }
  const left = (foot: string) => Number(/(\d+) de \d+/.exec(foot)?.[1] ?? NaN);
  const footOk = feet.length === 2 && left(feet[1]) === left(feet[0]) - 1;
  const observed: Observed = {
    ...(last ?? {
      answer: '',
      links: [],
      receipts: [],
      notices: [],
      failures: [],
      turns: { tools: [], cards: [], citations: [], errors: [] },
      screenshot: '',
    }),
    asked: false,
    footer: feet.join(' → '),
    usage: { before: steps[0]?.before ?? null, after: usage.used, limit: usage.limit },
    check: {
      ok: wrong.length === 0 && footOk,
      detail: [
        `${steps.length} questions, each +1: ${wrong.length ? `no: ${wrong.join(', ')}` : 'yes'}`,
        `${steps.map((step) => `${step.id} ${step.before}→${step.after}`).join(', ')}`,
        `foot from ${Math.ceil(limit * FOOT_FROM)} of ${limit}: ${feet.length ? feet.map((foot) => `«${foot}»`).join(' then ') : 'never reached'}`,
      ].join(' · '),
    },
  };
  record(C35, observed);
});

test(`${C38.id} the admin's usage row of the account counts its messages and their cost`, async ({ browser }) => {
  const { used } = await usageNow();
  const staff = await browser.newContext({ baseURL: PANEL_URL, locale: 'es-ES', viewport: { width: 1440, height: 900 } });
  try {
    const admin = await staff.newPage();
    await signIn(admin.request, ADMIN);
    await admin.goto(`/admin/assistant/assistantusage/?q=${encodeURIComponent(OWNER.email)}`);
    const row = admin.locator('#result_list tbody tr').first();
    await expect(row).toBeVisible();
    const messages = Number((await row.locator('td.field-messages').innerText()).trim());
    const cost = (await row.locator('td.field-cost').innerText()).trim();
    const spender = (await row.locator('th.field-spender, td.field-spender').first().innerText()).trim();
    const screenshot = join(QA_DIR, `${C38.shot}-${C38.slug}.png`);
    await admin.screenshot({ path: screenshot, fullPage: true });
    const observed: Observed = {
      asked: false,
      answer: '',
      links: [],
      receipts: [],
      notices: [],
      failures: [],
      footer: '',
      turns: { tools: [], cards: [], citations: [], errors: [] },
      usage: { before: null, after: used, limit: null },
      check: {
        ok: spender === OWNER.email && used !== null && messages === used,
        detail: `admin row «${spender}»: ${messages} messages, cost ${cost} USD; the panel's API: ${used} used`,
      },
      screenshot,
    };
    record(C38, observed);
  } finally {
    await staff.close();
  }
});
