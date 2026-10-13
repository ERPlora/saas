// Icon guardrail of the SaaS (PLAN §16.4): an icon that is not registered in @erplora/ui's shell
// paints NOTHING (no network for icons, by CSP), so a page or a component that names one must fail
// a test, not a sign-in. `scanIcons` is the reader @erplora/ui runs on itself; here it reads the
// SaaS's own sources. It resolves icons through the baked `~icons/*` modules, so it needs the
// `erploraVite()` plugins of vite.config.ts.
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { scanIcons } from '@erplora/ui/testing';
import { describe, expect, it } from 'vitest';

import { FRONTEND_APPS } from '../vite.config';

/** The root of saas-next: the globs below are relative to it. */
const SAAS_DIR = join(dirname(fileURLToPath(import.meta.url)), '..');
/**
 * Where the SaaS names icons: the shell entry and the frontend of every root app. The apps go in one
 * glob: some have no `frontend/` yet, so only their union must read something.
 */
const SOURCES = ['frontend/**/*.ts', `{${FRONTEND_APPS.join(',')}}/frontend/**/*.{vue,ts}`];

describe('guardrail: every icon the SaaS names is registered', () => {
  it('every icon named in the entry and the apps is registered, and every glob reads something', () => {
    expect(scanIcons({ root: SAAS_DIR, sources: SOURCES })).toEqual({ unregistered: [], emptyGlobs: [] });
  });
});
