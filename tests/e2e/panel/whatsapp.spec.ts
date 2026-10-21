// flow: WHATSAPP-G13, WHATSAPP-G07 — Meta's webhook on the panel's real Django, end to end over HTTP: Meta's
// verification of the address (its token and its challenge), then a customer's message, signed as Meta signs it,
// handed to the Hub through door 1 (`POST /internal/whatsapp/inbound`), signed as every internal call, with the
// contract's body. The spec plays Meta (it signs with the e2e app's secret, project.ts `WHATSAPP_E2E`) and the Hub
// (`startHubDouble`); Meta itself is never called. No screen: erplora.com has no WhatsApp page (PLAN-SAAS block 12).
// The cross e2e with the real Hub's inbox (Meta → erplora.com → the Hub's «WhatsApp inbox») is whatsapp-hub.spec.ts.
import { execFileSync } from 'node:child_process';
import { createHmac } from 'node:crypto';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { djangoEnv } from '../django-env';
import { expect, type HubCall, startHubDouble, test } from './fixtures';
import { WHATSAPP_E2E } from './project';

const SAAS_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const WEBHOOK = '/webhooks/whatsapp/';
/** whatsapp_seed.py's business and number. */
const SLUG = 'e2e-whatsapp-bar';
const NUMBER_ID = '880000000000001';

function seedWhatsapp(action: 'seed' | 'clear'): void {
  execFileSync('uv', ['run', 'python', 'tests/e2e/panel/whatsapp_seed.py', action], {
    cwd: SAAS_DIR,
    env: djangoEnv(true),
    stdio: 'pipe',
  });
}

/** A text message of a customer, as Meta's webhook carries it. */
function customerWrites(wamid: string, text: string): string {
  return JSON.stringify({
    object: 'whatsapp_business_account',
    entry: [
      {
        id: '880000000000000',
        changes: [
          {
            field: 'messages',
            value: {
              messaging_product: 'whatsapp',
              metadata: { display_phone_number: '34910000000', phone_number_id: NUMBER_ID },
              contacts: [{ profile: { name: 'Ana' }, wa_id: '34600111222' }],
              messages: [
                { from: '34600111222', id: wamid, timestamp: String(Math.floor(Date.now() / 1000)), type: 'text', text: { body: text } },
              ],
            },
          },
        ],
      },
    ],
  });
}

function metaSignature(body: string, secret: string = WHATSAPP_E2E.appSecret): string {
  return `sha256=${createHmac('sha256', secret).update(body).digest('hex')}`;
}

test.describe('WhatsApp: Meta’s webhook reaches the Hub', () => {
  test.beforeAll(() => seedWhatsapp('seed'));
  test.afterAll(() => seedWhatsapp('clear'));

  test('WHATSAPP-G13: Meta confirms the address with our token, never with another', async ({ request }) => {
    const ok = await request.get(WEBHOOK, {
      params: { 'hub.mode': 'subscribe', 'hub.verify_token': WHATSAPP_E2E.verifyToken, 'hub.challenge': '1158201444' },
    });
    expect(ok.status()).toBe(200);
    expect(await ok.text()).toBe('1158201444');

    const wrong = await request.get(WEBHOOK, {
      params: { 'hub.mode': 'subscribe', 'hub.verify_token': 'not-ours', 'hub.challenge': '1158201444' },
    });
    expect(wrong.status()).toBe(403);
  });

  test('WHATSAPP-G07: a customer’s message, signed by Meta, is handed to the Hub signed and as the contract says', async ({
    request,
  }) => {
    const hub = await startHubDouble();
    try {
      const unsigned = customerWrites('wamid.E2E-FORGED', 'Forged');
      const forged = await request.post(WEBHOOK, {
        data: unsigned,
        headers: { 'Content-Type': 'application/json', 'X-Hub-Signature-256': metaSignature(unsigned, 'another-secret') },
      });
      expect(forged.status()).toBe(403);

      const body = customerWrites('wamid.E2E-1', 'Hola, ¿tenéis mesa para dos?');
      const notice = await request.post(WEBHOOK, {
        data: body,
        headers: { 'Content-Type': 'application/json', 'X-Hub-Signature-256': metaSignature(body) },
      });
      expect(notice.status()).toBe(200);

      const inbound = (call: HubCall) => call.method === 'POST' && call.path === '/internal/whatsapp/inbound';
      await expect.poll(() => hub.calls.filter(inbound).length).toBe(1);
      const [delivered] = hub.calls.filter(inbound);
      expect(delivered.signed).toBe(true);
      expect(delivered.body).toMatchObject({
        hub: SLUG,
        wa_message_id: 'wamid.E2E-1',
        from: '34600111222',
        contact_name: 'Ana',
        direction: 'inbound',
        source: 'live',
        type: 'text',
        text: 'Hola, ¿tenéis mesa para dos?',
      });
      expect(hub.calls.some((call) => JSON.stringify(call.body).includes('E2E-FORGED'))).toBe(false);
    } finally {
      await hub.close();
    }
  });
});
