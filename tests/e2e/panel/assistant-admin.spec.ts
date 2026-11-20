// The AI gateway in erplora.com's admin (assistant/WORKBOOK.md), at the three sizes
// (390×844, 834×1112, 1440×900), in English and in Spanish, against the panel's own Django and the
// rows of assistant_seed.py. The provider is assistant.tests.fake_provider, a real HTTP server on 127.0.0.1 that
// speaks OpenAI's API (two chat models, one embeddings model, an answer streamed in three pieces): no test reaches a
// real provider, and the only key is the made-up one the e2e gives the panel's Django (E2E_AI_KEY, panel/project.ts).
// flow: ASSISTANT-F01 — the staff add a provider with its API, its address and the variable of its key.
// flow: ASSISTANT-F02 — its key lives in the environment: the pages say whether it is there, never any part of it.
// flow: ASSISTANT-F04 — the staff choose the provider's models from the list its API gives.
// flow: ASSISTANT-F05 — the staff choose which model answers and its fallback.
// flow: ASSISTANT-F07 — the staff try a model and watch its answer arrive with its tokens, time and cost.
import type { ChildProcess } from 'node:child_process';

import { FAKE_PROVIDER_URL, startFakeProvider } from './assistant-chat';
import { runSeed } from './django';
import { expect, test } from './fixtures';
import { watchPageErrors } from './page-events';
import { E2E_AI_KEY } from './project';
import { captureAtEverySize } from './screen';
import { signIn } from './session';

const atEverySize = captureAtEverySize('APP-ASSISTANT-1');

const PASSWORD = process.env.QA_PANEL_PASSWORD ?? 'e2e-panel';
const ADMIN = { email: 'e2e-assistant-admin@example.com', password: PASSWORD };
const VIEWER = { email: 'e2e-assistant-viewer@example.com', password: PASSWORD };

let provider: ChildProcess | undefined;

/** `assistant_seed.py <action> <provider address>`: always from scratch. */
const seed = (action: 'clear' | 'staff' | 'provider' | 'models') => runSeed('assistant_seed.py', [action, FAKE_PROVIDER_URL]);

test.beforeAll(async () => {
  provider = await startFakeProvider();
});

test.afterAll(() => {
  seed('clear');
  provider?.kill();
});

test('ASSISTANT-F01 · ASSISTANT-F02: the staff add a provider naming the variable of its key, never shown', async ({ page }) => {
  const errors = watchPageErrors(page);
  seed('staff');
  await signIn(page.request, ADMIN);

  await page.goto('/admin/assistant/aiprovider/add/');
  await expect(page.locator('input[type="password"]')).toHaveCount(0);
  await page.getByLabel('Name:').fill('E2E Local');
  await page.getByLabel('Identifier:').fill('e2e-local');
  await page.getByLabel('API:').selectOption('openai');
  await page.getByLabel('Address:').fill('http://example.com/v1');
  await page.getByLabel('Key variable:').selectOption('OPENAI_API_KEY');
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  // The key travels to the address: plain http only to this machine.
  await expect(page.locator('.errorlist')).toContainText("Use an https address: the provider's key travels to it.");

  await page.getByLabel('Address:').fill(FAKE_PROVIDER_URL);
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(page.locator('.messagelist')).toContainText('was added successfully');
  const row = page.getByRole('row', { name: /E2E Local/ });
  await atEverySize(page, 'ASSISTANT-F01', async () => {
    await expect(row).toContainText('OPENAI_API_KEY');
    await expect(row).toContainText('In the environment');
  });

  await row.getByRole('link', { name: 'E2E Local' }).click();
  await atEverySize(page, 'ASSISTANT-F02', async () => {
    await expect(page.getByLabel('Key variable:')).toHaveValue('OPENAI_API_KEY');
    await expect(page.getByText('In the environment', { exact: true })).toBeVisible();
  });
  await expect(page.locator('input[type="password"]')).toHaveCount(0);
  const html = await page.content();
  expect(html).not.toContain(E2E_AI_KEY);
  expect(html).not.toContain(E2E_AI_KEY.slice(-4));
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
      await expect(row).toContainText('En el entorno');
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
