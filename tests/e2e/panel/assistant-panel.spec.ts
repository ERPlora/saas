// The panel's assistant (MIGRATION-TASK T4 of plan 2026-10-30-asistente-saas; assistant/WORKBOOK.md, ASSISTANT-F25
// and F26), in a browser against the panel's own Django: the sparkles «Assistant» at the end of the topbar opens the
// shared chat's panel, docked beside the screen from 768 px (pushing it) and over a veil on a phone; its empty
// conversation says the panel's sentence with three shortcuts; a read the model asks for runs alone and the answer
// names the account's business; a write stops at its card, which asks to type the word, and a «Cancel» changes
// nothing; the account's month (2 messages in this run, panel/project.ts) ends with the allowance spent and no
// «Upgrade plan». In Spanish and in English, at 390, 834 and 1440 (screenshots under `.artifacts/panel/`). Signed out,
// the panel sends to the sign-in and nobody sees the assistant.
// The model is assistant-provider.ts, a real HTTP server on 127.0.0.1 that speaks OpenAI's API, set to answer by
// assistant_seed.py «panel» (with `e2e-assistant-owner`, an account like any other with one business): no test reaches
// a real provider and no real key is ever typed.
// flow: ASSISTANT-F25 — the account asks the panel's assistant: reads alone, writes after the card.
// flow: ASSISTANT-F26 — the account's messages of the month, spent without a plan to upgrade.
import { execFileSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import type { Page } from '@playwright/test';

import { NEW_BUSINESS, type Provider, startProvider } from '../assistant-provider';
import { djangoEnv } from '../django-env';
import { expect, settled, shot, sidewaysScroll, signIn, test, watchPageErrors } from './fixtures';

const SAAS_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const PASSWORD = process.env.QA_PANEL_PASSWORD ?? 'e2e-panel';
const OWNER = { email: 'e2e-assistant-owner@example.com', password: PASSWORD };
const BUSINESS = 'E2E Asistente Panel';
const SIZES = [
  { name: '1440', width: 1440, height: 900 },
  { name: '834', width: 834, height: 1112 },
  { name: '390', width: 390, height: 844 },
] as const;

/** What the person sees, in each language (the package's words and the panel's, frontend/locale). */
const WORDS = {
  es: {
    empty: 'Pregúntame por tus negocios, tus facturas o tu cuenta.',
    shortcuts: ['¿Qué negocios tengo?', '¿Cuánto pago al mes?', '¿Cómo creo un negocio?'],
    answer: `Tienes 1 negocio: ${BUSINESS}.`,
    goTo: 'Ir a Negocios',
    create: `Crea un negocio llamado ${NEW_BUSINESS}`,
    word: 'CONFIRMAR',
    card: 'Crear negocio en Negocios. Revisa cada dato antes de seguir.',
    notCreated: 'No he creado el negocio: no ha cambiado nada.',
    receipt: 'No se hizo, cancelado: Crear negocio en Negocios',
    footerSpent: /^Has usado los 2 mensajes de este mes\. Se renuevan el 1 de \p{L}+\.$/u,
    third: '¿Cuánto pago al mes?',
    spent: 'Has usado todos los mensajes del asistente de este mes (2 de 2).',
    elsewhere: 'Cada negocio tiene su propio asistente, con sus propios mensajes: abre el negocio para seguir preguntando allí.',
    upgrade: /mejorar|plan/i,
  },
  en: {
    empty: 'Ask me about your businesses, your invoices or your account.',
    shortcuts: ['Which businesses do I have?', 'How much do I pay a month?', 'How do I create a business?'],
    answer: `You have 1 business: ${BUSINESS}.`,
    goTo: 'Go to Businesses',
    create: `Create a business called ${NEW_BUSINESS}`,
    word: 'CONFIRM',
    card: 'Create business in Businesses. Check each datum before going on.',
    notCreated: 'I did not create the business: nothing changed.',
    receipt: 'Not done, cancelled: Create business in Businesses',
    footerSpent: /^You have used all 2 messages of this month\. They renew on \p{L}+ 1\.$/u,
    third: 'How much do I pay a month?',
    spent: "You have used all the assistant's messages of this month (2 of 2).",
    elsewhere: 'Each business has its own assistant, with its own messages: open the business to keep asking there.',
    upgrade: /upgrade|plan/i,
  },
} as const;

let provider: Provider | undefined;

/** `assistant_seed.py <action> <provider address> <language>`: always from scratch. */
function seed(action: 'clear' | 'panel', language: 'es' | 'en' = 'es'): void {
  execFileSync('uv', ['run', 'python', 'tests/e2e/panel/assistant_seed.py', action, provider?.url ?? '', language], {
    cwd: SAAS_DIR,
    env: djangoEnv(true),
    stdio: ['ignore', 'pipe', 'pipe'],
  });
}

/** Writes `text` in the composer and sends it, once the turn before is over. */
async function ask(page: Page, text: string): Promise<void> {
  await expect(page.getByTestId('assistant-stop')).toHaveCount(0);
  await page.getByTestId('assistant-input').locator('textarea').fill(text);
  await page.getByTestId('assistant-send').click();
}

/** The panel's width and how far the pane is pushed from the right (0 when it is not). */
async function docking(page: Page): Promise<{ panel: number; pushed: number }> {
  return {
    panel: await page.getByTestId('assistant-panel').evaluate((element) => element.getBoundingClientRect().width),
    pushed: await page.locator('ion-app > ion-split-pane').evaluate((element) => parseFloat(getComputedStyle(element).right) || 0),
  };
}

test.beforeAll(async () => {
  provider = await startProvider(0);
});

test.afterAll(async () => {
  seed('clear');
  await provider?.close();
});

for (const language of ['es', 'en'] as const) {
  const words = WORDS[language];

  test(`the account asks the panel's assistant, a write waits for its card, and the month ends spent (${language})`, async ({
    page,
  }) => {
    seed('panel', language);
    await signIn(page.request, OWNER);
    const errors = watchPageErrors(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/dashboard/businesses');
    await expect(page.getByText(BUSINESS).first()).toBeVisible();

    // The sparkles at the end of the topbar open the panel, docked: the screen beside it is pushed, not covered.
    const button = page.getByTestId('assistant-button');
    await expect(button).toBeVisible();
    await button.click();
    const panel = page.getByTestId('assistant-panel');
    await expect(panel).toHaveAttribute('data-open', 'true');
    await expect(page.locator('html')).toHaveClass(/assistant-docked/);
    await expect(page.getByTestId('assistant-veil')).toHaveCount(0);
    const docked = await docking(page);
    expect(docked.pushed).toBeGreaterThan(300);
    expect(docked.pushed).toBeCloseTo(docked.panel, 0);

    // The empty conversation: the panel's sentence and its three shortcuts.
    await expect(page.getByTestId('assistant-empty')).toContainText(words.empty);
    await expect(page.getByTestId('assistant-shortcut')).toHaveText([...words.shortcuts]);
    await settled(page);
    await page.screenshot({ path: shot(`assistant-panel-empty-1440-${language}`) });

    // A read runs alone: «writing» until the first words, then the account's business, and «Go to Businesses».
    await page.getByTestId('assistant-shortcut').first().click();
    await expect(page.getByTestId('assistant-bubble-user')).toHaveText(words.shortcuts[0]);
    await expect(page.getByTestId('assistant-writing')).toBeVisible();
    const answer = page.getByTestId('assistant-bubble-assistant').last();
    await expect(answer).toContainText(words.answer);
    await expect(page.getByTestId('assistant-go')).toContainText(words.goTo);

    // A write stops at its card: creating a business asks to type the word; «Cancel» changes nothing.
    await ask(page, words.create);
    const card = page.getByTestId('assistant-confirm');
    await expect(card).toBeVisible();
    await expect(card).toContainText(words.card);
    await expect(card.getByText(words.word, { exact: true })).toBeVisible();
    // `ion-button` is no native button: Ionic says it is off on its host.
    await expect(page.getByTestId('assistant-confirm-submit')).toHaveAttribute('aria-disabled', 'true');
    await expect(page.getByTestId('assistant-confirm-input')).toBeVisible();
    await settled(page);
    await page.screenshot({ path: shot(`assistant-panel-card-1440-${language}`) });
    await page.getByTestId('assistant-confirm-cancel').click();
    await expect(card).toBeHidden();
    await expect(page.getByTestId('assistant-bubble-assistant').last()).toContainText(words.notCreated);
    await expect(page.getByTestId('assistant-receipt').last()).toHaveText(words.receipt);
    const listed = (await (await page.request.get('/api/hubs/businesses')).json()) as { rows: { name: string }[] };
    expect(listed.rows.map((row) => row.name)).toEqual([BUSINESS]);

    // Two questions were the month's two messages (the card's answer cost none): the foot says it, and a third one is
    // refused with when they come back and where to keep asking, never «Upgrade plan».
    await expect(page.getByTestId('assistant-stop')).toHaveCount(0);
    await expect(page.getByTestId('assistant-usage')).toHaveText(words.footerSpent);
    await ask(page, words.third);
    const failure = page.getByTestId('assistant-failure').last();
    await expect(failure).toContainText(words.spent);
    await expect(failure).toContainText(words.elsewhere);
    await expect(failure).not.toContainText(words.upgrade);
    await expect(page.getByTestId('assistant-upgrade')).toHaveCount(0);

    // The same conversation at the three sizes: docked from 768 px, over a veil on a phone.
    for (const size of SIZES) {
      await page.setViewportSize({ width: size.width, height: size.height });
      if (size.width >= 768) {
        await expect(page.locator('html')).toHaveClass(/assistant-docked/);
        await expect(page.getByTestId('assistant-veil')).toHaveCount(0);
        const pushed = await docking(page);
        expect(pushed.pushed).toBeCloseTo(pushed.panel, 0);
      } else {
        await expect(page.getByTestId('assistant-veil')).toBeVisible();
        await expect(page.locator('html')).not.toHaveClass(/assistant-docked/);
        await expect(panel).toHaveAttribute('aria-modal', 'true');
        expect((await docking(page)).panel).toBe(size.width);
      }
      await expect(failure).toBeVisible();
      expect(await sidewaysScroll(page), `${size.name}: nothing scrolls sideways`).toEqual([]);
      await settled(page);
      await page.screenshot({ path: shot(`assistant-panel-spent-${size.name}-${language}`) });
    }

    // × closes it: the screen takes the whole width back.
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.getByTestId('assistant-close').click();
    await expect(panel).toHaveAttribute('data-open', 'false');
    await expect(page.locator('html')).not.toHaveClass(/assistant-docked/);
    expect(errors).toEqual([]);
  });
}

test('signed out, the panel sends to the sign-in and nobody sees the assistant', async ({ page }) => {
  await page.goto('/dashboard/businesses');
  await expect(page).toHaveURL(/\/launch(\?|$)/);
  await expect(page.getByTestId('login-form')).toBeVisible();
  await expect(page.getByTestId('assistant-button')).toHaveCount(0);
  await expect(page.getByTestId('assistant-panel')).toHaveCount(0);
});
