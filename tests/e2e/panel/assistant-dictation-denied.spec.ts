// A microphone the browser refuses, in the panel's assistant (assistant/WORKBOOK.md, ASSISTANT-F21): it says where to allow
// it again, and nothing is recorded. Chrome itself refuses: its fake media prompt answers «Block», a launch option, so a
// file of its own (assistant-dictation.spec.ts needs the prompt that accepts).
// flow: ASSISTANT-F21 — dictate to the assistant.
import { execFileSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { djangoEnv } from '../django-env';
import { expect, settled, shot, signIn, test } from './fixtures';

const SAAS_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const OWNER = { email: 'e2e-assistant-owner@example.com', password: process.env.QA_PANEL_PASSWORD ?? 'e2e-panel' };

function seed(action: 'clear' | 'panel'): void {
  execFileSync('uv', ['run', 'python', 'tests/e2e/panel/assistant_seed.py', action, 'http://127.0.0.1:9/v1', 'en'], {
    cwd: SAAS_DIR,
    env: djangoEnv(true),
    stdio: 'pipe',
  });
}

test.use({
  launchOptions: { args: ['--use-fake-ui-for-media-stream=deny', '--use-fake-device-for-media-stream'] },
});

test.afterAll(() => {
  seed('clear');
});

test('a microphone the browser refuses says where to allow it, and nothing is recorded', async ({ page }) => {
  seed('panel');
  await signIn(page.request, OWNER);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/dashboard/businesses');
  await page.getByTestId('assistant-button').click();
  const panel = page.getByTestId('assistant-panel');
  const mic = panel.getByTestId('assistant-mic');

  await mic.click();

  await expect(panel.getByTestId('assistant-composer-problem')).toHaveText(
    'Microphone access is blocked. Allow it in your browser to dictate.',
  );
  await expect(mic).toHaveAttribute('aria-pressed', 'false');
  await settled(page);
  await page.screenshot({ path: shot('assistant-dictation-denied') });
});
