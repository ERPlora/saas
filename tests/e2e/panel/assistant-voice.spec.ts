// «Read aloud» of the panel's assistant in a server voice (assistant/WORKBOOK.md, ASSISTANT-F22; PLAN-SAAS round
// 2026-11-03m), in a browser against the panel's own Django: the chat's head offers the language's two voices of Azure AI
// Speech and the device's (`@erplora/ui` `voices.ts`, the ids of `assistant.media.VOICES`), and an answer offers «Read
// aloud». This stack has no provider of the voice (no Azure key in the e2e's database), so `base.assistant.speak` answers
// 503 `assistant.speech_unavailable` and the chat reads the answer in the device's voice instead, with no error on the
// page. In Spanish and in English, at 1440, 834 and 390 (screenshots under `.artifacts/panel/`).
// The device's voice is the browser's `speechSynthesis`, which a headless Chrome cannot sound: the page's `speak` is
// replaced by a recorder that ends each utterance at once, as the fake microphone stands in for the dictation's.
// The model is assistant-provider.ts, a real HTTP server on 127.0.0.1 set by assistant_seed.py «panel».
// flow: ASSISTANT-F22 — read an answer aloud: the server's voice, else the device's.
import { execFileSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

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
    voices: ['Ximena', 'Tristan', 'Voz del dispositivo'],
    listen: 'Leer en voz alta',
    device: 'es-ES',
  },
  en: {
    question: 'Hello',
    answer: 'Hello, I am the test assistant.',
    voices: ['Ava', 'Andrew', 'Device voice'],
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

for (const language of ['es', 'en'] as const) {
  const words = WORDS[language];

  test(`the chat offers the voices of its language and, without the server's, reads in the device's (${language})`, async ({
    page,
  }) => {
    seed('panel', language);
    await signIn(page.request, OWNER);
    const errors = watchPageErrors(page);
    const consoleErrors: string[] = [];
    page.on('console', (message) => {
      // The browser's own line for an answer that is not 2xx (the 503 below) is the network's, not the page's.
      if (message.type() === 'error' && !message.text().startsWith('Failed to load resource')) consoleErrors.push(message.text());
    });
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/dashboard/businesses');
    await page.getByTestId('assistant-button').click();
    const panel = page.getByTestId('assistant-panel');
    await expect(panel).toHaveAttribute('data-open', 'true');

    // The head's choice of voice: the language's two server voices, the device's last, the first by default.
    const voice = panel.getByTestId('assistant-voice');
    await expect(voice).toBeVisible();
    await expect(voice).toHaveJSProperty('value', language === 'es' ? 'es-ES-Ximena:DragonHDLatestNeural' : 'en-US-Ava:DragonHDLatestNeural');
    for (const size of SIZES) {
      await page.setViewportSize({ width: size.width, height: size.height });
      await voice.click();
      // The select's own popover (`select-popover`): the side menu keeps an inline one of its own.
      const options = page.locator('ion-popover.select-popover ion-radio');
      await expect(options).toHaveText([...words.voices]);
      // Its enter is no animation `settled()` sees (Ionic's own): shot once it is fully drawn, not half-faded.
      await expect
        .poll(() =>
          page
            .locator('ion-popover.select-popover')
            .evaluate((popover) => getComputedStyle(popover.shadowRoot!.querySelector('.popover-wrapper')!).opacity),
        )
        .toBe('1');
      await settled(page);
      await page.screenshot({ path: shot(`assistant-voice-choice-${size.name}-${language}`) });
      // Closed by choosing the voice already chosen: Escape would close the whole chat (its own key).
      await options.first().click();
      await expect(page.locator('ion-popover.select-popover')).toHaveCount(0);
      await expect(panel).toHaveAttribute('data-open', 'true');
    }

    // An answer, and its «Read aloud».
    await page.setViewportSize({ width: 1440, height: 900 });
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
      await page.screenshot({ path: shot(`assistant-voice-answer-${size.name}-${language}`) });
    }

    // No provider of the voice here: the server says so, and the device reads the answer, in the chat's language.
    await page.setViewportSize({ width: 1440, height: 900 });
    const refused = page.waitForResponse((response) => response.url().endsWith('/api/assistant/speak'));
    await listen.click();
    const speech = await refused;
    expect(speech.status()).toBe(503);
    expect((await speech.json()).error.code).toBe('assistant.speech_unavailable');
    await expect
      .poll(() => page.evaluate(() => (window as unknown as { __spoken: Array<{ text: string; lang: string }> }).__spoken))
      .toEqual([expect.objectContaining({ text: words.answer, lang: words.device })]);
    await expect(panel.getByTestId('assistant-listen-failed')).toHaveCount(0);
    await expect(listen).toContainText(words.listen);
    await settled(page);
    await page.screenshot({ path: shot(`assistant-voice-device-fallback-${language}`) });

    expect(errors).toEqual([]);
    expect(consoleErrors).toEqual([]);
  });
}
