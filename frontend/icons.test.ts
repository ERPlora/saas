// Icon guardrail of the SaaS (PLAN §16.4): an icon that is not registered in @erplora/ui's shell
// paints NOTHING (no network for icons, by CSP), so a page, a component or the server's menu that
// names one must fail a test, not a sign-in. `scanIcons` is the reader @erplora/ui runs on itself;
// here it reads the SaaS's own sources: the entry, the frontend of every app and the panel's menu
// (`base/navigation.py`, round 17), whose `Nav(icon="set:name")` it reads like a template's `icon`.
// It does not read the action icon of `FormModal` (`submit-icon`) and `ConfirmDialog`
// (`confirm-icon`), painted with HubIcon, so this file reads those too. It resolves icons through the
// baked `~icons/*` modules, so it needs the `erploraVite()` plugins of vite.config.ts.
import { globSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { iconReferences, type IconReference, isRegisteredIcon, scanIcons } from '@erplora/ui/testing';
import { describe, expect, it } from 'vitest';

import { FRONTEND_APPS } from '../vite.config';

/** The root of saas-next: the globs below are relative to it. */
const SAAS_DIR = join(dirname(fileURLToPath(import.meta.url)), '..');
/**
 * Where the SaaS's frontend names icons: the shell entry and the frontend of every root app. The apps
 * go in one glob: some have no `frontend/` yet, so only their union must read something.
 */
const FRONTEND_SOURCES = ['frontend/**/*.ts', `{${FRONTEND_APPS.join(',')}}/frontend/**/*.{vue,ts}`];
/** The panel's menu, which `base.session.me` sends to the shell (round 17, PLAN-SAAS §3.6). */
const MENU_SOURCE = 'base/navigation.py';

/**
 * The action icon of FormModal (`submit-icon`) and ConfirmDialog (`confirm-icon`), kebab or camel,
 * static or bound to a literal. HubIcon paints it, so it carries its set. A bound variable is
 * runtime data: not read.
 */
const ACTION_ICONS = [
  /\s(?:submit-icon|submitIcon|confirm-icon|confirmIcon)="([^"]*)"/g,
  /\s:(?:submit-icon|submitIcon|confirm-icon|confirmIcon)="'([^']*)'"/g,
];

function actionIconReferences(source: string): IconReference[] {
  return ACTION_ICONS.flatMap((pattern) =>
    [...source.matchAll(pattern)].map((match) => ({ kind: 'HubIcon' as const, name: match[1] })),
  );
}

/** Tests are not app code: they may name icons that do not exist on purpose (as `scanIcons` skips them). */
const SKIPPED = /\.test\.ts$|(?:^|\/)__tests__\//;

/** Every unregistered action icon in the files the globs read under `root`, as `file: name`. */
function unregisteredActionIcons(root: string, sources: readonly string[]): string[] {
  return sources
    .flatMap((pattern) => globSync(pattern, { cwd: root }))
    .map((file) => file.replaceAll('\\', '/'))
    .filter((file) => !SKIPPED.test(file))
    .sort()
    .flatMap((file) =>
      actionIconReferences(readFileSync(join(root, file), 'utf8'))
        .filter((reference) => !isRegisteredIcon(reference))
        .map(({ name }) => `${file}: ${name}`),
    );
}

describe('guardrail: every icon the SaaS names is registered', () => {
  it('every icon named in the entry and the apps is registered, and every glob reads something', () => {
    expect(scanIcons({ root: SAAS_DIR, sources: FRONTEND_SOURCES })).toEqual({ unregistered: [], emptyGlobs: [] });
  });

  it("every icon of the panel's menu (base/navigation.py) is registered", () => {
    expect(scanIcons({ root: SAAS_DIR, sources: [MENU_SOURCE] })).toEqual({ unregistered: [], emptyGlobs: [] });
  });

  it("reads every icon of the panel's menu: a Nav written another way would slip past the guard", () => {
    const named = iconReferences(readFileSync(join(SAAS_DIR, MENU_SOURCE), 'utf8')).map(({ name }) => name);
    expect(named).toEqual(['lucide:store', 'lucide:shopping-bag', 'lucide:receipt', 'lucide:circle-user']);
  });

  it('every submit-icon and confirm-icon the entry and the apps name is registered', () => {
    expect(unregisteredActionIcons(SAAS_DIR, FRONTEND_SOURCES)).toEqual([]);
  });
});

describe('the action icon reader', () => {
  it('reads submit-icon and confirm-icon, kebab or camel, static or bound to a literal', () => {
    const source = [
      '<FormModal submit-icon="ion:save-outline" />',
      '<FormModal :submit-icon="\'lucide:lock\'" />',
      '<ConfirmDialog confirm-icon="ion:trash-outline" />',
      '<ConfirmDialog :confirmIcon="\'mdi:cart\'" />',
    ].join('\n');
    // Static ones first, then the bound literals.
    expect(actionIconReferences(source)).toEqual([
      { kind: 'HubIcon', name: 'ion:save-outline' },
      { kind: 'HubIcon', name: 'ion:trash-outline' },
      { kind: 'HubIcon', name: 'lucide:lock' },
      { kind: 'HubIcon', name: 'mdi:cart' },
    ]);
  });

  it('leaves a bound variable alone: it is runtime data', () => {
    expect(actionIconReferences('<FormModal :submit-icon="icon" :confirm-icon="row.icon" />')).toEqual([]);
  });
});

describe('the guardrail catches what it should (negatives)', () => {
  /** A throwaway tree with one page that names `body`. */
  function tree(body: string): string {
    const root = mkdtempSync(join(tmpdir(), 'saas-icons-'));
    mkdirSync(join(root, 'hubs', 'frontend', 'pages'), { recursive: true });
    writeFileSync(join(root, 'hubs', 'frontend', 'pages', 'Page.vue'), body);
    return root;
  }

  it('reports an unregistered icon of a page, and a menu that names one', () => {
    const root = tree('<template><HubIcon name="ion:definitely-not-an-icon" /></template>\n');
    mkdirSync(join(root, 'base'));
    writeFileSync(join(root, 'base', 'navigation.py'), 'Nav(id="x", label="X", icon="lucide:no-such-icon", path="/x")\n');
    expect(scanIcons({ root, sources: ['hubs/frontend/**/*.vue', 'base/navigation.py'] }).unregistered).toEqual([
      { file: 'base/navigation.py', name: 'lucide:no-such-icon' },
      { file: 'hubs/frontend/pages/Page.vue', name: 'ion:definitely-not-an-icon' },
    ]);
  });

  it('reports an unregistered action icon, and one without its set (HubIcon needs it)', () => {
    const root = tree('<FormModal submit-icon="ion:no-such-icon" /><ConfirmDialog confirm-icon="trash-outline" />\n');
    expect(unregisteredActionIcons(root, ['hubs/frontend/**/*.vue'])).toEqual([
      'hubs/frontend/pages/Page.vue: ion:no-such-icon',
      'hubs/frontend/pages/Page.vue: trash-outline',
    ]);
  });

  it('passes a registered action icon', () => {
    const root = tree('<ConfirmDialog confirm-icon="ion:trash-outline" />\n');
    expect(unregisteredActionIcons(root, ['hubs/frontend/**/*.vue'])).toEqual([]);
  });
});
