import { execFileSync } from 'node:child_process';
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';

import type { Page } from '@playwright/test';

/** Runs the fleet's three-viewport sweep against the live stack, only when explicitly requested. */
export async function uiClipSweep(page: Page, url: string): Promise<void> {
  if (process.env.UI_CLIP_SWEEP !== '1') return;
  const home = process.env.HOME;
  if (!home) throw new Error('UI_CLIP_SWEEP needs HOME for its logs and script');
  const evidence = join(home, '.erplora', 'fleet-next', 'logs', '387', 'ui');
  mkdirSync(evidence, { recursive: true });
  const session = join(evidence, 'storage-state.json');
  await page.context().storageState({ path: session });
  execFileSync(
    'bash',
    [
      join(home, '.erplora', 'fleet-next', 'ui-clip-sweep.sh'),
      '--shots',
      evidence,
      '--storage-state',
      session,
      url,
    ],
    { stdio: 'inherit' },
  );
}
