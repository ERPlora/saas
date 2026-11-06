// erplora.com's own tools in the panel's assistant (assistant/WORKBOOK.md, ASSISTANT-F14; saas#202), in a browser against
// the panel's own Django: asked what a currency is worth or about a law, the model asks for `currency_rate` or
// `web_search`, erplora.com runs it, and the answer reaches the bubble with where it comes from under it, although the
// model named no source. In Spanish and in English, at 390, 834 and 1440 (screenshots under `.artifacts/panel/`): the
// long address of a page fits a phone, nothing scrolling sideways.
// assistant-provider.ts plays the model and both providers, a real HTTP server on 127.0.0.1 at `aiProviderPort`, where the
// panel's ASSISTANT_RATES_URL and ASSISTANT_SEARCH_URL point (panel/project.ts): no test reaches a real provider.
// flow: ASSISTANT-F14 — the assistant says a rate and searches the web, with its source in sight.
import { LONG_ADDRESS } from '../assistant-provider';
import { STACK } from '../stack';

import { ask, DESKTOP_FIRST, localAssistant, openPanel } from './assistant-chat';
import { expect, expectNoSidewaysScroll, settled, shot, test, watchPageErrors } from './fixtures';

const RATE_SOURCE = 'https://frankfurter.dev';
const WORDS = {
  es: { rate: '¿A cómo está el dólar?', rateAnswer: 'Hoy, 1 USD son 0.89 EUR.', law: '¿Qué dice la nueva ley?', lawAnswer: 'La ley entra en vigor este mes.' },
  en: { rate: 'What is the dollar worth?', rateAnswer: 'Today, 1 USD is 0.89 EUR.', law: 'What does the new law say?', lawAnswer: 'The law takes effect this month.' },
} as const;

const { provider, seed } = localAssistant(STACK.aiProviderPort);

for (const language of ['es', 'en'] as const) {
  const words = WORDS[language];

  test(`the panel's assistant says a rate and searches the web, its source in sight (${language})`, async ({ page }) => {
    seed('panel', language);
    const errors = watchPageErrors(page);
    const panel = await openPanel(page);

    await ask(page, words.rate);
    const rate = panel.getByTestId('assistant-bubble-assistant').last();
    await expect(rate).toContainText(words.rateAnswer);
    await expect(rate).toContainText(RATE_SOURCE);

    await ask(page, words.law);
    const law = panel.getByTestId('assistant-bubble-assistant').last();
    await expect(law).toContainText(words.lawAnswer);
    await expect(law).toContainText(LONG_ADDRESS);

    // The model asked for both; the second answer went back to it with the page and the rate never reached the browser.
    const paths = provider().seen.map((seen) => seen.path);
    expect(paths).toContain('/v1/latest');
    // The provider stays up between the two languages: this language's search is the last.
    const search = provider().seen.filter((seen) => seen.path === '/res/v1/web/search').at(-1);
    expect(new URLSearchParams(search?.query).get('search_lang')).toBe(language);
    expect(new URLSearchParams(search?.query).get('country')).toBe(language === 'es' ? 'ES' : 'ALL');

    for (const size of DESKTOP_FIRST) {
      await page.setViewportSize({ width: size.width, height: size.height });
      await expect(law).toContainText(LONG_ADDRESS);
      await expectNoSidewaysScroll(page, `${size.width}: nothing scrolls sideways`);
      const bubble = await law.boundingBox();
      const pane = await panel.boundingBox();
      expect(bubble!.x + bubble!.width, `${size.width}: the address stays inside the panel`).toBeLessThanOrEqual(pane!.x + pane!.width);
      await settled(page);
      await page.screenshot({ path: shot(`assistant-web-tools-${size.width}-${language}`) });
    }
    expect(errors).toEqual([]);
  });
}
