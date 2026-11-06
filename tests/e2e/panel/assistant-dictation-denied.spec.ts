// A microphone the browser refuses, in the panel's assistant (assistant/WORKBOOK.md, ASSISTANT-F21): it says where to allow
// it again, and nothing is recorded. Chrome itself refuses: its fake media prompt answers «Block», a launch option, so a
// file of its own (assistant-dictation.spec.ts needs the prompt that accepts).
// flow: ASSISTANT-F21 — dictate to the assistant.
import { openPanel } from './assistant-chat';
import { expect, runSeed, settled, shot, test } from './fixtures';

const seed = (action: 'clear' | 'panel') => runSeed('assistant_seed.py', [action, 'http://127.0.0.1:9/v1', 'en']);

test.use({
  launchOptions: { args: ['--use-fake-ui-for-media-stream=deny', '--use-fake-device-for-media-stream'] },
});

test.afterAll(() => {
  seed('clear');
});

test('a microphone the browser refuses says where to allow it, and nothing is recorded', async ({ page }) => {
  seed('panel');
  const panel = await openPanel(page);
  const mic = panel.getByTestId('assistant-mic');

  await mic.click();

  await expect(panel.getByTestId('assistant-composer-problem')).toHaveText(
    'Microphone access is blocked. Allow it in your browser to dictate.',
  );
  await expect(mic).not.toHaveAttribute('aria-pressed', 'true');
  await settled(page);
  await page.screenshot({ path: shot('assistant-dictation-denied') });
});
