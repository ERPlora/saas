// The AI gateway in erplora.com's admin (MIGRATION-TASK APP-ASSISTANT-1; assistant/WORKBOOK.md), at the three sizes
// of the migration (390×844, 834×1112, 1440×900), in English and in Spanish, against the panel's own Django and the
// rows of assistant_seed.py. The provider is assistant.tests.fake_provider, a real HTTP server on 127.0.0.1 that
// speaks OpenAI's API (two chat models, one embeddings model, an answer streamed in three pieces): no test reaches a
// real provider and no real key is ever typed.
// flow: ASSISTANT-F01 — the staff add a provider with its API and its address.
// flow: ASSISTANT-F02 — its key is typed once, kept encrypted and never shown again: only its last four characters.
// flow: ASSISTANT-F04 — the staff choose the provider's models from the list its API gives.
// flow: ASSISTANT-F05 — the staff choose which model answers and its fallback.
// flow: ASSISTANT-F07 — the staff try a model and watch its answer arrive with its tokens, time and cost.
import { type ChildProcess, execFileSync, spawn } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import type { Page } from '@playwright/test';

import { djangoEnv } from '../django-env';
import { STACK } from '../stack';
import { expect, settled, shot, sidewaysScroll, signIn, test, watchPageErrors } from './fixtures';

const SAAS_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const PASSWORD = process.env.QA_PANEL_PASSWORD ?? 'e2e-panel';
const ADMIN = { email: 'e2e-assistant-admin@example.com', password: PASSWORD };
const VIEWER = { email: 'e2e-assistant-viewer@example.com', password: PASSWORD };
// The provider's own port in the run's block (stack.ts): +8 is reCAPTCHA's double since saas#88.
const PROVIDER_PORT = STACK.aiProviderPort;
const PROVIDER_URL = `http://127.0.0.1:${PROVIDER_PORT}/v1`;
const API_KEY = 'sk-e2e-0000000000000000000000000000e2e1';
const SIZES = [
  { name: '390', width: 390, height: 844 },
  { name: '834', width: 834, height: 1112 },
  { name: '1440', width: 1440, height: 900 },
] as const;

let provider: ChildProcess | undefined;

/** `assistant_seed.py <action> <provider address>`: always from scratch. */
function seed(action: 'clear' | 'staff' | 'provider' | 'models'): void {
  execFileSync('uv', ['run', 'python', 'tests/e2e/panel/assistant_seed.py', action, PROVIDER_URL], {
    cwd: SAAS_DIR,
    env: djangoEnv(true),
    stdio: 'pipe',
  });
}

test.beforeAll(async () => {
  provider = spawn('uv', ['run', 'python', '-m', 'assistant.tests.fake_provider', '--port', String(PROVIDER_PORT)], {
    cwd: SAAS_DIR,
    env: djangoEnv(true),
    stdio: 'ignore',
  });
  await expect
    .poll(
      async () => {
        try {
          return (await fetch(`${PROVIDER_URL}/models`)).status;
        } catch {
          return 0;
        }
      },
      { timeout: 30_000, message: `the fake provider on :${PROVIDER_PORT}` },
    )
    .toBe(200);
});

test.afterAll(() => {
  seed('clear');
  provider?.kill();
});

/** `ready` at each size: no sideways scroll, a capture `APP-ASSISTANT-1-<key>-<size>`; back at 1440 after. */
async function atEverySize(page: Page, key: string, ready: () => Promise<void>): Promise<void> {
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await ready();
    await settled(page);
    expect(await sidewaysScroll(page), `${key} at ${size.name}`).toEqual([]);
    await page.screenshot({ path: shot(`APP-ASSISTANT-1-${key}-${size.name}`), fullPage: true });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}

test('ASSISTANT-F01 · ASSISTANT-F02: the staff add a provider with its key, which is never shown again', async ({ page }) => {
  const errors = watchPageErrors(page);
  seed('staff');
  await signIn(page.request, ADMIN);

  await page.goto('/admin/assistant/aiprovider/add/');
  await page.getByLabel('Name:').fill('E2E Local');
  await page.getByLabel('Identifier:').fill('e2e-local');
  await page.getByLabel('API:').selectOption('openai');
  await page.getByLabel('Address:').fill('http://example.com/v1');
  // Django 6.1 paints the inline's «Add another» as a button.
  await page.getByRole('button', { name: 'Add another Key' }).click();
  await page.locator('[name="credentials-0-new_key"]').fill(API_KEY);
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  // The key travels to the address: plain http only to this machine.
  await expect(page.locator('.errorlist')).toContainText("Use an https address: the provider's key travels to it.");

  await page.getByLabel('Address:').fill(PROVIDER_URL);
  await page.locator('[name="credentials-0-new_key"]').fill(API_KEY);
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(page.locator('.messagelist')).toContainText('was added successfully');
  const row = page.getByRole('row', { name: /E2E Local/ });
  await atEverySize(page, 'ASSISTANT-F01', async () => {
    await expect(row).toContainText('…e2e1');
  });

  await row.getByRole('link', { name: 'E2E Local' }).click();
  const typed = page.locator('[name="credentials-0-new_key"]');
  await atEverySize(page, 'ASSISTANT-F02', async () => {
    await expect(page.getByRole('cell', { name: '…e2e1', exact: true })).toBeVisible();
    await expect(typed).toHaveValue('');
  });
  expect(await page.content()).not.toContain(API_KEY);
  expect(errors).toEqual([]);
});

test('ASSISTANT-F04: the staff choose the provider\'s models from the list its API gives', async ({ page }) => {
  const errors = watchPageErrors(page);
  seed('provider');
  await signIn(page.request, ADMIN);

  await page.goto('/admin/assistant/aiprovider/');
  await page.getByRole('link', { name: 'E2E Local' }).click();
  await page.getByRole('link', { name: 'Choose models from the provider' }).click();
  const large = page.getByLabel('gpt-e2e-large');
  await atEverySize(page, 'ASSISTANT-F04', async () => {
    await expect(large).toBeVisible();
    await expect(page.getByLabel('gpt-e2e-mini')).toBeVisible();
  });
  // The provider's embeddings model is not a chat model.
  await expect(page.getByText('text-embedding-e2e')).toHaveCount(0);

  await large.check();
  await page.getByRole('button', { name: 'Save the choice' }).click();
  await expect(page.locator('.messagelist')).toContainText('E2E Local: 1 new, 0 kept, 0 removed, 0 in use by the policy.');
  await expect(page.locator('[name="models-0-model_id"]')).toHaveValue('gpt-e2e-large');
  expect(errors).toEqual([]);
});

test('ASSISTANT-F05: the staff choose which model answers and its fallback', async ({ page }) => {
  const errors = watchPageErrors(page);
  seed('models');
  await signIn(page.request, ADMIN);

  await page.goto('/admin/assistant/airoutingpolicy/');
  await page.getByLabel('Model that answers').selectOption({ label: 'E2E Local · Large (gpt-e2e-large)' });
  await page.getByLabel('Fallback model').selectOption({ label: 'E2E Local · Mini (gpt-e2e-mini)' });
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(page.locator('.messagelist')).toContainText('The model that answers was saved.');
  await atEverySize(page, 'ASSISTANT-F05', async () => {
    await expect(page.getByLabel('Model that answers')).toHaveValue(/.+/);
    await expect(page.getByRole('link', { name: 'Try a model' })).toBeVisible();
  });
  expect(errors).toEqual([]);
});

test('ASSISTANT-F07: the staff try a model and watch its answer with its tokens, time and cost', async ({ page }) => {
  const errors = watchPageErrors(page);
  seed('models');
  await signIn(page.request, ADMIN);

  await page.goto('/admin/assistant/airoutingpolicy/');
  await page.getByRole('link', { name: 'Try a model' }).click();
  await expect(page.getByRole('heading', { name: 'Try a model' })).toBeVisible();

  // Badly written tools are refused before the provider is called.
  await page.getByLabel('Model').selectOption({ label: 'E2E Local · Large (gpt-e2e-large)' });
  await page.getByLabel('Message').fill('Say hello');
  await page.getByLabel('Tools').fill('not a list');
  await page.getByRole('button', { name: 'Send' }).click();
  await expect(page.locator('#try-error')).toHaveText(
    'The tools are not well written: write a list of tools as in the example, each with its name.',
  );

  await page.getByLabel('Tools').fill('');
  await page.getByRole('button', { name: 'Send' }).click();
  await expect(page.locator('#try-answer')).toHaveText('Hello from the test model.');
  await expect(page.locator('#try-status')).toHaveText('Done.');
  await expect(page.locator('#try-model-name')).toHaveText('E2E Local · Large (gpt-e2e-large)');
  await expect(page.locator('[data-metric="input_tokens"]')).toHaveText('1200');
  await expect(page.locator('[data-metric="output_tokens"]')).toHaveText('300');
  // (1200 × 1 + 300 × 2) / 1 000 000 USD.
  await expect(page.locator('[data-metric="cost_usd"]')).toHaveText('0.0018 USD');
  await expect(page.locator('[data-metric="latency_ms"]')).toHaveText(/^\d+ ms$/);
  await expect(page.locator('#try-error')).toBeHidden();
  await atEverySize(page, 'ASSISTANT-F07', async () => {
    await expect(page.locator('#try-metrics')).toBeVisible();
  });
  expect(errors).toEqual([]);
});

test('ASSISTANT-F07: the staff who may only look are not led to try a model and cannot', async ({ page }) => {
  seed('models');
  await signIn(page.request, VIEWER);

  await page.goto('/admin/assistant/airoutingpolicy/policy/');
  await expect(page.getByLabel('Model that answers')).toBeDisabled();
  await expect(page.getByRole('link', { name: 'Try a model' })).toHaveCount(0);
  expect((await page.goto('/admin/assistant/airoutingpolicy/policy/try/'))?.status()).toBe(403);
});

test.describe('in Spanish', () => {
  test.use({ locale: 'es-ES' });

  test('ASSISTANT-F01 · ASSISTANT-F05 · ASSISTANT-F07: the gateway\'s pages speak the staff\'s language', async ({ page }) => {
    const errors = watchPageErrors(page);
    seed('models');
    await signIn(page.request, ADMIN);

    await page.goto('/admin/assistant/aiprovider/');
    const row = page.getByRole('row', { name: /E2E Local/ });
    await atEverySize(page, 'ASSISTANT-F01-es', async () => {
      await expect(row).toContainText('…e2e1');
      await expect(page.getByRole('heading', { name: /proveedor de IA/ })).toBeVisible();
    });

    await page.goto('/admin/assistant/airoutingpolicy/policy/');
    await atEverySize(page, 'ASSISTANT-F05-es', async () => {
      await expect(page.getByLabel('Modelo que contesta')).toBeVisible();
      await expect(page.getByRole('link', { name: 'Probar un modelo' })).toBeVisible();
    });

    await page.getByRole('link', { name: 'Probar un modelo' }).click();
    await page.getByLabel('Mensaje').fill('Saluda');
    await page.getByRole('button', { name: 'Enviar' }).click();
    await expect(page.locator('#try-status')).toHaveText('Hecho.');
    await atEverySize(page, 'ASSISTANT-F07-es', async () => {
      await expect(page.getByRole('heading', { name: 'Respuesta' })).toBeVisible();
      await expect(page.getByRole('rowheader', { name: 'Tokens de entrada' })).toBeVisible();
    });
    expect(errors).toEqual([]);
  });
});
