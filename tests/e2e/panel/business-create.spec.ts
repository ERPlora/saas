// Creating a business (round 17 §2.3; mockups `businesses.html` «create»/«creating»/«create-ready») in
// Ioan's Chrome: the empty Businesses holds the sign-up form; the address follows the name; after
// «Create my business» the dialog shows the preparation and the row appears «Preparing» through the
// live list; when the Hub reports it ready (here the spec plays the Hub: a signed
// `POST /internal/hubs/{id}/ready`, as hub-next sends it) the dialog says it is ready and the row is
// «Active». The panel's Django (project.ts) sends its calls to the Hub nowhere: a Hub running locally
// never provisions this throwaway business (no orphan database), and the SaaS keeps the registry
// pending as when the Hub is away.
import type { Locator } from '@playwright/test';

import {
  businessIdOf,
  catalogueText,
  expect,
  internalSecret,
  panelAccount,
  provenAccount,
  removeAccountsOf,
  reportBusinessReady,
  seedPanel,
  sidewaysScroll,
  signIn,
  test,
  VIEWPORTS,
  watchPageErrors,
} from './fixtures';

/** The accounts of the address-wrapping test (saas#293), removed after the run. */
const PREFIX = 'e2e-create-host-';
const PASSWORD = 'e2e-create-host-password';

test.beforeAll(() => seedPanel());
// What reportBusinessReady signs with, read here and not inside a test (fixtures.ts, internalSecret).
test.beforeAll(() => internalSecret());
test.afterAll(() => {
  seedPanel('clear');
  removeAccountsOf(PREFIX);
});

test('create → Preparing → the Hub reports it ready → Ready', async ({ page }) => {
  const errors = watchPageErrors(page);
  await signIn(page.request, panelAccount('creator'));
  await page.goto('/dashboard/businesses');
  await expect(page.getByTestId('businesses-empty')).toContainText('Create your first business');

  await page.getByTestId('create-name').locator('input').fill('Pastelería Dulce E2E');
  await expect(page.getByTestId('create-address')).toContainText('Your address will be pasteleria-dulce-e2e');
  await page.getByTestId('create-submit').click();

  await expect(page.getByTestId('create-modal')).toContainText('Preparing Pastelería Dulce E2E');
  await expect(page.getByTestId('create-modal')).toContainText('Business created');
  const row = page.getByTestId('businesses-row').filter({ hasText: 'Pastelería Dulce E2E' });
  await expect(row).toContainText('Preparing');

  await reportBusinessReady(page.request, await businessIdOf(page.request, 'Pastelería Dulce E2E'));

  await expect(page.getByTestId('create-modal')).toContainText('Your business is ready');
  await expect(page.getByTestId('create-modal-open')).toBeVisible();
  await page.getByTestId('create-modal-close-list').click();
  await expect(row).toContainText('Active');
  expect(errors).toEqual([]);
});

/** The painted lines of `host`'s text, one entry per line box (each character measured where it lands). */
function paintedLines(host: Locator): Promise<string[]> {
  return host.evaluate((element) => {
    const lines: { top: number; text: string }[] = [];
    const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      for (let index = 0; index < (node.textContent ?? '').length; index += 1) {
        const range = document.createRange();
        range.setStart(node, index);
        range.setEnd(node, index + 1);
        const top = Math.round(range.getBoundingClientRect().top);
        const line = lines.find((candidate) => Math.abs(candidate.top - top) < 2);
        if (line) line.text += node.textContent![index];
        else lines.push({ top, text: node.textContent![index] });
      }
    }
    return lines.sort((a, b) => a.top - b.top).map((line) => line.text);
  });
}

// saas#293 (HUBS-F01): on a phone the address «Create your business» proposes broke at the hyphen («casa- / lucia.…»), as
// if it were two addresses. Like the launcher's own addresses (HostName, audit 2 R-25) it breaks only after a dot, and
// only when it does not fit on a line of its own: a two-word name's address stays on one line at 390 px, the longest a
// name proposes (a 30-character base) stays inside the hint. In both languages (the account's language wins on the panel).
const NAMES = [
  { name: 'Casa Lucía', host: /^casa-lucia(-\d+)?\./, oneLineOnPhone: true },
  { name: 'Peluquería y Estética Hermanas Fernández', host: /^peluqueria-y-estetica-hermanas(-\d+)?\./, oneLineOnPhone: false },
] as const;

for (const language of ['en', 'es'] as const) {
  test(`HUBS-F01 (${language}): the proposed address breaks only after a dot, on one line on a phone`, async ({ page }) => {
    const errors = watchPageErrors(page);
    const email = `${PREFIX}${language}-${Date.now()}@example.com`;
    provenAccount(email, PASSWORD, language);
    await signIn(page.request, { email, password: PASSWORD });
    await page.goto('/launch');
    await expect(page.getByRole('heading', { name: catalogueText('hubs', language, 'hubs.launch.first.title') })).toBeVisible();
    const hint = page.getByTestId('create-address');
    const host = hint.locator('.mono');

    for (const { name, host: proposed, oneLineOnPhone } of NAMES) {
      await page.setViewportSize(VIEWPORTS[2]);
      await page.getByTestId('create-name').locator('input').fill(name);
      await expect(host).toHaveText(proposed);
      const address = (await host.textContent())!;
      await expect(hint).toHaveText(catalogueText('hubs', language, 'hubs.create.address', { host: address }));

      for (const size of VIEWPORTS) {
        const where = `${name} at ${size.width} px`;
        await page.setViewportSize(size);
        const lines = await paintedLines(host);
        expect(lines.join(''), where).toBe(address);
        for (const line of lines.slice(0, -1)) expect(line, `${where}: a line of ${JSON.stringify(lines)}`).toMatch(/\.$/);
        if (oneLineOnPhone && size.width === 390) expect(lines, `${where}: the address on one line`).toHaveLength(1);
        const [hostBox, hintBox] = [await host.boundingBox(), await hint.boundingBox()];
        expect(hostBox!.x + hostBox!.width, `${where}: inside the hint`).toBeLessThanOrEqual(hintBox!.x + hintBox!.width + 0.5);
        expect(await sidewaysScroll(page), where).toEqual([]);
      }
    }
    expect(errors).toEqual([]);
  });
}
