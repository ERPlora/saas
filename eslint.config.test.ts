// @vitest-environment node
// Lint of saas-next: the SPA reaches the server only through the SDK (`@erplora/ui/sdk`), so the
// shell entry and every app frontend are linted for raw network globals. Linted for real here.
import { existsSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { ESLint } from 'eslint';
import { describe, expect, it } from 'vitest';

const SAAS_DIR = dirname(fileURLToPath(import.meta.url));
const eslint = new ESLint({ cwd: SAAS_DIR });

/** The apps of saas-next with a frontend: root directories next to `base/` holding a `frontend/` (no `apps/`, PLAN §20.2). */
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

/** The elements whose `slot="…"` attribute the lint reports as Vue 2 syntax. */
async function deprecatedSlots(code: string, filePath: string): Promise<string[]> {
  const [result] = await eslint.lintText(code, { filePath });
  return result.messages
    .filter((m) => m.ruleId === 'vue/no-deprecated-slot-attribute')
    .map((m) => code.split('\n')[m.line - 1].trim().split(/[\s>]/)[0]);
}

describe('eslint config', () => {
  it.each(['fetch', 'EventSource', 'WebSocket', 'XMLHttpRequest'])('forbids %s in an app page and in the entry', async (name) => {
    const code = `export const x = ${name};\n`;
    expect(await restricted(code, 'accounts/frontend/pages/LoginPage.ts')).toHaveLength(1);
    expect(await restricted(code, 'frontend/main.ts')).toHaveLength(1);
  });

  it('forbids it in the <script setup> of a .vue page too', async () => {
    const code = `<script setup lang="ts">\nconst session = fetch('/_allauth/browser/v1/auth/session');\n</script>\n<template><div>{{ session }}</div></template>\n`;
    expect(await restricted(code, 'accounts/frontend/pages/LoginPage.vue')).toEqual([
      "Unexpected use of 'fetch'. Network access goes through the SDK (@erplora/ui/sdk).",
    ]);
  });

  it('forbids it in the frontend of every root app (saas-next has no apps/, PLAN §20.2)', async () => {
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

  it('allows the Web Components slot on ion-* and HubIcon, no longer on the retired ok-* (PLAN §16.11)', async () => {
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

  it("leaves the template pages' vendored scripts alone", async () => {
    expect(await eslint.isPathIgnored('static/vendor/ionic/ionic.esm.js')).toBe(true);
  });
});
