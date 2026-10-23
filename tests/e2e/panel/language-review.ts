// The review of a screen in the language the person reads (the migration's review of the `hecho` flows of
// accounts/WORKBOOK.md, APP-ACCOUNTS-6 and APP-ACCOUNTS-7): at the three sizes of the migration (390×844, 834×1112,
// 1440×900), the page says its language (`<html lang>`), no whole text of the other language is left on screen (every
// catalogue of the panel, `accounts`, `hubs`, the shell and @erplora/ui), nothing scrolls sideways, and a capture
// `<task>-<flow>-<size>-<lang>` stays for the eye.
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { type Page } from '@playwright/test';

import { expect, settled, shot, sidewaysScroll } from './fixtures';

export const SIZES = [
  { name: '390', width: 390, height: 844 },
  { name: '834', width: 834, height: 1112 },
  { name: '1440', width: 1440, height: 900 },
] as const;
export const LANGUAGES = [
  { lang: 'en', locale: 'en-US' },
  { lang: 'es', locale: 'es-ES' },
] as const;
export type Lang = (typeof LANGUAGES)[number]['lang'];

// ── The catalogues of the panel, both languages ───────────────────────────────────────────────

const SAAS_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const COMPONENTS = join(SAAS_DIR, 'packages/ui/src/components');
const CATALOGUE_DIRS = [
  'accounts/frontend/locale',
  'hubs/frontend/locale',
  'frontend/locale',
  'packages/ui/src/shell/locales',
  'packages/ui/src/sdk/locales',
  ...readdirSync(COMPONENTS).map((name) => `packages/ui/src/components/${name}/locales`),
].filter((dir) => existsSync(join(SAAS_DIR, dir, 'en.json')));

function flatten(tree: Record<string, unknown>, prefix = '', into = new Map<string, string>()): Map<string, string> {
  for (const [key, value] of Object.entries(tree)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === 'string') into.set(path, value);
    else if (value && typeof value === 'object') flatten(value as Record<string, unknown>, path, into);
  }
  return into;
}

function catalogue(lang: Lang): Map<string, string> {
  const all = new Map<string, string>();
  for (const dir of CATALOGUE_DIRS) flatten(JSON.parse(readFileSync(join(SAAS_DIR, dir, `${lang}.json`), 'utf8')), '', all);
  return all;
}

const CATALOGUES: Record<Lang, Map<string, string>> = { en: catalogue('en'), es: catalogue('es') };

/** The text of `key` in `lang`, as the panel shows it. */
export function t(lang: Lang, key: string): string {
  const text = CATALOGUES[lang].get(key);
  if (text === undefined) throw new Error(`no ${lang} text for ${key}`);
  return text;
}

/**
 * The whole texts of the other language that a page in `lang` must not show: every message translated differently,
 * without placeholders, that is no text of `lang` itself (a word both languages share, «Email», is no clue).
 */
function foreignTexts(lang: Lang): string[] {
  const other: Lang = lang === 'en' ? 'es' : 'en';
  const own = new Set(CATALOGUES[lang].values());
  const found = new Set<string>();
  for (const [key, text] of CATALOGUES[other]) {
    const mine = CATALOGUES[lang].get(key);
    if (mine === undefined || mine === text || own.has(text) || text.length < 4 || /[{|]/.test(text)) continue;
    found.add(text);
  }
  return [...found];
}

const FOREIGN: Record<Lang, string[]> = { en: foreignTexts('en'), es: foreignTexts('es') };

/**
 * Every visible text node of the page (through open shadow roots) that is a whole text of the other language. A text
 * the page says is in another language (inside an element with its own `lang`, as the API's reference) is no slip.
 */
export async function textsOfTheOtherLanguage(page: Page, lang: Lang): Promise<string[]> {
  return page.evaluate(
    ([foreign, own]) => {
      const texts = new Set(foreign);
      const found = new Set<string>();
      const visit = (root: Node) => {
        const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
        for (let node: Node | null = walker.currentNode; node; node = walker.nextNode()) {
          if (node.nodeType === Node.TEXT_NODE) {
            const text = node.textContent?.trim() ?? '';
            const parent = node.parentElement;
            const marked = parent?.closest('[lang]')?.getAttribute('lang') ?? own;
            if (!marked.startsWith(own)) continue;
            if (texts.has(text) && parent?.checkVisibility({ opacityProperty: true, visibilityProperty: true })) found.add(text);
          } else if ((node as Element).shadowRoot) {
            visit((node as Element).shadowRoot as ShadowRoot);
          }
        }
      };
      visit(document.body);
      return [...found];
    },
    [FOREIGN[lang], lang] as const,
  );
}

// ── The review of one screen ──────────────────────────────────────────────────────────────────

/**
 * The review of a task (`APP-ACCOUNTS-6`…): `ready` at each size, then the checks of every screen (the page says
 * `lang`, no text of the other language, no sideways scroll) and the capture `<task>-<flow>-<size>-<lang>`; back at
 * 1440 after. `fullPage: false` for a page as long as the API's reference, whose full shot is thousands of pixels tall.
 */
export function reviewOf(task: string) {
  return async function review(
    page: Page,
    lang: Lang,
    flow: string,
    ready: () => Promise<void>,
    { fullPage = true }: { fullPage?: boolean } = {},
  ): Promise<void> {
    for (const size of SIZES) {
      await page.setViewportSize({ width: size.width, height: size.height });
      await ready();
      await settled(page);
      await expect(page.locator('html'), `${flow} says its language`).toHaveAttribute('lang', new RegExp(`^${lang}\\b`));
      expect(await textsOfTheOtherLanguage(page, lang), `${flow} at ${size.name} in ${lang}: text of the other language`).toEqual([]);
      expect(await sidewaysScroll(page), `${flow} scrolls sideways at ${size.name} in ${lang}`).toEqual([]);
      await page.screenshot({ path: shot(`${task}-${flow}-${size.name}-${lang}`), fullPage });
    }
    await page.setViewportSize({ width: 1440, height: 900 });
  };
}

/** The user menu (`UserMenuPopover`): in the side menu, a drawer behind the topbar's menu button below `lg`. */
export async function openUserMenu(page: Page): Promise<void> {
  const trigger = page.getByTestId('user-menu-trigger');
  await expect(trigger).toBeAttached();
  await settled(page);
  if (!(await trigger.isVisible())) {
    await page.locator('ion-router-outlet > .ion-page:not(.ion-page-hidden) ion-menu-button').last().click();
    await expect(trigger).toBeVisible();
  }
  const presented = page.evaluate(
    () => new Promise<void>((resolve) => document.addEventListener('ionPopoverDidPresent', () => resolve(), { once: true })),
  );
  await trigger.click();
  await presented;
  await expect(page.getByTestId('user-menu-logout')).toBeVisible();
}

/** Closes whatever overlay is open (the user menu, a modal) and the side menu, so the next size starts clean. */
export async function closeOverlays(page: Page): Promise<void> {
  await page.evaluate(async () => {
    for (const overlay of document.querySelectorAll<HTMLElement & { dismiss: () => Promise<boolean> }>('ion-popover, ion-modal')) {
      await overlay.dismiss();
    }
    const menu = document.querySelector<HTMLElement & { close: () => Promise<boolean> }>('ion-menu');
    await menu?.close();
  });
}
