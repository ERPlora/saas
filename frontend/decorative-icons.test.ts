// Icons of the panel's pages and components (audit 2026-10-14, R-03): an icon sits next to a text that already
// says what it is (a button's own text, a row's title), so it is decorative and hidden from screen readers
// (`aria-hidden="true"`); otherwise a reader announces «image» with no name on every button. Only an icon that
// carries the meaning alone is named (`label` / `aria-label`). An icon-only button is named on the BUTTON
// (`aria-label`), its icon stays decorative. A guard over every `.vue` of the panel (hubs, billing, accounts and the
// entry's own), so a new icon cannot forget it. `HubIcon` of `@erplora/ui` may become decorative by default; the
// explicit attribute keeps the pages right with either version.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const HERE = dirname(fileURLToPath(import.meta.url));
const SAAS_DIR = join(HERE, '..');
/** The panel's frontends (`vite.config.ts` FRONTEND_APPS) and the entry's own components. */
const DIRS = ['hubs/frontend', 'billing/frontend', 'accounts/frontend', 'frontend'].map((dir) => join(SAAS_DIR, dir));

function vueFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return ['node_modules', 'dist', '__tests__'].includes(entry.name) ? [] : vueFiles(path);
    return entry.name.endsWith('.vue') ? [path] : [];
  });
}

/** The `<template>` of a single-file component (comments out: they may quote a tag). */
function template(source: string): string {
  const start = source.indexOf('<template>');
  const end = source.lastIndexOf('</template>');
  if (start < 0 || end < 0) return '';
  return source.slice(start, end).replace(/<!--[\s\S]*?-->/g, '');
}

/** An opening tag's attribute names (`aria-hidden`, `:label`, `slot`…), with their raw values. */
function attributes(raw: string): Map<string, string> {
  const out = new Map<string, string>();
  for (const [, name, value] of raw.matchAll(/([:@#]?[\w.:-]+)(?:="([^"]*)")?/g)) out.set(name, value ?? '');
  return out;
}

/** An opening tag of `name`: its attributes may hold `>` inside quotes. */
const tag = (name: string) => new RegExp(`<${name}\\b((?:\\s+[^\\s=>/]+(?:="[^"]*")?)*)\\s*/?>`, 'g');

const NAMES = ['label', ':label', 'v-bind:label', 'aria-label', ':aria-label', 'aria-labelledby', ':aria-labelledby'];
const named = (attrs: Map<string, string>) => NAMES.some((name) => attrs.has(name));

const FILES = DIRS.flatMap((dir) => vueFiles(dir));

describe('icons of the panel', () => {
  it('finds the pages and components of every panel app', () => {
    for (const app of ['hubs', 'billing', 'accounts']) {
      expect(FILES.filter((file) => relative(SAAS_DIR, file).startsWith(`${app}/`)).length, app).toBeGreaterThan(5);
    }
  });

  it('hide every icon without a name from screen readers (`aria-hidden="true"`)', () => {
    const offenders: string[] = [];
    for (const file of FILES) {
      const markup = template(readFileSync(file, 'utf8'));
      for (const element of ['HubIcon', 'ion-icon']) {
        for (const match of markup.matchAll(tag(element))) {
          const attrs = attributes(match[1]);
          if (named(attrs)) continue;
          if (attrs.get('aria-hidden') !== 'true') offenders.push(`${relative(SAAS_DIR, file)}: ${match[0].replace(/\s+/g, ' ')}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  it('name every icon-only button on the button itself', () => {
    const offenders: string[] = [];
    const icon = /<(?:HubIcon|ion-icon)\b(?:\s+[^\s=>/]+(?:="[^"]*")?)*\s*\/?>(?:\s*<\/ion-icon>)?/g;
    for (const file of FILES) {
      const markup = template(readFileSync(file, 'utf8'));
      for (const match of markup.matchAll(/<ion-button\b((?:\s+[^\s=>/]+(?:="[^"]*")?)*)\s*>([\s\S]*?)<\/ion-button>/g)) {
        const inner = match[2];
        if (!icon.test(inner)) continue;
        icon.lastIndex = 0;
        if (inner.replace(icon, '').trim() !== '') continue;
        if (!named(attributes(match[1]))) offenders.push(`${relative(SAAS_DIR, file)}: ${match[0].replace(/\s+/g, ' ').slice(0, 160)}`);
      }
    }
    expect(offenders).toEqual([]);
  });
});
