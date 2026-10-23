// `test` of the public project's specs: Playwright's, with Google's reCAPTCHA played in every context
// (`fakeGoogleRecaptcha`, a person's tokens): the public server checks every form with reCAPTCHA, as production does,
// and asks the run's double about the tokens (recaptcha.ts). A spec that needs a bot or Google blocked calls
// `fakeGoogleRecaptcha(context, …)` again.
import { test as base } from '@playwright/test';

import { fakeGoogleRecaptcha } from './recaptcha';

export const test = base.extend<{ googleRecaptcha: void }>({
  googleRecaptcha: [
    async ({ context }, use) => {
      await fakeGoogleRecaptcha(context);
      await use();
    },
    { auto: true },
  ],
});

export { expect } from '@playwright/test';
