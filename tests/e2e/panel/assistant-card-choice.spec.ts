// The card of the panel's assistant for the one preference asked (assistant/WORKBOOK.md, ASSISTANT-F25 step 5): a value
// of a closed list says which datum it is, also when it goes first. Asked only for the language, the line used to read
// «Cambiar las preferencias en Cuenta: English». In Spanish and in English, at 1440, 834 and 390 (screenshots under
// `.artifacts/panel/`); «Cancel» changes nothing. The model is assistant-provider.ts, set by assistant_seed.py «panel».
// flow: ASSISTANT-F25 — the card of a write names a value of a closed list by its datum.
import { ask, DESKTOP_FIRST, localAssistant, openPanel } from './assistant-chat';
import { expect, test } from './fixtures';
import { watchPageErrors } from './page-events';
import { expectNoSidewaysScroll, settled, shot } from './screen';

const WORDS = {
  es: { ask: 'Ponme el panel en inglés', line: 'Cambiar las preferencias en Cuenta: Idioma: English', language: 'es' },
  en: { ask: 'Switch the panel to Spanish', line: 'Change preferences in Account: Language: Español', language: 'en' },
} as const;

const { seed } = localAssistant();

for (const language of ['es', 'en'] as const) {
  const words = WORDS[language];

  test(`the card of the one preference asked says which one it is (${language})`, async ({ page }) => {
    await seed('panel', language);
    const errors = watchPageErrors(page);
    await openPanel(page);

    await ask(page, words.ask);
    const card = page.getByTestId('assistant-confirm');
    await expect(card).toBeVisible();
    for (const size of DESKTOP_FIRST) {
      await page.setViewportSize({ width: size.width, height: size.height });
      await expect(card.getByText(words.line, { exact: true })).toBeVisible();
      await expectNoSidewaysScroll(page, `${size.width}: nothing scrolls sideways`);
      await settled(page);
      await page.screenshot({ path: shot(`assistant-card-choice-${size.width}-${language}`) });
    }

    await page.getByTestId('assistant-confirm-cancel').click();
    await expect(card).toBeHidden();
    const preferences = (await (await page.request.get('/api/accounts/preferences')).json()) as { language: string };
    expect(preferences.language).toBe(words.language);
    expect(errors).toEqual([]);
  });
}
