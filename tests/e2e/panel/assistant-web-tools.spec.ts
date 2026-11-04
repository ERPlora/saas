// erplora.com's own tools in the panel's assistant (assistant/WORKBOOK.md, ASSISTANT-F14; saas#202), in a browser against
// the panel's own Django: asked what a currency is worth or about a law, the model asks for `currency_rate` or
// `web_search`, erplora.com runs it, and the answer reaches the bubble with where it comes from under it, although the
// model named no source. In Spanish and in English, at 390, 834 and 1440 (screenshots under `.artifacts/panel/`): the
// long address of a page fits a phone, nothing scrolling sideways.
// assistant-provider.ts plays the model and both providers, a real HTTP server on 127.0.0.1 at `aiProviderPort`, where the
// panel's ASSISTANT_RATES_URL and ASSISTANT_SEARCH_URL point (panel/project.ts): no test reaches a real provider.
// flow: ASSISTANT-F14 — the assistant says a rate and searches the web, with its source in sight.
import { execFileSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import type { Page } from '@playwright/test';

import { LONG_ADDRESS, type Provider, startProvider } from '../assistant-provider';
import { djangoEnv } from '../django-env';
import { STACK } from '../stack';

import { expect, settled, shot, sidewaysScroll, signIn, test, watchPageErrors } from './fixtures';

const SAAS_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const OWNER = { email: 'e2e-assistant-owner@example.com', password: process.env.QA_PANEL_PASSWORD ?? 'e2e-panel' };
const SIZES = [
  { name: 'phone', width: 390, height: 844 },
  { name: 'tablet', width: 834, height: 1112 },
  { name: 'desktop', width: 1440, height: 900 },
] as const;
const RATE_SOURCE = 'https://frankfurter.dev';
const WORDS = {
  es: { rate: '¿A cómo está el dólar?', rateAnswer: 'Hoy, 1 USD son 0.89 EUR.', law: '¿Qué dice la nueva ley?', lawAnswer: 'La ley entra en vigor este mes.' },
  en: { rate: 'What is the dollar worth?', rateAnswer: 'Today, 1 USD is 0.89 EUR.', law: 'What does the new law say?', lawAnswer: 'The law takes effect this month.' },
} as const;

let provider: Provider | undefined;

function seed(action: 'clear' | 'panel', language: 'es' | 'en' = 'es'): void {
  execFileSync('uv', ['run', 'python', 'tests/e2e/panel/assistant_seed.py', action, provider?.url ?? '', language], {
    cwd: SAAS_DIR,
    env: djangoEnv(true),
    stdio: 'pipe',
  });
}

async function ask(page: Page, text: string): Promise<void> {
  await expect(page.getByTestId('assistant-stop')).toHaveCount(0);
  await page.getByTestId('assistant-input').locator('textarea').fill(text);
  await page.getByTestId('assistant-send').click();
}

test.beforeAll(async () => {
  provider = await startProvider(STACK.aiProviderPort);
});

test.afterAll(async () => {
  seed('clear');
  await provider?.close();
});

for (const language of ['es', 'en'] as const) {
  const words = WORDS[language];

  test(`the panel's assistant says a rate and searches the web, its source in sight (${language})`, async ({ page }) => {
    seed('panel', language);
    await signIn(page.request, OWNER);
    const errors = watchPageErrors(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/dashboard/businesses');
    await page.getByTestId('assistant-button').click();
    const panel = page.getByTestId('assistant-panel');
    await expect(panel).toHaveAttribute('data-open', 'true');

    await ask(page, words.rate);
    const rate = panel.getByTestId('assistant-bubble-assistant').last();
    await expect(rate).toContainText(words.rateAnswer);
    await expect(rate).toContainText(RATE_SOURCE);

    await ask(page, words.law);
    const law = panel.getByTestId('assistant-bubble-assistant').last();
    await expect(law).toContainText(words.lawAnswer);
    await expect(law).toContainText(LONG_ADDRESS);

    // The model asked for both; the second answer went back to it with the page and the rate never reached the browser.
    const paths = provider!.seen.map((seen) => seen.path);
    expect(paths).toContain('/v1/latest');
    expect(paths).toContain('/v1/search');

    for (const size of SIZES) {
      await page.setViewportSize({ width: size.width, height: size.height });
      await expect(law).toContainText(LONG_ADDRESS);
      await expect.poll(() => sidewaysScroll(page), `${size.name}: nothing scrolls sideways`).toEqual([]);
      const bubble = await law.boundingBox();
      const pane = await panel.boundingBox();
      expect(bubble!.x + bubble!.width, `${size.name}: the address stays inside the panel`).toBeLessThanOrEqual(pane!.x + pane!.width);
      await settled(page);
      await page.screenshot({ path: shot(`assistant-web-tools-${size.name}-${language}`) });
    }
    expect(errors).toEqual([]);
  });
}
