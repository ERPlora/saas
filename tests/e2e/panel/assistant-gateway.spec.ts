// The assistant's doors of the Hub (assistant/WORKBOOK.md, ASSISTANT-F11 to F24),
// called by HTTP as the Hub calls them: signed with the shared secret (accounts.signing, v1 and v2), against the
// panel's own Django and the rows of assistant_seed.py («gateway»). The provider is assistant.tests.fake_provider, a
// real HTTP server on 127.0.0.1 that speaks OpenAI's API (the turn streamed in three pieces, two fingerprints and a
// dictation): no test reaches a real provider and no real key is ever typed. Then «Assistant usage» in erplora.com's
// admin at the three sizes (390×844, 834×1112, 1440×900), in English and in Spanish.
//
// The CI runs it on every push (job `e2e` of test.yml, e2e-specs.sh): a change to a door touches no screen, so nobody runs it by hand.
// flow: ASSISTANT-F11 — only a signed call of a working business passes; it names the business it is for.
// flow: ASSISTANT-F12 — a turn answered live, piece by piece, ending with the allowance left.
// flow: ASSISTANT-F13 — the same turn answered at once.
// flow: ASSISTANT-F15 — a turn refused with its code before the model is called.
// flow: ASSISTANT-F18 — each turn spends one message of the plan; a demo has its own few.
// flow: ASSISTANT-F20 — the fingerprints of the Hub's texts, in their order.
// flow: ASSISTANT-F21 — a dictation turned into its text.
// flow: ASSISTANT-F22 — asked to read an answer aloud, the door says it cannot, and the caller uses the device's voice.
// flow: ASSISTANT-F23 — the report of an answer, mailed once.
// flow: ASSISTANT-F24 — the staff see what each business spent and what it cost, without changing it.
import type { ChildProcess } from 'node:child_process';
import { createHmac } from 'node:crypto';

import type { APIRequestContext, APIResponse } from '@playwright/test';

import { FAKE_PROVIDER_URL, startFakeProvider } from './assistant-chat';
import { captureAtEverySize, expect, internalSecret, runSeed, signIn, test, watchPageErrors } from './fixtures';

const atEverySize = captureAtEverySize('APP-ASSISTANT-2');

const PASSWORD = process.env.QA_PANEL_PASSWORD ?? 'e2e-panel';
const ADMIN = { email: 'e2e-assistant-admin@example.com', password: PASSWORD };

interface Gateway {
  limit: number;
  bar: string;
  spent: string;
  demo: string;
}

let provider: ChildProcess | undefined;
let secret = '';

/** `assistant_seed.py <action> <provider address>`: always from scratch; «gateway» says what it made. */
function seed(action: 'clear' | 'gateway'): Gateway {
  const last = runSeed('assistant_seed.py', [action, FAKE_PROVIDER_URL]);
  return action === 'gateway' ? (JSON.parse(last) as Gateway) : ({} as Gateway);
}

/** The headers the Hub signs a call with: its time, v1 over the body and v2 over the method, the path and the body. */
function signed(path: string, body: string, key = secret): Record<string, string> {
  const timestamp = Math.floor(Date.now() / 1000);
  return {
    'Content-Type': 'application/json',
    'X-Erplora-Timestamp': String(timestamp),
    'X-Erplora-Signature': createHmac('sha256', key).update(`${timestamp}.${body}`).digest('hex'),
    'X-Erplora-Signature-V2': createHmac('sha256', key)
      .update(`v2\n${timestamp}\nPOST\n${path}\n${body}`)
      .digest('hex'),
  };
}

/** A POST to one of the doors as the Hub makes it (signed unless `key` is another secret). */
async function call(request: APIRequestContext, path: string, payload: unknown, key?: string): Promise<APIResponse> {
  const body = JSON.stringify(payload);
  return request.post(path, { headers: signed(path, body, key), data: body });
}

/** The frames of a streamed answer, in order: each `data:` line's JSON, or `"[DONE]"`. */
function frames(text: string): unknown[] {
  return text
    .split('\n\n')
    .map((event) => event.trim())
    .filter((event) => event.startsWith('data: '))
    .map((event) => event.slice('data: '.length))
    .map((data) => (data === '[DONE]' ? data : JSON.parse(data)));
}

const turn = (hub: string, text = 'How many appointments do I have today?') => ({
  hub,
  messages: [{ role: 'user', content: text }],
  instructions: 'You are the assistant of a business.',
});

test.beforeAll(async () => {
  secret = await internalSecret();
  provider = await startFakeProvider();
});

test.afterAll(() => {
  seed('clear');
  provider?.kill();
});

test('ASSISTANT-F11: only a signed call of a working business passes, and it names the business', async ({ request }) => {
  const made = seed('gateway');

  const unsigned = await request.post('/internal/assistant/usage', { data: JSON.stringify({ hub: made.bar }) });
  expect(unsigned.status()).toBe(401);
  expect((await unsigned.json()).error.code).toBe('unauthorized');

  const otherSecret = await call(request, '/internal/assistant/usage', { hub: made.bar }, 'not-the-secret');
  expect(otherSecret.status()).toBe(401);

  const unknown = await call(request, '/internal/assistant/usage', { hub: 'e2e-assistant-nobody' });
  expect(unknown.status()).toBe(404);
  expect((await unknown.json()).error.code).toBe('hub_unknown');

  const usage = await call(request, '/internal/assistant/usage', { hub: made.bar });
  expect(usage.status()).toBe(200);
  expect(await usage.json()).toMatchObject({ used: 0, limit: made.limit, demo: false });
});

test('ASSISTANT-F12 · ASSISTANT-F18: a turn of the Hub is answered live and spends one message of the plan', async ({ request }) => {
  const made = seed('gateway');

  const response = await call(request, '/internal/assistant/chat/stream', turn(made.bar));

  expect(response.status()).toBe(200);
  expect(response.headers()['content-type']).toContain('text/event-stream');
  const got = frames(await response.text());
  const pieces = got.filter((frame) => (frame as { type?: string }).type === 'text_delta');
  expect(pieces).toEqual([
    { type: 'text_delta', text: 'Hello' },
    { type: 'text_delta', text: ' from the' },
    { type: 'text_delta', text: ' test model.' },
  ]);
  expect(got.at(-3)).toMatchObject({ type: 'response', usage: { input_tokens: 1200, output_tokens: 300 }, continuation: null });
  expect(got.at(-2)).toMatchObject({ type: 'usage', used: 1, limit: made.limit, demo: false });
  expect(got.at(-1)).toBe('[DONE]');
});

test('ASSISTANT-F13: the same turn is answered at once, with the allowance left', async ({ request }) => {
  const made = seed('gateway');

  const response = await call(request, '/internal/assistant/chat', turn(made.bar));

  expect(response.status()).toBe(200);
  const body = await response.json();
  expect(JSON.stringify(body.output)).toContain('Hello from the test model.');
  expect(body).toMatchObject({ usage: { input_tokens: 1200, output_tokens: 300 }, continuation: null });
  expect(body.quota).toMatchObject({ used: 1, limit: made.limit });
});

test('ASSISTANT-F15 · ASSISTANT-F18: a business with its messages spent is refused before the model, told to go up a plan', async ({ request }) => {
  const made = seed('gateway');

  const response = await call(request, '/internal/assistant/chat/stream', turn(made.spent));

  expect(response.status()).toBe(429);
  const { error } = await response.json();
  expect(error).toMatchObject({
    code: 'assistant.quota_exceeded',
    upgrade_required: true,
    used: made.limit,
    limit: made.limit,
    retriable: false,
  });
  expect(error.resets_at).toMatch(/^\d{4}-\d{2}-01T00:00:00/);
});

test('ASSISTANT-F18: a demo has its own few messages, which never come back', async ({ request }) => {
  const made = seed('gateway');

  await call(request, '/internal/assistant/chat', turn(made.demo));
  const usage = await call(request, '/internal/assistant/usage', { hub: made.demo });

  expect(await usage.json()).toEqual({ used: 1, limit: 10, resets_at: null, demo: true });
});

test('ASSISTANT-F20: the fingerprints of the Hub\'s texts come back in their order', async ({ request }) => {
  const made = seed('gateway');

  const response = await call(request, '/internal/assistant/embeddings', {
    hub: made.bar,
    texts: ['Appointments: book, move and cancel', 'Sales: charge at the till'],
  });

  expect(response.status()).toBe(200);
  expect(await response.json()).toEqual({
    embeddings: [
      [0.1, 0.2, 0.3],
      [0.4, 0.5, 0.6],
    ],
    model: 'text-embedding-3-small',
  });
});

test('ASSISTANT-F21: a dictation is turned into its text', async ({ request }) => {
  const made = seed('gateway');

  const response = await call(request, '/internal/speech/transcribe', {
    hub: made.bar,
    audio: Buffer.from('a few bytes of webm audio').toString('base64'),
    mime_type: 'audio/webm;codecs=opus',
    language: 'en-GB',
  });

  expect(response.status()).toBe(200);
  expect(await response.json()).toEqual({ text: 'How many appointments do I have today?', language: 'en' });
});

test('ASSISTANT-F22: asked to read an answer aloud, the door says it cannot and spends nothing', async ({ request }) => {
  const made = seed('gateway');
  const withoutLanguage = { hub: made.bar, text: 'You have two appointments today.' };
  const reading = { ...withoutLanguage, language: 'en' };
  const speak = (payload: unknown) => call(request, '/internal/speech/synthesize', payload);
  const used = async () => (await (await call(request, '/internal/assistant/usage', { hub: made.bar })).json()).used;
  const before = await used();

  // What the Hub sends (base/assistant.py, `speak`): the voice only when one was chosen. The 503 is what it reads with the device's voice on.
  for (const asked of [reading, { ...reading, voice: 'nova' }]) {
    const response = await speak(asked);

    expect(response.status()).toBe(503);
    expect((await response.json()).error).toMatchObject({ code: 'assistant.speech_unavailable', retriable: false });
  }
  expect(await used()).toBe(before);

  for (const [refused, field] of [
    [withoutLanguage, 'language'],
    [{ ...reading, language: 'fr' }, 'language'],
    [{ ...reading, text: '   ' }, 'text'],
  ] as const) {
    const response = await speak(refused);

    expect(response.status()).toBe(422);
    const { error } = await response.json();
    expect(error.code).toBe('invalid_payload');
    expect(Object.keys(error.fields)).toContain(field);
  }
});

test('ASSISTANT-F23: the report of an answer reaches support once', async ({ request }) => {
  const made = seed('gateway');
  const report = {
    hub: made.bar,
    message_id: `e2e-${Date.now()}`,
    reason: 'incorrect',
    comment: 'It said three appointments; there are two.',
    question: 'How many appointments do I have today?',
    answer: 'You have three appointments today.',
  };

  const first = await call(request, '/internal/assistant/report', report);
  const again = await call(request, '/internal/assistant/report', report);

  expect(first.status()).toBe(202);
  expect(await first.json()).toEqual({ sent: true, duplicate: false });
  expect(await again.json()).toEqual({ sent: false, duplicate: true });
});

/** A turn of the bar and one of the demo, so «Assistant usage records» has a business, a spent one and a demo. */
async function spend(request: APIRequestContext, made: Gateway): Promise<void> {
  expect((await call(request, '/internal/assistant/chat', turn(made.bar))).status()).toBe(200);
  expect((await call(request, '/internal/assistant/chat', turn(made.demo))).status()).toBe(200);
}

test('ASSISTANT-F24: the staff see what each business spent and what it cost, and cannot change it', async ({ page, request }) => {
  const errors = watchPageErrors(page);
  const made = seed('gateway');
  await spend(request, made);
  await signIn(page.request, ADMIN);

  await page.goto('/admin/assistant/assistantusage/');
  const bar = page.getByRole('row', { name: /E2E Bar Asistente/ });
  await atEverySize(page, 'ASSISTANT-F24', async () => {
    await expect(page.getByRole('heading', { level: 1, name: /assistant usage record/i })).toBeVisible();
    await expect(bar).toContainText('1200');
    // (1200 × 1 + 300 × 2) / 1 000 000 USD.
    await expect(bar).toContainText('0.0018');
  });
  // The cost and the messages are read without scrolling the table, at the desk's width.
  await expect(page.getByRole('columnheader', { name: 'Cost (USD)' })).toBeInViewport({ ratio: 1 });
  await expect(page.getByRole('columnheader', { name: 'Messages' })).toBeInViewport({ ratio: 1 });
  await expect(page.getByRole('row', { name: /E2E Sin Mensajes/ })).toContainText(String(made.limit));
  await expect(page.getByRole('row', { name: new RegExp(made.demo) })).toBeVisible();
  await expect(page.getByRole('link', { name: /Add assistant usage/i })).toHaveCount(0);

  await page.getByRole('link', { name: 'Demos' }).click();
  await expect(page.getByRole('row', { name: new RegExp(made.demo) })).toBeVisible();
  await expect(page.getByRole('row', { name: /E2E Bar Asistente/ })).toHaveCount(0);

  await page.goto('/admin/assistant/assistantusage/');
  await page.getByRole('link', { name: /E2E Bar Asistente/ }).click();
  await atEverySize(page, 'ASSISTANT-F24-row', async () => {
    await expect(page.getByText('1200', { exact: true })).toBeVisible();
    await expect(page.locator('input[name="messages"]')).toHaveCount(0);
  });
  await expect(page.getByRole('button', { name: 'Save', exact: true })).toHaveCount(0);
  expect(errors).toEqual([]);
});

test.describe('in Spanish', () => {
  test.use({ locale: 'es-ES' });

  test('ASSISTANT-F24: «Registros de uso del asistente» speaks the staff\'s language', async ({ page, request }) => {
    const errors = watchPageErrors(page);
    const made = seed('gateway');
    await spend(request, made);
    await signIn(page.request, ADMIN);

    await page.goto('/admin/assistant/assistantusage/');
    await atEverySize(page, 'ASSISTANT-F24-es', async () => {
      await expect(page.getByRole('heading', { level: 1, name: /registro de uso del asistente/i })).toBeVisible();
      await expect(page.getByRole('columnheader', { name: 'Coste (USD)' })).toBeVisible();
      // Since ASSISTANT-F26 an account has its rows too (assistant/admin.py `business, demo or account`).
      await expect(page.getByRole('columnheader', { name: 'Negocio, demo o cuenta' })).toBeVisible();
      await expect(page.getByRole('link', { name: 'Negocios' })).toBeVisible();
      await expect(page.getByText('3 registros de uso del asistente')).toBeVisible();
    });
    expect(errors).toEqual([]);
  });
});
