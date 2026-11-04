// Runs before every test file of the SaaS (`vite.config.ts`, `test.setupFiles`): happy-dom made to behave
// as a browser where Ionic's runtime reaches it (`@erplora/ui/testing`, `fillHappyDomGaps`), so its
// elements connect without Stencil logging a TypeError that buries the real failures. And nothing a test mounted
// outlives it (`frontend/test-run.test.ts`).
import { fillHappyDomGaps } from '@erplora/ui/testing';
import { enableAutoUnmount } from '@vue/test-utils';
import { afterEach } from 'vitest';

fillHappyDomGaps();
enableAutoUnmount(afterEach);
