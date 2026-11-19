// A comment that names the Python file a list mirrors sends the reader there: when that file moves (a module
// that becomes a package), the comment has to move with it. A file of the Hub is named with its folder,
// `hub/base/auth_views.py`: the Hub is another repository, so this one cannot tell whether it exists.
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import { FRONTEND_APPS } from '../vite.config';

const SAAS_DIR = join(dirname(fileURLToPath(import.meta.url)), '..');
/** The shell entry and the frontend of every app of the panel. */
const FRONTENDS = ['frontend', ...FRONTEND_APPS.map((app) => join(app, 'frontend'))];
/** A path with at least one folder, relative to the SaaS (`billing/models/invoices.py`). */
const PYTHON_FILE = /[\w.-]+(?:\/[\w.-]+)+\.py\b/g;
const HUB_FILE = /^hub\//;

function sources(folder: string): string[] {
  return readdirSync(join(SAAS_DIR, folder), { recursive: true, encoding: 'utf8' })
    .filter((name) => /\.(ts|vue)$/.test(name))
    .map((name) => join(folder, name));
}

describe('the Python files named in the frontends of the SaaS', () => {
  it('all exist', () => {
    const named = FRONTENDS.flatMap(sources).flatMap((file) =>
      (readFileSync(join(SAAS_DIR, file), 'utf8').match(PYTHON_FILE) ?? [])
        .filter((path) => !HUB_FILE.test(path))
        .map((path) => ({ file, path })),
    );
    expect(named.length, 'paths found: an empty scan proves nothing').toBeGreaterThan(0);
    expect(named.filter(({ path }) => !existsSync(join(SAAS_DIR, path)))).toEqual([]);
  }, 60_000);
});
