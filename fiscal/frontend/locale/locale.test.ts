// The texts of fiscal in the panel (the authorisation for ERPlora to file a business's invoices, on its
// Summary): English source + Spanish (PLAN §5), kept by hand next to the components until Django's
// catalogues are exported to JSON. The guard is the shape, as the hubs catalogue's: one root (`fiscal`),
// the same keys in both languages, nothing empty, the same placeholders and plural forms, and every key
// a component asks for exists.
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

describe('fiscal catalogues (en source + es)', () => {
  it('live under the app prefix, so merging them into the shell never collides', () => {
    expect(Object.keys(en)).toEqual(['fiscal']);
    expect(Object.keys(es)).toEqual(['fiscal']);
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

  it('cover every key the components ask for: calls, `keypath`, tables and template literals', () => {
    const files = sources(FRONTEND);
    expect(files.length).toBeGreaterThan(0);
    for (const file of files) expect(missingKeys(readFileSync(file, 'utf8')), file).toEqual([]);
  });

  it('the reader finds a missing key in every form a source writes one', () => {
    const source = [
      "t('fiscal.nope.call')",
      'keypath="fiscal.nope.keypath"',
      "const TABLE = { a: { label: 'fiscal.nope.table' } };",
      '$t(`fiscal.nope.${id}`)',
      "useLive('fiscal.representation.status')", // an operation, not a text
      "error.code === 'fiscal.invalid_nif'", // an error code, not a text
      "t('fiscal.representation.title')",
      '$t(`fiscal.representation.state.${status}`)',
    ].join('\n');
    expect(missingKeys(source)).toEqual(['fiscal.nope.call', 'fiscal.nope.keypath', 'fiscal.nope.table', 'fiscal.nope.*']);
  });
});

/** The operations of the SaaS: their names look like keys (`fiscal.representation.status`) and are not texts. */
const OPERATIONS = new Set(Object.keys(operations));

/** Every catalogue key a source names and the catalogue lacks; a template literal names a subtree (`*`). */
function missingKeys(source: string): string[] {
  const missing: string[] = [];
  for (const [, key, end] of source.matchAll(/['"`](fiscal\.[\w.]*?)(\$\{|['"`])/g)) {
    if (end === '${') {
      const prefix = key.replace(/\.$/, '');
      if (![...EN.keys()].some((known) => known.startsWith(`${prefix}.`))) missing.push(`${prefix}.*`);
      continue;
    }
    // An error code (`fiscal.invalid_nif`) has two parts; a text has at least three.
    if (OPERATIONS.has(key) || key.split('.').length < 3) continue;
    if (!EN.has(key)) missing.push(key);
  }
  return missing;
}
