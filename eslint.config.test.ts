// @vitest-environment node
// Lint of the SaaS: the SPA reaches the server only through the SDK (`@erplora/ui/sdk`), so the
// shell entry and every app frontend are linted for raw network globals. Linted for real here.
import { existsSync, readdirSync, readFileSync } from 'node:fs';
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

  it('fails a function whose complexity passes 15, counting optional chaining', async () => {
    expect(await functionLimits(branchy(15), 'billing/frontend/pick.ts')).toEqual([]);
    expect(await functionLimits(branchy(16), 'billing/frontend/pick.ts')).toEqual(['complexity']);
    expect(await functionLimits(chained(15), 'billing/frontend/pick.ts')).toEqual(['complexity']);
  });

  it('fails blocks nested deeper than 4', async () => {
    expect(await functionLimits(nested(4), 'billing/frontend/nest.ts')).toEqual([]);
    expect(await functionLimits(nested(5), 'billing/frontend/nest.ts')).toEqual(['max-depth']);
  });

  it('fails a function with more than 3 parameters', async () => {
    expect(await functionLimits(withParameters(3), 'billing/frontend/sum.ts')).toEqual([]);
    expect(await functionLimits(withParameters(4), 'billing/frontend/sum.ts')).toEqual(['max-params']);
  });

  it('fails a function longer than 50 lines, not counting blank lines and comments', async () => {
    expect(await functionLimits(long(50), 'billing/frontend/long.ts')).toEqual([]);
    expect(await functionLimits(long(51), 'billing/frontend/long.ts')).toEqual(['max-lines-per-function']);
  });

  it('applies the limits to the script of a .vue page too', async () => {
    const page = `<script setup lang="ts">\n${withParameters(4)}</script>\n<template><div /></template>\n`;
    expect(await functionLimits(page, 'billing/frontend/pages/Page.vue')).toEqual(['max-params']);
  });

  it('suppresses only in files it lints: ESLint skips the entry of a deleted or renamed file without a word', async () => {
    const suppressions = JSON.parse(readFileSync(join(SAAS_DIR, 'eslint-suppressions.json'), 'utf8'));
    for (const path of Object.keys(suppressions)) {
      expect(existsSync(join(SAAS_DIR, path)), path).toBe(true);
      expect(await eslint.isPathIgnored(path), path).toBe(false);
    }
  });

  it('lints no shell script, though a script test is named like a test', async () => {
    expect(await eslint.isPathIgnored('.github/scripts/deploy-env.test.sh')).toBe(true);
    expect(await eslint.isPathIgnored('docker/image.test.sh')).toBe(true);
  });

  it('fails a Vue block past its cap, blank lines included: template 250, script 300 and style 150', async () => {
    const path = 'billing/frontend/pages/LongPage.vue';
    expect(await longBlocks(vuePage({ template: 250, script: 300, style: 150 }), path)).toEqual([]);
    expect(await longBlocks(vuePage({ template: 251, script: 301, style: 151 }), path)).toEqual([
      'template',
      'script',
      'style',
    ]);
  });

  it('takes no comment that switches a rule off: a limit is never silenced in the code', async () => {
    const code = `/* eslint-disable max-params */\n${withParameters(4)}`;
    expect(await functionLimits(code, 'billing/frontend/sum.ts')).toEqual(['max-params']);
    const page = vuePage({ template: 251, script: 1, style: 1 }).replace(
      '<template>',
      '<!-- eslint-disable vue/max-lines-per-block -->\n<template>',
    );
    expect(await longBlocks(page, 'billing/frontend/pages/LongPage.vue')).toEqual(['template']);
  });

  it.each([
    'billing/frontend/pick.test.ts',
    'billing/frontend/__tests__/mount-billing.ts',
    'tests/e2e/panel/fixtures.ts',
    'tests/e2e/public-web.spec.ts',
  ])(
    'lets a test have long functions and many parameters, not more complexity or depth: %s',
    async (test) => {
      expect(await functionLimits(long(80) + withParameters(6), test)).toEqual([]);
      expect(await functionLimits(branchy(16) + nested(5), test)).toEqual(['complexity', 'max-depth']);
    },
  );
});

const FUNCTION_LIMITS = ['complexity', 'max-depth', 'max-params', 'max-lines-per-function'];

/** The function limits the lint fails on `code`, as errors: a warning would not stop `pnpm lint`. */
async function functionLimits(code: string, filePath: string): Promise<string[]> {
  const [result] = await eslint.lintText(code, { filePath });
  const limits = result.messages.filter((m) => FUNCTION_LIMITS.includes(m.ruleId ?? ''));
  expect(limits.every((m) => m.severity === 2), JSON.stringify(limits)).toBe(true);
  return [...new Set(limits.map((m) => m.ruleId ?? ''))].sort();
}

/** The blocks of a Vue page the lint fails as too long, as errors, in the order they appear. */
async function longBlocks(code: string, filePath: string): Promise<string[]> {
  const [result] = await eslint.lintText(code, { filePath });
  const blocks = result.messages.filter((m) => m.ruleId === 'vue/max-lines-per-block');
  expect(blocks.every((m) => m.severity === 2), JSON.stringify(blocks)).toBe(true);
  return blocks.map((m) => code.split('\n')[m.line - 1].replace(/^<(\w+).*$/, '$1'));
}

/** `count` lines of `text`, every other one blank. */
function lines(count: number, text: (n: number) => string): string {
  return Array.from({ length: count }, (_, n) => (n % 2 ? '' : text(n))).join('\n');
}

/** A Vue page whose blocks hold the given number of lines between their opening and closing tags. */
function vuePage(blocks: { template: number; script: number; style: number }): string {
  return [
    `<template>\n${lines(blocks.template, (n) => `  <p>${n}</p>`)}\n</template>`,
    `<script setup lang="ts">\n${lines(blocks.script, (n) => `const line${n} = ${n};`)}\n</script>`,
    `<style scoped>\n${lines(blocks.style, (n) => `.line${n} { order: ${n}; }`)}\n</style>`,
    '',
  ].join('\n');
}

/** A function of the given complexity, one `if` per point past the first. */
function branchy(complexity: number): string {
  const ifs = Array.from({ length: complexity - 1 }, (_, n) => `  if (value === ${n}) return '${n}';\n`);
  return `export function pick${complexity}(value: number): string {\n${ifs.join('')}  return '';\n}\n`;
}

/** A function of the given complexity made of optional chaining only. */
function chained(steps: number): string {
  return `export function path${steps}(value: any): unknown {\n  return value${'?.next'.repeat(steps)};\n}\n`;
}

function nested(depth: number): string {
  const open = Array.from({ length: depth }, (_, n) => `${'  '.repeat(n + 1)}if (value > ${n}) {\n`);
  const close = Array.from({ length: depth }, (_, n) => `${'  '.repeat(depth - n)}}\n`);
  return `export function nest${depth}(value: number): number {\n${open.join('')}  value += 1;\n${close.join('')}  return value;\n}\n`;
}

function withParameters(count: number): string {
  const names = Array.from({ length: count }, (_, n) => `p${n}: number`);
  return `export function sum${count}(${names.join(', ')}): number {\n  return ${count};\n}\n`;
}

/** A function of `lines` lines counted with its signature and closing brace, plus blank lines and comments that do not count. */
function long(lines: number): string {
  const body = Array.from({ length: lines - 4 }, (_, n) => `  total += ${n};\n\n  // step ${n}\n`);
  return `export function long${lines}(): number {\n  let total = 0;\n${body.join('')}  return total;\n}\n`;
}
