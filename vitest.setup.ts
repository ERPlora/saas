// Runs before every test file of the SaaS (`vite.config.ts`, `test.setupFiles`): happy-dom made to behave
// as a browser where Ionic's runtime reaches it (`@erplora/ui/testing`, `fillHappyDomGaps`), so its
// elements connect without Stencil logging a TypeError that buries the real failures.
import { fillHappyDomGaps } from '@erplora/ui/testing';

fillHappyDomGaps();
