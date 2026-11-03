// The dictation of the panel's assistant (assistant/WORKBOOK.md, ASSISTANT-F21; saas#175), in a browser against the
// panel's own Django: the composer has its microphone; a tap records (the browser's fake microphone), the next one stops,
// and the words land in the box for the person to read, sent by nobody and spending no message of the account's month.
// In Spanish and in English, at 390, 834 and 1440 (screenshots under `.artifacts/panel/`). What stops a dictation is said
// under the box: a recording the server could not transcribe, and it writes nothing in the box. The microphone the browser
// refuses is assistant-dictation-denied.spec.ts: its fake prompt is a launch option, so a file of its own.
// The provider is assistant-provider.ts, a real HTTP server on 127.0.0.1 set by assistant_seed.py «panel»: the audio
// goes through the panel's Django to it, as it would to the real one.
// flow: ASSISTANT-F21 — dictate to the assistant: the words land in the box, nothing is sent.
import { execFileSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { DICTATION, type Provider, startProvider } from '../assistant-provider';
import { djangoEnv } from '../django-env';
import { expect, settled, shot, sidewaysScroll, signIn, test, watchPageErrors } from './fixtures';

const SAAS_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const OWNER = { email: 'e2e-assistant-owner@example.com', password: process.env.QA_PANEL_PASSWORD ?? 'e2e-panel' };
const SIZES = [
  { name: '1440', width: 1440, height: 900 },
  { name: '834', width: 834, height: 1112 },
  { name: '390', width: 390, height: 844 },
] as const;

/** What the person sees, in each language (the package's words, `assistant.voice.*`). */
const WORDS = {
  es: { dictate: 'Dictar por voz', stop: 'Detener la grabación', failed: 'No se ha podido transcribir el audio. Inténtalo de nuevo.' },
  en: { dictate: 'Dictate by voice', stop: 'Stop recording', failed: 'The audio could not be transcribed. Try again.' },
} as const;

let provider: Provider | undefined;

function seed(action: 'clear' | 'panel', language: 'es' | 'en' = 'es'): void {
  execFileSync('uv', ['run', 'python', 'tests/e2e/panel/assistant_seed.py', action, provider?.url ?? '', language], {
    cwd: SAAS_DIR,
    env: djangoEnv(true),
    stdio: 'pipe',
  });
}

// The browser's fake microphone: a worker-wide launch option, so for the whole file.
test.use({
  launchOptions: { args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'] },
  permissions: ['microphone'],
});

test.beforeAll(async () => {
  provider = await startProvider(0);
});

test.afterAll(async () => {
  seed('clear');
  await provider?.close();
});

for (const language of ['es', 'en'] as const) {
  const words = WORDS[language];

  test(`the account dictates to the panel's assistant: the words land in the box, nothing is sent (${language})`, async ({
    page,
  }) => {
    seed('panel', language);
    await signIn(page.request, OWNER);
    const errors = watchPageErrors(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/dashboard/businesses');
    await page.getByTestId('assistant-button').click();
    const panel = page.getByTestId('assistant-panel');
    await expect(panel).toHaveAttribute('data-open', 'true');

    const mic = panel.getByTestId('assistant-mic');
    await expect(mic).toBeVisible();
    await expect(mic).toHaveAttribute('aria-label', words.dictate);

    await mic.click();
    await expect(mic).toHaveAttribute('aria-pressed', 'true');
    await expect(mic).toHaveAttribute('aria-label', words.stop);
    // A second and a bit of the fake microphone's tone.
    await page.waitForTimeout(1200);
    const before = provider!.seen.length;
    await mic.click();

    const box = panel.getByTestId('assistant-input').locator('textarea');
    await expect(box).toHaveValue(DICTATION);
    await expect(mic).toHaveAttribute('aria-pressed', 'false');
    expect(provider!.seen.slice(before).map((seen) => seen.path)).toEqual(['/v1/audio/transcriptions']);

    // Nothing is sent by itself: no question in the conversation, none to the model, no message of the month.
    await expect(panel.getByTestId('assistant-empty')).toBeVisible();
    const usage = await page.request.get('/api/assistant/usage');
    expect((await usage.json()).used).toBe(0);

    for (const size of SIZES) {
      await page.setViewportSize({ width: size.width, height: size.height });
      await expect(box).toHaveValue(DICTATION);
      await expect(mic).toBeVisible();
      expect(await sidewaysScroll(page), `${size.name}: nothing scrolls sideways`).toEqual([]);
      await settled(page);
      await page.screenshot({ path: shot(`assistant-dictation-${size.name}-${language}`) });
    }
    expect(errors).toEqual([]);
  });

  test(`a dictation the server could not transcribe is said under the box, which stays as it was (${language})`, async ({
    page,
  }) => {
    seed('panel', language);
    await signIn(page.request, OWNER);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.route('**/api/assistant/transcribe', (route) =>
      route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ error: { code: 'base.assistant_transcribe_failed', message: 'Failed' } }),
      }),
    );
    await page.goto('/dashboard/businesses');
    await page.getByTestId('assistant-button').click();
    const panel = page.getByTestId('assistant-panel');
    const mic = panel.getByTestId('assistant-mic');

    await mic.click();
    await expect(mic).toHaveAttribute('aria-pressed', 'true');
    await page.waitForTimeout(1200);
    await mic.click();

    await expect(panel.getByTestId('assistant-composer-problem')).toHaveText(words.failed);
    await expect(panel.getByTestId('assistant-input').locator('textarea')).toHaveValue('');
    await settled(page);
    await page.screenshot({ path: shot(`assistant-dictation-failed-${language}`) });
  });
}
