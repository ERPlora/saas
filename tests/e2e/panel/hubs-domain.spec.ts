// HUBS-F17, «Own domain» in a business's Settings (saas#195), in a real browser, in English and in Spanish, at
// three sizes (fixtures' VIEWPORTS: 390×844, 834×1112, 1440×900): the owner writes a domain, what the server
// refuses of it goes on its field, and asking for it gives the two CNAME records to create, each copied with
// «Copy»; the page reads what the server keeps through the real API, and removing it lets the name go. A connected
// domain counts the checks that failed against the three that stop it; one that is not connected says why and is
// asked for again; a plan without it leads to the plans. Each screen: no sideways scroll, no field's label cut, no
// page error, its texts the catalogue's (hubs/frontend/locale/<language>.json) and a capture
// `HUBS-F17-<screen>-<size>-<language>`.
//
// The panel's Django connects domains here (project.ts) and sends AWS to the Hub double's port: this spec plays ACM
// there (its certificate and its validation record, then its deletion) and the Hub's acknowledgements, as the hourly
// check and the removal need them. The DNS is the box's own: `example.com` and `example.org` are IANA's for good, and a
// DNS that cannot answer lets the domain through as well. Accounts of this spec: `e2e-domain-…@example.com`.
import { createServer, type Server } from 'node:http';

import { type Locator, type Page } from '@playwright/test';

import {
  captureAtEverySize,
  catalogueText,
  createAccountWarm,
  djangoPrintWarm,
  expect,
  readyBusinessOn,
  removeAccountsWarm,
  signIn,
  test,
  watchPageErrors,
} from './fixtures';
import { HUB_DOUBLE_PORT } from './project';

const capture = captureAtEverySize('HUBS-F17');

const PREFIX = 'e2e-domain-';
const PASSWORD = 'Dominio-propio-de-la-web-26';
const RUNS = [
  { language: 'en', locale: 'en-US', domain: 'www.example.com' },
  { language: 'es', locale: 'es-ES', domain: 'www.example.org' },
] as const;
type Language = (typeof RUNS)[number]['language'];

/** What the server says in each language (hubs/locale/es/LC_MESSAGES/django.po): its labels and refusals. */
const SERVER = {
  en: {
    ours: 'That domain belongs to ERPlora. Write your own.',
    waiting: 'Waiting for your records',
    certificatePending: 'Create the validation record: the certificate is waiting for it.',
    connected: 'Connected',
    cnameMissing: 'Create the record that points your domain at ERPlora.',
    notConnected: 'Not connected',
    checksFailed: 'It comes back by itself when the record does.',
  },
  es: {
    ours: 'Ese dominio es de ERPlora. Escribe el tuyo.',
    waiting: 'Esperando tus registros',
    certificatePending: 'Crea el registro de validación: el certificado lo está esperando.',
    connected: 'Conectado',
    cnameMissing: 'Crea el registro que apunta tu dominio a ERPlora.',
    notConnected: 'Sin conectar',
    checksFailed: 'Volverá sola cuando vuelva el registro.',
  },
} as const;

/** The card's text of `hubs.domain.<key>` in `language` (hubs/frontend/locale/<language>.json). */
const say = (language: Language, key: string, params: Record<string, string | number> = {}) =>
  catalogueText('hubs', language, `hubs.domain.${key}`, params);

// --- What this spec plays on the Hub double's port: ACM, and the Hub's acknowledgements --------------------------------

interface AwsCall {
  target: string;
  body: Record<string, unknown>;
}

const aws: AwsCall[] = [];
let certificates = 0;
let double: Server;

/** ACM's answer to `target` (its JSON protocol), or `null` for a call this spec does not play. */
function acm(target: string, body: Record<string, unknown>): Record<string, unknown> | null {
  if (target === 'CertificateManager.RequestCertificate') {
    return { CertificateArn: `arn:aws:acm:eu-west-1:000000000000:certificate/e2e-${++certificates}` };
  }
  if (target === 'CertificateManager.DescribeCertificate') {
    const issued = aws.find((call) => call.target === 'CertificateManager.RequestCertificate');
    const domain = String(issued?.body.DomainName ?? '');
    return {
      Certificate: {
        CertificateArn: body.CertificateArn,
        DomainName: domain,
        Status: 'PENDING_VALIDATION',
        DomainValidationOptions: [
          {
            DomainName: domain,
            ValidationMethod: 'DNS',
            ResourceRecord: { Name: `_e2e0a1b2c3d4.${domain}.`, Type: 'CNAME', Value: '_e2e5f6a7b8c9.xlfgrmvvlj.acm-validations.aws.' },
          },
        ],
      },
    };
  }
  return target === 'CertificateManager.DeleteCertificate' ? {} : null;
}

function startDouble(): Promise<Server> {
  const server = createServer((request, response) => {
    const chunks: Buffer[] = [];
    request.on('data', (chunk: Buffer) => chunks.push(chunk));
    request.on('end', () => {
      const target = String(request.headers['x-amz-target'] ?? '');
      if (target) {
        const body = JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}') as Record<string, unknown>;
        aws.push({ target, body });
        const answer = acm(target, body);
        response.writeHead(answer ? 200 : 400, { 'Content-Type': 'application/x-amz-json-1.1' });
        response.end(JSON.stringify(answer ?? { __type: 'ValidationException', message: `not played: ${target}` }));
        return;
      }
      // The Hub: its registry and the snapshot, acknowledged; the rest, away.
      const played = request.method === 'PUT' && /^\/internal\/hubs\/[0-9a-f-]+(\/state)?$/.test(request.url ?? '');
      response.writeHead(played ? 200 : 503, { 'Content-Type': 'application/json' });
      response.end(played ? '{}' : '{"error":{"code":"hub_away"}}');
    });
  });
  return new Promise((listening, failed) => {
    server.once('error', failed);
    server.listen(HUB_DOUBLE_PORT, '127.0.0.1', () => listening(server));
  });
}

// Django's boot on no test's clock (saas#354): the warm Django starts here.
test.beforeAll(async () => {
  [double] = await Promise.all([startDouble(), removeAccountsWarm(PREFIX)]);
});
test.afterAll(async () => {
  await new Promise((closed) => double.close(closed));
  await removeAccountsWarm(PREFIX);
});
test.beforeEach(() => {
  aws.length = 0;
});

// --- The business and its screens --------------------------------------------------------------------------------------

/** A fresh owner speaking `language`, signed in on `page`, of a business ready as the Hub leaves it, on `plan`. */
async function ownerOn(page: Page, language: Language, plan: string): Promise<string> {
  const email = `${PREFIX}${plan}-${language}-${Date.now()}@example.com`;
  await createAccountWarm(email, PASSWORD, { language });
  await signIn(page.request, { email, password: PASSWORD });
  return readyBusinessOn(page.request, 'Peluquería Aurora', plan);
}

/** The card «Own domain» of the page on screen (Ionic keeps the pages it left in the DOM, hidden). */
const card = (page: Page): Locator =>
  page.locator('ion-router-outlet > .ion-page:not(.ion-page-hidden)').last().getByTestId('custom-domain');

/** The labels of the fields on screen that Ionic cuts with «…». */
function cutLabels(page: Page): Promise<string[]> {
  return page.evaluate(() =>
    [...document.querySelectorAll<HTMLElement>('ion-input .label-text')]
      .filter((label) => label.offsetParent !== null && label.scrollWidth > label.clientWidth + 1)
      .map((label) => label.textContent?.trim() ?? ''),
  );
}

/**
 * `ready` at each size: no sideways scroll, no label cut, and the card «Own domain» whole in a capture
 * `HUBS-F17-<screen>-<size>-<language>` (the page scrolls inside its content, so a page capture would cut it).
 */
function atEverySize(page: Page, screen: string, language: Language, ready: () => Promise<void>): Promise<void> {
  return capture(page, screen, ready, {
    of: card(page),
    suffix: language,
    checks: async (size) => expect(await cutLabels(page), `${screen}: a label cut at ${size.width}`).toEqual([]),
  });
}

/** What the server keeps of the business's domain, through the panel's own API. */
async function kept(page: Page, id: string): Promise<{ available: boolean; in_plan: boolean; domain: Record<string, unknown> | null }> {
  const answer = await page.request.get(`/api/hubs/businesses/custom-domain?id=${id}`);
  expect(answer.status(), await answer.text()).toBe(200);
  return answer.json();
}

for (const { language, locale, domain } of RUNS) {
  test.describe(`in ${language}`, () => {
    test.use({ locale });

    test(`HUBS-F17 (${language}): the owner connects ${domain}, copies its two records and removes it`, async ({ page }) => {
      const errors = watchPageErrors(page);
      await page.context().grantPermissions(['clipboard-read', 'clipboard-write']);
      const id = await ownerOn(page, language, 'standard');
      await page.goto(`/dashboard/businesses/${id}/settings`);
      const own = card(page);
      await atEverySize(page, 'form', language, async () => {
        await expect(own.getByRole('heading', { name: say(language, 'title') })).toBeVisible();
        await expect(own).toContainText(say(language, 'lead'));
        await expect(own).toContainText(say(language, 'fieldHint'));
        await expect(own.getByTestId('domain-connect')).toContainText(say(language, 'connect'));
      });

      // A domain of ERPlora's never reaches AWS: the field says why.
      await own.getByTestId('domain-input').locator('input').fill('www.erplora.com');
      await own.getByTestId('domain-connect').click();
      await expect(own.getByTestId('domain-input')).toHaveClass(/ion-invalid/);
      await expect(own.getByTestId('domain-input')).toContainText(SERVER[language].ours);
      expect(aws).toEqual([]);

      await own.getByTestId('domain-input').locator('input').fill(domain);
      await own.getByTestId('domain-connect').click();
      await expect(page.getByText(say(language, 'connected', { domain }))).toBeVisible();
      const validation = own.getByTestId('domain-record-validation');
      const traffic = own.getByTestId('domain-record-traffic');
      await atEverySize(page, 'records', language, async () => {
        await expect(own.getByTestId('domain-name')).toHaveText(domain);
        await expect(own.getByTestId('domain-state')).toHaveText(SERVER[language].waiting);
        await expect(own.getByTestId('domain-reason')).toContainText(SERVER[language].certificatePending);
        await expect(validation).toContainText(say(language, 'validation.title'));
        await expect(validation.getByTestId('copy-value')).toHaveText([`_e2e0a1b2c3d4.${domain}`, '_e2e5f6a7b8c9.xlfgrmvvlj.acm-validations.aws']);
        await expect(traffic).toContainText(say(language, 'traffic.title'));
        await expect(traffic.getByTestId('copy-value')).toHaveText([domain, `hub-${id}.erplora.com`]);
        await expect(own.getByTestId('domain-checks')).toHaveText(say(language, 'checks'));
      });
      const asked = aws.find((call) => call.target === 'CertificateManager.RequestCertificate');
      expect(asked?.body).toMatchObject({ DomainName: domain, ValidationMethod: 'DNS', Tags: [{ Key: 'Purpose', Value: 'custom-domain' }] });
      expect((await kept(page, id)).domain).toMatchObject({
        domain,
        state: 'pending',
        reason: 'certificate_pending',
        validation: { name: `_e2e0a1b2c3d4.${domain}`, value: '_e2e5f6a7b8c9.xlfgrmvvlj.acm-validations.aws' },
        traffic: { name: domain, value: `hub-${id}.erplora.com` },
      });

      await traffic.getByTestId('copy-button').last().click();
      await expect(page.getByText(say(language, 'records.copied'), { exact: true })).toBeVisible();
      expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(`hub-${id}.erplora.com`);

      await own.getByTestId('domain-remove').click();
      const dialog = page.getByTestId('domain-remove-dialog');
      await expect(dialog).toContainText(say(language, 'removeMessage', { domain }));
      await dialog.getByTestId('domain-remove-dialog-submit').click();
      await expect(page.getByText(say(language, 'removed', { domain }))).toBeVisible();
      // The removal ends after the COMMIT: the Hub hears of it, ACM deletes the certificate and the name is free.
      await expect(own.getByTestId('domain-form')).toBeVisible();
      await expect(own.getByTestId('domain-input').locator('input')).toHaveValue('');
      expect(aws.map((call) => call.target)).toContain('CertificateManager.DeleteCertificate');
      expect(await kept(page, id)).toEqual({ available: true, in_plan: true, domain: null });
      expect(errors).toEqual([]);
    });

    test(`HUBS-F17 (${language}): a connected domain counts the checks that failed, and one that stopped is asked for again`, async ({ page }) => {
      const errors = watchPageErrors(page);
      const id = await ownerOn(page, language, 'standard');
      // A domain connected two days ago with one failed check: only the hourly check writes one.
      await djangoPrintWarm(
        [
          'from datetime import timedelta',
          'from django.utils import timezone',
          'from hubs.models import CustomDomain',
          'now = timezone.now()',
          `CustomDomain.objects.create(hub_id="${id}", hostname="tienda-${language}.example.net", state="active", reason="cname_missing",`,
          '    certificate_arn="arn:aws:acm:eu-west-1:000000000000:certificate/e2e-seeded", attached_at=now - timedelta(days=2),',
          `    validation_name="_e2eseeded.tienda-${language}.example.net", validation_value="_e2eseeded.acm-validations.aws",`,
          '    proven_at=now - timedelta(days=2), activated_at=now - timedelta(days=2), checked_at=now, failures=1)',
        ].join('\n'),
      );
      await page.goto(`/dashboard/businesses/${id}/settings`);
      const own = card(page);
      await atEverySize(page, 'failing', language, async () => {
        await expect(own.getByTestId('domain-state')).toHaveText(SERVER[language].connected);
        await expect(own.getByTestId('domain-reason')).toContainText(SERVER[language].cnameMissing);
        await expect(own.getByTestId('domain-failures')).toHaveText(say(language, 'failures', { count: 1 }));
        await expect(own.getByTestId('domain-checked-at')).toBeVisible();
        await expect(own.getByTestId('domain-active-since')).toBeVisible();
      });

      // Three in a row: the hourly check took it down, as `check_custom_domains` leaves it; the page reads it again.
      await djangoPrintWarm(
        `from hubs.models import CustomDomain\nCustomDomain.objects.filter(hub_id="${id}").update(state="lapsed", reason="checks_failed", failures=0, proven_at=None, activated_at=None)`,
      );
      await page.reload();
      await atEverySize(page, 'lapsed', language, async () => {
        await expect(own.getByTestId('domain-state')).toHaveText(SERVER[language].notConnected);
        await expect(own.getByTestId('domain-reason')).toContainText(SERVER[language].checksFailed);
        await expect(own.getByTestId('domain-failures')).toHaveCount(0);
        await expect(own.getByTestId('domain-input').locator('input')).toHaveValue(`tienda-${language}.example.net`);
        await expect(own.getByTestId('domain-remove')).toBeVisible();
      });
      expect(errors).toEqual([]);
    });

    test(`HUBS-F17 (${language}): a plan without an own domain says so, names the plan that includes one and leads to the plans, with no form`, async ({ page }) => {
      const errors = watchPageErrors(page);
      const id = await ownerOn(page, language, 'starter');
      await page.goto(`/dashboard/businesses/${id}/settings`);
      const own = card(page);
      const notice = own.getByTestId('domain-not-in-plan');
      const detail = await page.request.get(`/api/hubs/businesses/detail?id=${id}`);
      const plan = ((await detail.json()) as { plan: { name: string } }).plan.name;
      // The plan of the notice is the first on sale whose row includes one (saas#301), as `hubs.plan.list` says.
      const onSale = (await (await page.request.get('/api/plans')).json()) as { plans: { slug: string; name: string; includes_custom_domain: boolean }[] };
      const withIt = onSale.plans.find((candidate) => candidate.includes_custom_domain);
      expect(withIt).toBeDefined();
      await atEverySize(page, 'not-in-plan', language, async () => {
        await expect(notice).toContainText(say(language, 'notInPlan.headingNamed', { plan }));
        await expect(notice).toContainText(say(language, 'notInPlan.bodyNamed', { plan: withIt!.name }));
        await expect(own.getByTestId('domain-form')).toHaveCount(0);
      });
      expect(await kept(page, id)).toMatchObject({ available: true, in_plan: false, domain: null });
      await own.getByTestId('domain-plans').click();
      await expect(page).toHaveURL(new RegExp(`/dashboard/store/plans\\?business=${id}$`));
      // The Store says it on the card of each plan that includes one, and only there.
      const line = catalogueText('billing', language, 'billing.plans.customDomain');
      await expect(page.getByTestId(`plan-${withIt!.slug}`).getByTestId('plan-domain')).toHaveText(line);
      for (const { slug, includes_custom_domain: included } of onSale.plans) {
        const shown = page.getByTestId(`plan-${slug}`);
        if ((await shown.count()) === 0) continue;
        await expect(shown.getByTestId('plan-domain')).toHaveCount(included ? 1 : 0);
      }
      await expect(page.getByTestId('plan-starter').getByTestId('plan-domain')).toHaveCount(0);
      expect(errors).toEqual([]);
    });
  });
}
