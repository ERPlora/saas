// What the specs of the public web share (public-web.spec.ts, public-web-menu.spec.ts): where their captures go and
// the watch on CSP violations and page errors.
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import type { Page } from '@playwright/test';

import { expect } from './public-test';

const HERE = dirname(fileURLToPath(import.meta.url));
export const ARTIFACTS = join(HERE, '.artifacts');

/** Every CSP violation and page error, however the browser reports it (as demo-door.spec.ts). */
export async function watch(page: Page) {
  const reports: string[] = [];
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  page.on('request', (request) => {
    if (request.url().includes('/csp-report/')) reports.push(request.postData() ?? '');
  });
  page.on('console', (message) => {
    if (/content security policy|trusted ?type|refused to/i.test(message.text())) consoleErrors.push(message.text());
  });
  page.on('pageerror', (error) => pageErrors.push(String(error)));
  await page.addInitScript(() => {
    const w = window as unknown as { __csp: string[] };
    w.__csp = [];
    document.addEventListener('securitypolicyviolation', (event) =>
      w.__csp.push(`${event.violatedDirective} ${event.blockedURI}`),
    );
  });
  return async (where: string) => {
    const violations = await page.evaluate(() => (window as unknown as { __csp: string[] }).__csp);
    expect({ violations, reports, consoleErrors, pageErrors }, where).toEqual({
      violations: [],
      reports: [],
      consoleErrors: [],
      pageErrors: [],
    });
  };
}
