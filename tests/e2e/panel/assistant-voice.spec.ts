// «Read aloud» of the panel's assistant (assistant/WORKBOOK.md, ASSISTANT-F22), in a browser against the panel's own Django.
// erplora.com has no voice of its own (PLAN-SAAS round 2026-11-04c): the page says so (`spa-config.assistantSpeech`,
// base/spa.py), so the chat offers no choice of voice and reads each answer in the device's, with no request to
// `/api/assistant/speak`. A page told otherwise (the flag turned on at the edge, everything behind it real) asks the
// server, whose door answers 503 `assistant.speech_unavailable`, and the device reads it, with no error on the page.
// In Spanish and in English, at 1440, 834 and 390 (screenshots under `.artifacts/panel/`).
// The device's voice is the browser's `speechSynthesis`, which a headless Chrome cannot sound: the page's `speak` is
// replaced by a recorder that ends each utterance at once, as the fake microphone stands in for the dictation's.
// The model is assistant-provider.ts, a real HTTP server on 127.0.0.1 set by assistant_seed.py «panel».
// flow: ASSISTANT-F22 — read an answer aloud: the device's voice, and the door shut without an engine.
import { execFileSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import type { Locator, Page } from '@playwright/test';

import { type Provider, startProvider } from '../assistant-provider';
import { djangoEnv } from '../django-env';
import { expect, settled, shot, signIn, test, watchPageErrors } from './fixtures';

const SAAS_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const OWNER = { email: 'e2e-assistant-owner@example.com', password: process.env.QA_PANEL_PASSWORD ?? 'e2e-panel' };
const SIZES = [
  { name: '1440', width: 1440, height: 900 },
  { name: '834', width: 834, height: 1112 },
  { name: '390', width: 390, height: 844 },
] as const;

/** What the person sees and hears, in each language (the package's words, `assistant.speech.*`). */
const WORDS = {
  es: {
    question: 'Hola',
    answer: 'Hola, soy el asistente de prueba.',
    listen: 'Leer en voz alta',
    device: 'es-ES',
  },
  en: {
    question: 'Hello',
    answer: 'Hello, I am the test assistant.',
    listen: 'Read aloud',
    device: 'en-US',
  },
} as const;

let provider: Provider | undefined;

function seed(action: 'clear' | 'panel', language: 'es' | 'en' = 'es'): void {
  execFileSync('uv', ['run', 'python', 'tests/e2e/panel/assistant_seed.py', action, provider?.url ?? '', language], {
    cwd: SAAS_DIR,
    env: djangoEnv(true),
    stdio: 'pipe',
  });
}

test.beforeAll(async () => {
  provider = await startProvider(0);
});

test.afterAll(async () => {
  seed('clear');
  await provider?.close();
});

test.beforeEach(async ({ page }) => {
  // The device's voice, recorded: what it was asked to read and in which language, each utterance ended at once.
  await page.addInitScript(() => {
    const spoken: Array<{ text: string; lang: string }> = [];
    Object.defineProperty(window, '__spoken', { value: spoken });
    window.speechSynthesis.speak = (utterance: SpeechSynthesisUtterance) => {
      spoken.push({ text: utterance.text, lang: utterance.lang });
      setTimeout(() => utterance.dispatchEvent(new Event('end')), 10);
    };
  });
});

/** What the device's voice was asked to read, in which language. */
function spoken(page: Page): Promise<Array<{ text: string; lang: string }>> {
  return page.evaluate(() => (window as unknown as { __spoken: Array<{ text: string; lang: string }> }).__spoken);
}

/** Every request the page makes for a reading in a server voice. */
function speakRequests(page: Page): string[] {
  const seen: string[] = [];
  page.on('request', (request) => {
    if (new URL(request.url()).pathname === '/api/assistant/speak') seen.push(request.method());
  });
  return seen;
}

/** The console's errors, but the browser's own line for an answer that is not 2xx (the network's, not the page's). */
function watchConsoleErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('console', (message) => {
    if (message.type() === 'error' && !message.text().startsWith('Failed to load resource')) errors.push(message.text());
  });
  return errors;
}

/** The chat open on the panel, signed in as the owner, at 1440. */
async function openChat(page: Page) {
  await signIn(page.request, OWNER);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/dashboard/businesses');
  await page.getByTestId('assistant-button').click();
  const panel = page.getByTestId('assistant-panel');
  await expect(panel).toHaveAttribute('data-open', 'true');
  return panel;
}

/** Asks `question` and gives back the answer's «Read aloud», checked at every size. */
async function answerAndListen(page: Page, panel: Locator, words: (typeof WORDS)['es' | 'en'], shotName: string) {
  await panel.getByTestId('assistant-input').locator('textarea').fill(words.question);
  await panel.getByTestId('assistant-send').click();
  const answer = panel.getByTestId('assistant-bubble-assistant').last();
  await expect(answer).toContainText(words.answer);
  // Under the answer, beside «Report a problem» (outside its bubble).
  const listen = panel.getByTestId('assistant-listen').last();
  await expect(listen).toContainText(words.listen);
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await expect(listen).toBeVisible();
    await settled(page);
    await page.screenshot({ path: shot(`${shotName}-${size.name}`) });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  return listen;
}

for (const language of ['es', 'en'] as const) {
  const words = WORDS[language];

  test(`without a voice of the server the chat offers none and reads in the device's, never asking the server (${language})`, async ({
    page,
  }) => {
    seed('panel', language);
    const errors = watchPageErrors(page);
    const consoleErrors = watchConsoleErrors(page);
    const asked = speakRequests(page);
    const panel = await openChat(page);

    // No choice of voice: the only voice is the device's.
    await expect(panel.getByTestId('assistant-voice')).toHaveCount(0);
    const listen = await answerAndListen(page, panel, words, `assistant-voice-device-answer-${language}`);
    await expect(panel.getByTestId('assistant-voice')).toHaveCount(0);

    await listen.click();
    await expect.poll(() => spoken(page)).toEqual([expect.objectContaining({ text: words.answer, lang: words.device })]);
    expect(asked).toEqual([]);
    await expect(panel.getByTestId('assistant-listen-failed')).toHaveCount(0);
    await expect(listen).toContainText(words.listen);
    await settled(page);
    await page.screenshot({ path: shot(`assistant-voice-device-${language}`) });

    expect(errors).toEqual([]);
    expect(consoleErrors).toEqual([]);
  });

  test(`a page told there is a voice asks the server, whose door is shut, and the device reads (${language})`, async ({ page }) => {
    seed('panel', language);
    // The shell as an engine would leave it: the real page with its flag turned on as it is parsed, before the SPA's
    // module runs, and everything behind it real. Not with `route.fulfill`: Chrome gives a page served that way no
    // address, and refuses it the Vite server's scripts.
    await page.addInitScript(() => {
      const observer = new MutationObserver(() => {
        const config = document.getElementById('spa-config');
        const told = config?.textContent?.replace('"assistantSpeech": false', '"assistantSpeech": true');
        if (!config || told === undefined || told === config.textContent) return;
        config.textContent = told;
        observer.disconnect();
      });
      observer.observe(document, { childList: true, subtree: true });
    });
    const errors = watchPageErrors(page);
    const consoleErrors = watchConsoleErrors(page);
    const panel = await openChat(page);

    // Nothing to choose: `@erplora/ui` names no voices, and the host gives none.
    await expect(panel.getByTestId('assistant-voice')).toHaveCount(0);
    const listen = await answerAndListen(page, panel, words, `assistant-voice-door-answer-${language}`);

    const answered = page.waitForResponse((response) => new URL(response.url()).pathname === '/api/assistant/speak');
    await listen.click();
    const response = await answered;
    expect(response.status()).toBe(503);
    expect((await response.json()).error.code).toBe('assistant.speech_unavailable');
    expect(response.request().postDataJSON()).toEqual({ text: words.answer, language, voice: '' });
    await expect.poll(() => spoken(page)).toEqual([expect.objectContaining({ text: words.answer, lang: words.device })]);
    await expect(panel.getByTestId('assistant-listen-failed')).toHaveCount(0);
    await expect(listen).toContainText(words.listen);

    expect(errors).toEqual([]);
    expect(consoleErrors).toEqual([]);
  });
}
