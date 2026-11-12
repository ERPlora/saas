// @vitest-environment node
// Lint of the SaaS: the SPA reaches the server only through the SDK (`@erplora/ui/sdk`), so the
// shell entry and every app frontend are linted for raw network globals. Linted for real here.
import { existsSync, readdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { ESLint } from 'eslint';
import { beforeAll, describe, expect, it } from 'vitest';

const SAAS_DIR = dirname(fileURLToPath(import.meta.url));
const eslint = new ESLint({ cwd: SAAS_DIR });
/** Node's module cache: ESLint, typescript-eslint, TypeScript and eslint-plugin-vue are CommonJS. */
const loadedModules = createRequire(import.meta.url).cache;

/** The apps with a frontend: root directories next to `base/` holding a `frontend/` (there is no `apps/` folder). */
function rootAppsWithFrontend(): string[] {
  return readdirSync(SAAS_DIR, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && entry.name !== 'node_modules' && !entry.name.startsWith('.'))
    .filter((entry) => existsSync(join(SAAS_DIR, entry.name, 'frontend')))
    .map((entry) => entry.name);
}

async function restricted(code: string, filePath: string): Promise<string[]> {
  const [result] = await eslint.lintText(code, { filePath });
  return result.messages.filter((m) => m.ruleId === 'no-restricted-globals').map((m) => m.message);
}

/** What the lint says of the imports of `code` it forbids. */
async function forbiddenImports(code: string, filePath: string): Promise<string[]> {
  const [result] = await eslint.lintText(code, { filePath });
  return result.messages.filter((m) => m.ruleId === 'no-restricted-imports').map((m) => m.message);
}

/** The elements whose `slot="…"` attribute the lint reports as Vue 2 syntax. */
async function deprecatedSlots(code: string, filePath: string): Promise<string[]> {
  const [result] = await eslint.lintText(code, { filePath });
  return result.messages
    .filter((m) => m.ruleId === 'vue/no-deprecated-slot-attribute')
    .map((m) => code.split('\n')[m.line - 1].trim().split(/[\s>]/)[0]);
}

describe('eslint config', () => {
  // The first lint loads the config and, through it, typescript-eslint, TypeScript, eslint-plugin-vue and its
  // parser: about a thousand modules, once per run (the config is evaluated once; every later lint takes
  // milliseconds). That fixed cost depends on the machine: 0.5 s at rest, up to 3 s beside another `pnpm test`, and
  // past Vitest's 5 s on a heavily loaded machine. It is paid here, once, with the limit of the guardrails that read
  // the whole tree (60 s, vite.config.test.ts); each test keeps Vitest's 5 s for its own lints.
  beforeAll(async () => {
    await restricted('export {};\n', 'frontend/main.ts');
  }, 60_000);

  it('lints a page without loading a module: ESLint, its parsers and plugins are loaded before the tests', async () => {
    const before = new Set(Object.keys(loadedModules));
    await restricted('export const x = fetch;\n', 'frontend/main.ts');
    await restricted(
      '<script setup lang="ts">\nconst x = fetch;\n</script>\n<template><div>{{ x }}</div></template>\n',
      'accounts/frontend/pages/Page.vue',
    );
    expect(Object.keys(loadedModules).filter((path) => !before.has(path)).length).toBe(0);
  });

  it.each(['fetch', 'EventSource', 'WebSocket', 'XMLHttpRequest'])('forbids %s in an app page and in the entry', async (name) => {
    const code = `export const x = ${name};\n`;
    expect(await restricted(code, 'accounts/frontend/components/SignInForm.ts')).toHaveLength(1);
    expect(await restricted(code, 'frontend/main.ts')).toHaveLength(1);
  });

  it('forbids it in the <script setup> of a .vue page too', async () => {
    const code = `<script setup lang="ts">\nconst session = fetch('/_allauth/browser/v1/auth/session');\n</script>\n<template><div>{{ session }}</div></template>\n`;
    expect(await restricted(code, 'accounts/frontend/components/SignInForm.vue')).toEqual([
      "Unexpected use of 'fetch'. Network access goes through the SDK (@erplora/ui/sdk).",
    ]);
  });

  it('forbids it in the frontend of every root app (the SaaS has no apps/ folder)', async () => {
    const apps = [...new Set([...rootAppsWithFrontend(), 'accounts', 'hubs', 'billing'])];
    for (const app of apps) {
      expect(await restricted('export const x = fetch;\n', `${app}/frontend/pages/Page.ts`), app).toHaveLength(1);
    }
  });

  it('ignores the build and collectstatic output', async () => {
    expect(await eslint.isPathIgnored('frontend/dist/assets/main-abc.js')).toBe(true);
    expect(await eslint.isPathIgnored('staticfiles/admin/js/core.js')).toBe(true);
  });

  it('leaves the live and ui submodules to their own repos', async () => {
    expect(await eslint.isPathIgnored('packages/ui/src/sdk/client.ts')).toBe(true);
    expect(await eslint.isPathIgnored('packages/live/live/static/live/sw.js')).toBe(true);
  });

  it("leaves the repo's virtualenv alone (the scripts Django and ninja ship)", async () => {
    expect(await eslint.isPathIgnored('.venv/lib/python3.14/site-packages/django/contrib/admin/static/admin/js/core.js')).toBe(true);
  });

  it('allows the Web Components slot on ion-* and HubIcon, no longer on the retired ok-*', async () => {
    const code = [
      '<template>',
      '  <ion-button>',
      '    <ion-icon slot="start" />',
      '    <HubIcon slot="end" icon="ion:home" />',
      '    <ok-button slot="end" />',
      '  </ion-button>',
      '</template>',
      '',
    ].join('\n');
    expect(await deprecatedSlots(code, 'accounts/frontend/pages/Page.vue')).toEqual(['<ok-button']);
  });

  it.each(['@erplora/ui/testing/mail', '@erplora/ui/testing'])(
    'forbids readMails from %s in an e2e: it stops Playwright reading the whole mail folder (saas#363)',
    async (entry) => {
      const code = `import { readMails } from '${entry}';\nexport const mails = readMails('.mail');\n`;
      for (const spec of ['tests/e2e/panel/accounts-report.spec.ts', 'tests/e2e/recaptcha.spec.ts', 'tests/e2e/panel/fixtures.ts']) {
        expect(await forbiddenImports(code, spec), spec).toEqual([
          expect.stringContaining('readMailsSince'),
        ]);
      }
    },
  );

  it('lets an e2e read the mails written from the action on, and wait for one', async () => {
    const code = [
      "import { readMailCode, readMailsSince, waitForMail } from '@erplora/ui/testing/mail';",
      'export const read = [readMailCode, readMailsSince, waitForMail];',
      '',
    ].join('\n');
    expect(await forbiddenImports(code, 'tests/e2e/panel/assistant-report.spec.ts')).toEqual([]);
  });

  it("leaves the template pages' vendored scripts alone", async () => {
    expect(await eslint.isPathIgnored('static/vendor/ionic/ionic.esm.js')).toBe(true);
  });
});
