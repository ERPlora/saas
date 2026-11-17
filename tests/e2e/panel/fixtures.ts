// Import `test` and `expect` from here, not from `@playwright/test`.
import { type BrowserContext, type Page, test as base, expect } from '@playwright/test';

import { type Credentials, OWNER, seedAccountsAsync } from './accounts';
import { runSeed, runSeedWarm, warmDjango } from './django';
import { VITE_PORT, viteHmrSocket } from './project';
import { signIn } from './session';

export { expect };

/** This run's Vite's hot-update socket (`VITE_DEV_PORT`, panel/project.ts). */
const VITE_HMR = viteHmrSocket(VITE_PORT);

/**
 * Cuts `context`'s pages off from Vite's hot updates: the socket opens, answered by the spec, and
 * nothing arrives. Another session saving a `.vue` mid-run (a shared component, DataTable) would
 * otherwise remount components under the spec and leave an open dialog behind. Every page load
 * still gets the files as they are on disk. The `context` of every panel spec already has it.
 */
export async function freezeFrontend(context: BrowserContext): Promise<void> {
  await context.routeWebSocket(VITE_HMR, () => {});
}

export const test = base.extend<{ signedInPage: Page }, { owner: Credentials }>({
  // Every page of a spec: no hot updates mid-spec (`freezeFrontend`).
  context: async ({ context }, use) => {
    await freezeFrontend(context);
    await use(context);
  },
  // Once per worker: the accounts exist before any spec signs in. Seeded without blocking Node (saas#358); as every
  // worker fixture, on a clock of its own (the project's timeout), never on the first test's.
  owner: [
    // Playwright reads a fixture's dependencies from its first parameter's pattern: none here.
    async ({}, use) => {
      await seedAccountsAsync();
      await use(OWNER);
    },
    { scope: 'worker' },
  ],
  // A page whose context is signed in as the owner, through the API (fast; no form on screen).
  signedInPage: async ({ page, owner }, use) => {
    await signIn(page.request, owner);
    await use(page);
  },
});

/**
 * Every test of the spec, or of the `describe` it is called in, starts from the rows of `script` (`runSeed`) seeded
 * afresh, its page signed in as `account` through the API; once the last test has run, the rows go.
 */
export function seededAndSignedIn(script: string, account: Credentials): void {
  test.beforeEach(async ({ page }) => {
    runSeed(script, 'seed');
    await signIn(page.request, account);
  });
  test.afterAll(() => runSeed(script, 'clear'));
}

/**
 * `seededAndSignedIn` with every test's seed run by the warm Django (`runSeedWarm`): every test of the spec, or of the
 * `describe` it is called in, starts from the rows of `script` seeded afresh, its page signed in as `account` through
 * the API; once the last test has run, the rows go. The warm Django starts in a `beforeAll`, on no test's clock.
 */
export function seededAndSignedInWarm(script: string, account: Credentials): void {
  test.beforeAll(() => warmDjango());
  test.beforeEach(async ({ page }) => {
    await runSeedWarm(script, 'seed');
    await signIn(page.request, account);
  });
  test.afterAll(() => runSeedWarm(script, 'clear'));
}
