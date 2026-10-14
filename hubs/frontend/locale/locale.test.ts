// The texts of the businesses panel (launcher, Businesses, a business's page, the invitation): English
// source + Spanish (PLAN §5), kept by hand next to the pages until Django's catalogues are exported to
// JSON. Every text is new (the old SaaS's templates are not ported here), so the guard is the shape:
// one root (`hubs`), the same keys in both languages, nothing empty, the same placeholders and plural
// forms, and every key a page or a component asks for exists.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import operations from '../../../frontend/generated/operations.json';
import en from './en.json';
import es from './es.json';

type Catalogue = { [key: string]: string | Catalogue };

const HERE = dirname(fileURLToPath(import.meta.url));
const FRONTEND = join(HERE, '..');

/** vue-i18n's separator of plural forms (`singular | plural`). */
const PLURAL = ' | ';

function flatten(catalogue: Catalogue, prefix = ''): Map<string, string> {
  const out = new Map<string, string>();
  for (const [key, value] of Object.entries(catalogue)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === 'string') out.set(path, value);
    else for (const [k, v] of flatten(value, path)) out.set(k, v);
  }
  return out;
}

/** The sources that ask for texts: every `.vue` and `.ts` of the frontend but the tests. */
function sources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return entry.name === '__tests__' ? [] : sources(path);
    return /\.(vue|ts)$/.test(entry.name) && !entry.name.endsWith('.test.ts') ? [path] : [];
  });
}

const EN = flatten(en as Catalogue);
const ES = flatten(es as Catalogue);

describe('hubs catalogues (en source + es)', () => {
  it('live under the app prefix, so merging them into the shell never collides', () => {
    expect(Object.keys(en)).toEqual(['hubs']);
    expect(Object.keys(es)).toEqual(['hubs']);
  });

  it('have exactly the same keys', () => {
    expect([...ES.keys()].sort()).toEqual([...EN.keys()].sort());
  });

  it('have no empty message', () => {
    for (const [key, message] of [...EN, ...ES]) expect(message.trim(), key).not.toBe('');
  });

  it('write a plural with as many forms in both languages', () => {
    const forms = (message: string) => message.split(PLURAL).length;
    for (const [key, message] of EN) expect(forms(ES.get(key)!), key).toBe(forms(message));
  });

  it('write a placeholder the same in both languages', () => {
    const placeholders = (message: string) => [...message.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();
    for (const [key, message] of EN) expect(placeholders(ES.get(key)!), key).toEqual(placeholders(message));
  });

  it("use none of vue-i18n's special characters as text (an e-mail's @ would be read as a link)", () => {
    for (const [key, message] of [...EN, ...ES]) expect(message, key).not.toMatch(/[@$]/);
  });

  it('cover every key the pages and components ask for: calls, `keypath`, tables and template literals', () => {
    const files = sources(FRONTEND);
    expect(files.length).toBeGreaterThan(0);
    for (const file of files) expect(missingKeys(readFileSync(file, 'utf8')), file).toEqual([]);
  });

  it('the reader finds a missing key in every form a source writes one', () => {
    const source = [
      "t('hubs.nope.call')",
      'keypath="hubs.nope.keypath"',
      "const TABLE = { a: { label: 'hubs.nope.table' } };",
      '$t(`hubs.nope.${id}`)',
      "useLive('hubs.business.list')", // an operation, not a text
      "error.code === 'hubs.seat_limit'", // an error code, not a text
      "t('hubs.list.title')",
      '$t(`hubs.business.tabs.${section.id}`)',
    ].join('\n');
    expect(missingKeys(source)).toEqual(['hubs.nope.call', 'hubs.nope.keypath', 'hubs.nope.table', 'hubs.nope.*']);
  });
});

/** The operations of the SaaS: their names look like keys (`hubs.business.list`) and are not texts. */
const OPERATIONS = new Set(Object.keys(operations));

/** Every catalogue key a source names and the catalogue lacks; a template literal names a subtree (`*`). */
function missingKeys(source: string): string[] {
  const missing: string[] = [];
  for (const [, key, end] of source.matchAll(/['"`](hubs\.[\w.]*?)(\$\{|['"`])/g)) {
    if (end === '${') {
      const prefix = key.replace(/\.$/, '');
      if (![...EN.keys()].some((known) => known.startsWith(`${prefix}.`))) missing.push(`${prefix}.*`);
      continue;
    }
    // An error code (`hubs.seat_limit`) has two parts; a text has at least three.
    if (OPERATIONS.has(key) || key.split('.').length < 3) continue;
    if (!EN.has(key)) missing.push(key);
  }
  return missing;
}
