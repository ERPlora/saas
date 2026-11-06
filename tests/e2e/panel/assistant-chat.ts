// The panel's assistant as the QA specs with the real model drive it (assistant-battery.spec.ts and
// assistant-probes.spec.ts): the turns it streams (`/api/assistant/turn`, read back as frames by `summarizeTurns`), a
// question typed and followed to its end with its cards decided, and what the panel showed for it; and the seed both
// start from: the real providers, the account «QA Base» and the documentation index (`assistant_seed.py real`). And for
// the specs on the e2e's own model (assistant-provider.ts): its server and seed for a spec's file (`localAssistant`), the
// panel open for an account (`openPanel`) and a question typed in the composer (`ask`). And for the staff's specs
// (assistant-admin.spec.ts, assistant-gateway.spec.ts): the Python double of a provider (`startFakeProvider`).
import { type ChildProcess, execFileSync, spawn } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import type { Locator, Page } from '@playwright/test';

import { type Card, summarizeTurns, type Turns } from '../assistant-battery';
import { redactedError } from '../assistant-probes';
import { type Provider, startProvider } from '../assistant-provider';
import { djangoEnv } from '../django-env';
import { STACK } from '../stack';
import { expect, signIn, test } from './fixtures';

const SAAS_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');

/** The account `assistant_seed.py panel` makes, with its one business. */
export const OWNER = { email: 'e2e-assistant-owner@example.com', password: process.env.QA_PANEL_PASSWORD ?? 'e2e-panel' };
/** The panel's three sizes, for a spec's screenshots. */
export const SIZES = [
  { name: '1440', width: 1440, height: 900 },
  { name: '834', width: 834, height: 1112 },
  { name: '390', width: 390, height: 844 },
] as const;

/** How long one question may take, cards included: the real model, its tools and the documentation search. */
export const TURN_MS = 240_000;
/** How long nothing moves before a turn counts as over. */
const QUIET_MS = 2_500;

/** The address of `assistant.tests.fake_provider`, on its own port in the run's block (stack.ts): +8 is reCAPTCHA's double. */
export const FAKE_PROVIDER_URL = `http://127.0.0.1:${STACK.aiProviderPort}/v1`;

/** `assistant.tests.fake_provider` started on its port and answering its models (stopped again if it never does). */
export async function startFakeProvider(): Promise<ChildProcess> {
  const provider = spawn('uv', ['run', 'python', '-m', 'assistant.tests.fake_provider', '--port', String(STACK.aiProviderPort)], {
    cwd: SAAS_DIR,
    env: djangoEnv(true),
    stdio: 'ignore',
  });
  try {
    await expect
      .poll(
        async () => {
          try {
            return (await fetch(`${FAKE_PROVIDER_URL}/models`)).status;
          } catch {
            return 0;
          }
        },
        { timeout: 30_000, message: `the fake provider on :${STACK.aiProviderPort}` },
      )
      .toBe(200);
  } catch (error) {
    provider.kill();
    throw error;
  }
  return provider;
}

/** `uv run <args>` from the SaaS against the run's database, its output (the keys stay in the seed's environment);
 *  a failure's message (with the command's output) reaches the console without the real keys. */
export function uvRun(args: string[], extra: Record<string, string> = {}): string {
  try {
    return execFileSync('uv', ['run', ...args], {
      cwd: SAAS_DIR,
      env: { ...djangoEnv(true), ...extra },
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
      timeout: 900_000,
    }).trim();
  } catch (error) {
    throw redactedError(error, [process.env.QA_QWEN_API_KEY, process.env.QA_OPENAI_API_KEY]);
  }
}

/** What `assistant_seed.py real` made: the account, its business and the models. */
export interface RealSeed {
  owner: string;
  business: string;
  slug: string;
  model: string;
  fallback: string;
}

/** The real providers (keys from `QA_QWEN_API_KEY` and `QA_OPENAI_API_KEY`, read by the seed only) and the account
 *  owner of «QA Base» in `language`, then the documentation index (idempotent: only the excerpts that changed since the
 *  last run are embedded again) and its lines of this run. */
export function seedRealAssistant(language = 'es'): { seed: RealSeed; indexed: string[] } {
  const seed = JSON.parse(uvRun(['python', 'tests/e2e/panel/assistant_seed.py', 'real', language]).split('\n').pop() ?? '{}') as RealSeed;
  const indexed = uvRun(['python', 'manage.py', 'index_docs'], { ASSISTANT_SERVICE_PROVIDER: 'openai' })
    .split('\n')
    .filter((line) => /^assistant\.index_docs source=/.test(line));
  return { seed, indexed };
}

/** The real keys and the QA accounts out of the run's e2e database (`assistant_seed.py forget`; it refuses any other):
 *  after a worker, whatever happened to it. */
export function forgetRealAssistant(): void {
  uvRun(['python', 'tests/e2e/panel/assistant_seed.py', 'forget']);
}

/** The e2e's own model for the tests of a spec's file, on `port` (0: any free one): started before them and, with what
 *  the seed left, gone after them. `seed` is `assistant_seed.py <action> <its address> <language>`: always from scratch. */
export function localAssistant(port = 0): {
  provider: () => Provider;
  seed: (action: 'clear' | 'panel' | 'paying', language?: 'es' | 'en') => void;
} {
  let provider: Provider | undefined;
  const seed = (action: 'clear' | 'panel' | 'paying', language: 'es' | 'en' = 'es'): void => {
    uvRun(['python', 'tests/e2e/panel/assistant_seed.py', action, provider?.url ?? '', language]);
  };
  test.beforeAll(async () => {
    provider = await startProvider(port);
  });
  test.afterAll(async () => {
    seed('clear');
    await provider?.close();
  });
  return { provider: () => provider!, seed };
}

/** `OWNER` signed in on the businesses at 1440, with the assistant's panel open: that panel. */
export async function openPanel(page: Page): Promise<Locator> {
  await signIn(page.request, OWNER);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/dashboard/businesses');
  await page.getByTestId('assistant-button').click();
  const panel = page.getByTestId('assistant-panel');
  await expect(panel).toHaveAttribute('data-open', 'true');
  return panel;
}

/** Writes `text` in the composer and sends it, once the turn before is over. */
export async function ask(page: Page, text: string): Promise<void> {
  await expect(page.getByTestId('assistant-stop')).toHaveCount(0);
  await page.getByTestId('assistant-input').locator('textarea').fill(text);
  await page.getByTestId('assistant-send').click();
}

const isTurn = (url: string): boolean => new URL(url).pathname === '/api/assistant/turn';

/** What the panel showed under a question. */
export interface Shown {
  /** The assistant's bubbles of the conversation, in order. */
  answer: string;
  /** The links of the answer, and its «go» buttons as `button: <label>`. */
  links: string[];
  receipts: string[];
  /** The notices under the answer, by the suffix of their `assistant-notice-<notice>`. */
  notices: string[];
  failures: string[];
  /** The panel's foot about the month's messages (shown from 80 %), or empty. */
  footer: string;
}

export interface Usage {
  used: number | null;
  limit: number | null;
}

async function texts(locator: Locator): Promise<string[]> {
  return (await locator.allInnerTexts()).map((value) => value.trim()).filter(Boolean);
}

/** The assistant's panel of one page: it keeps the bodies of the turns of the question being asked. */
export class AssistantChat {
  readonly page: Page;
  private bodies: Promise<string>[] = [];
  private streaming = 0;

  constructor(page: Page) {
    this.page = page;
    page.on('request', (request) => {
      if (isTurn(request.url())) this.streaming += 1;
    });
    const ended = (request: { url(): string }) => {
      if (isTurn(request.url())) this.streaming = Math.max(0, this.streaming - 1);
    };
    page.on('requestfinished', ended);
    page.on('requestfailed', ended);
    page.on('response', (response) => {
      if (isTurn(response.url())) this.bodies.push(response.text().catch(() => ''));
    });
  }

  /** Opens the panel when it is closed. */
  async open(): Promise<void> {
    const panel = this.page.getByTestId('assistant-panel');
    if ((await panel.getAttribute('data-open')) !== 'true') await this.page.getByTestId('assistant-button').click();
    await expect(panel).toHaveAttribute('data-open', 'true');
  }

  /** The month's messages of the account, as the panel's API says them. */
  async usage(): Promise<Usage> {
    const response = await this.page.request.get('/api/assistant/usage');
    if (!response.ok()) return { used: null, limit: null };
    const body = (await response.json()) as { used?: number; limit?: number };
    return { used: body.used ?? null, limit: body.limit ?? null };
  }

  /** A new conversation, with no turn of the one before kept. */
  async newConversation(): Promise<void> {
    if (await this.page.getByTestId('assistant-new').isVisible()) await this.page.getByTestId('assistant-new').click();
    await expect(this.page.getByTestId('assistant-bubble-user')).toHaveCount(0);
    this.bodies = [];
  }

  /** Writes `text` in the composer and sends it, once the turn before is over. */
  async send(text: string): Promise<void> {
    await ask(this.page, text);
  }

  /** What the turns of the question streamed so far. */
  async turns(): Promise<Turns> {
    return summarizeTurns(await Promise.all(this.bodies));
  }

  /** The card the last turn showed, as its frame said it. */
  async lastCard(): Promise<Card | undefined> {
    return (await this.turns()).cards.at(-1);
  }

  /** Follows the question's turns to their end: no turn streaming, nothing «writing», and quiet for a while; each
   *  card on screen goes to `onCard`, which decides it (`resolveCard`). */
  async settle(label: string, onCard: (card: Locator) => Promise<void>): Promise<void> {
    const deadline = Date.now() + TURN_MS;
    let quietSince = 0;
    while (Date.now() < deadline) {
      await this.page.waitForTimeout(400);
      const card = this.page.getByTestId('assistant-confirm');
      if (this.streaming === 0 && (await card.isVisible())) {
        await onCard(card);
        quietSince = 0;
        continue;
      }
      const busy = this.streaming > 0 || this.bodies.length === 0 || (await this.page.getByTestId('assistant-stop').count()) > 0;
      if (busy) {
        quietSince = 0;
        continue;
      }
      quietSince ||= Date.now();
      if (Date.now() - quietSince >= QUIET_MS) return;
    }
    throw new Error(`${label}: the turn did not end in ${TURN_MS / 1000} s`);
  }

  /** Confirms the card on screen (typing the word it asks for, if any) or cancels it. */
  async resolveCard(card: Locator, decision: 'confirm' | 'cancel'): Promise<void> {
    if (decision === 'cancel') {
      await this.page.getByTestId('assistant-confirm-cancel').click();
      await expect(card).toBeHidden();
      return;
    }
    const prompt = card.locator('.ep-confirm-dialog__prompt strong');
    if (await prompt.count()) {
      await this.page.getByTestId('assistant-confirm-input').locator('input').fill((await prompt.innerText()).trim());
    }
    await this.page.getByTestId('assistant-confirm-submit').click();
    await expect(card).toBeHidden();
  }

  /** What the panel shows now: the answer, its links, receipts, notices, failures and foot. */
  async shown(): Promise<Shown> {
    const answers = this.page.getByTestId('assistant-bubble-assistant');
    const links = await answers.locator('a[href]').evaluateAll((anchors) => anchors.map((anchor) => (anchor as HTMLAnchorElement).href));
    const goes = await texts(this.page.getByTestId('assistant-go'));
    const notices = await this.page
      .locator('[data-testid^="assistant-notice-"]')
      .evaluateAll((nodes) => nodes.map((node) => node.getAttribute('data-testid')?.replace('assistant-notice-', '') ?? ''));
    const foot = this.page.getByTestId('assistant-usage');
    return {
      answer: (await texts(answers)).join('\n\n'),
      links: [...links, ...goes.map((go) => `button: ${go}`)],
      receipts: await texts(this.page.getByTestId('assistant-receipt')),
      notices,
      failures: await texts(this.page.getByTestId('assistant-failure')),
      footer: (await foot.count()) ? (await foot.innerText()).trim() : '',
    };
  }
}
