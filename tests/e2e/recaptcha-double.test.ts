// @vitest-environment node
// The e2e's Google of reCAPTCHA Enterprise's assessments (recaptcha-double.ts): the public server asks it instead
// of Google (`RECAPTCHA_ENDPOINT`), so no run depends on Google's scoring of a headless Chrome. It reads the e2e
// tokens the fake enterprise.js gives (recaptcha.ts): `e2e-human:<action>` is a person (0.9), `e2e-bot:<action>`
// a bot (0.1); anything else is malformed. It keeps what it was asked (`GET /assessments`).
import { afterEach, describe, expect, it } from 'vitest';

import { assessmentOf, type RecaptchaDouble, startRecaptchaDouble } from './recaptcha-double';

describe('assessmentOf', () => {
  it('reads a person’s token of the action', () => {
    expect(assessmentOf({ token: 'e2e-human:login', expectedAction: 'login' })).toEqual({
      tokenProperties: { valid: true, action: 'login', hostname: 'localhost' },
      riskAnalysis: { score: 0.9, reasons: [] },
    });
  });

  it('reads a bot’s token', () => {
    expect(assessmentOf({ token: 'e2e-bot:contact', expectedAction: 'contact' }).riskAnalysis).toEqual({
      score: 0.1,
      reasons: ['AUTOMATION'],
    });
  });

  it('keeps the action the token was made for, whatever was expected', () => {
    expect(assessmentOf({ token: 'e2e-human:signup', expectedAction: 'login' }).tokenProperties.action).toBe('signup');
  });

  it.each([['forged'], [''], ['e2e-robot:login']])('calls %j malformed', (token) => {
    expect(assessmentOf({ token, expectedAction: 'login' })).toEqual({
      tokenProperties: { valid: false, invalidReason: 'MALFORMED' },
      riskAnalysis: { score: 0, reasons: [] },
    });
  });
});

describe('startRecaptchaDouble', () => {
  let double: RecaptchaDouble | undefined;

  afterEach(async () => {
    await double?.close();
    double = undefined;
  });

  it('answers the assessments as Google’s REST API does, keeps them, and says it is up', async () => {
    double = await startRecaptchaDouble(0);
    const base = `http://127.0.0.1:${double.port}`;

    const answer = await fetch(`${base}/v1/projects/erplora/assessments?key=e2e-api-key`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ event: { token: 'e2e-human:contact', siteKey: 'k', expectedAction: 'contact' } }),
    });

    expect(answer.status).toBe(200);
    expect(((await answer.json()) as { tokenProperties: { valid: boolean } }).tokenProperties.valid).toBe(true);
    expect(await (await fetch(`${base}/assessments`)).json()).toEqual([{ token: 'e2e-human:contact', expectedAction: 'contact' }]);
    expect((await fetch(`${base}/healthz`)).status).toBe(200);
  });

  it('answers 400 to a body that is no assessment, and 404 elsewhere', async () => {
    double = await startRecaptchaDouble(0);
    const base = `http://127.0.0.1:${double.port}`;

    const junk = await fetch(`${base}/v1/projects/erplora/assessments`, { method: 'POST', body: 'not json' });
    const elsewhere = await fetch(`${base}/somewhere`);

    expect([junk.status, elsewhere.status]).toEqual([400, 404]);
  });
});
