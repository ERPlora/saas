// A comment that names the Python file a list mirrors sends the reader there: when that file moves (a module
// that becomes a package), the comment has to move with it.
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const SAAS_DIR = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const FOLDER = join('hubs', 'frontend');
/** A path with at least one folder, relative to the SaaS (`billing/models/invoices.py`). */
const PYTHON_FILE = /[\w.-]+(?:\/[\w.-]+)+\.py\b/g;

describe('the Python files named in hubs/frontend', () => {
  it('all exist', () => {
    const named = readdirSync(join(SAAS_DIR, FOLDER), { recursive: true, encoding: 'utf8' })
      .filter((name) => /\.(ts|vue)$/.test(name))
      .flatMap((name) => {
        const text = readFileSync(join(SAAS_DIR, FOLDER, name), 'utf8');
        return (text.match(PYTHON_FILE) ?? []).map((path) => ({ file: join(FOLDER, name), path }));
      });
    expect(named.length, 'paths found: an empty scan proves nothing').toBeGreaterThan(0);
    expect(named.filter(({ path }) => !existsSync(join(SAAS_DIR, path)))).toEqual([]);
  }, 60_000);
});
