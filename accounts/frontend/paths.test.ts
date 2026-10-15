// The launcher's path, named once (`paths.ts`): the sign-in lives there (round 19, PLAN-SAAS §3.7), so every
// page, component and the entry that sends a visitor to it imports `LAUNCHER` instead of spelling the path
// under a name of its own (`LOGIN`, `SIGN_IN`, `HERE`…). Only the `routes.ts` files spell it: they import types
// only (main.test.ts), so they cannot import a value.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import hubRoutes from '../../hubs/frontend/routes';
import { LAUNCHER } from './paths';

const SAAS_DIR = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
/** The panel's frontends (`vite.config.ts` FRONTEND_APPS) and the entry. */
const DIRS = ['accounts/frontend', 'hubs/frontend', 'billing/frontend', 'frontend'].map((dir) => join(SAAS_DIR, dir));
/** The launcher's path as a string literal in code (`'/launch'`, `"/launch"`, `'/launch?…'`). */
const SPELLED = /['"]\/launch(?=['"?#])/;

function sources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      return ['node_modules', 'dist', 'generated', '__tests__'].includes(entry.name) ? [] : sources(path);
    }
    const code = /\.(ts|vue)$/.test(entry.name) && !entry.name.endsWith('.test.ts');
    return code && entry.name !== 'routes.ts' && entry.name !== 'paths.ts' ? [path] : [];
  });
}

describe('LAUNCHER', () => {
  it('is the path of the launcher route, where the sign-in lives', () => {
    expect(LAUNCHER).toBe('/launch');
    expect(hubRoutes.map((route) => route.path)).toContain(LAUNCHER);
  });

  it('is the only spelling of the path outside the routes files', () => {
    const spelled = DIRS.flatMap(sources)
      .filter((file) => SPELLED.test(readFileSync(file, 'utf8')))
      .map((file) => relative(SAAS_DIR, file));
    expect(spelled).toEqual([]);
  });
});
