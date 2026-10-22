// «Report a problem» (`/report-a-problem`, the user menu; ACCOUNTS-F38): «Subject» and «What happened?», «Send report»,
// and «Report sent» with the address support answers to. The account, its businesses, the page the person came from
// and the browser go with it on their own (the screen says so). A refusal keeps what was typed: per field (422) under
// its field, the rest (the limit, a mail that could not leave, no network) above «Send report».
import { afterEach, describe, expect, it } from 'vitest';
import { createWebHistory } from 'vue-router';

import { apiError, flush, ionProps, mountPanel, typeInto } from '../__tests__/mount-panel';
import ReportProblemPage from './ReportProblemPage.vue';

afterEach(() => {
  document.body.innerHTML = '';
});

type Api = Parameters<typeof mountPanel>[1] extends infer O ? (O extends { api?: infer A } ? A : never) : never;

/** The page, opened from `/businesses` (the page the report says the person came from), on the panel's history. */
async function open(api: Api = () => Response.json({ reply_to: 'laura@example.com' }), locale: 'en' | 'es' = 'en') {
  const s = await mountPanel(ReportProblemPage, { path: '/businesses', api, locale, history: createWebHistory() });
  await s.router.push('/report-a-problem');
  await flush();
  return s;
}

async function fill(s: Awaited<ReturnType<typeof open>>, subject = 'The printer stops', description = 'Nothing prints.') {
  await typeInto(s.q('report-subject'), subject);
  await typeInto(s.q('report-description'), description);
}

describe('ReportProblemPage', () => {
  it('asks for a subject and what happened, and says what goes with the report', async () => {
    const s = await open();

    expect(document.querySelector('ion-title')?.textContent?.trim()).toBe('Report a problem');
    expect(s.q('report-intro')?.textContent?.trim()).toBe('Tell us what went wrong. We will reply by email.');
    expect(ionProps(s.q('report-subject'), 'label', 'mode', 'fill', 'maxlength')).toEqual({
      label: 'Subject',
      mode: 'md',
      fill: 'outline',
      maxlength: 150,
    });
    expect(ionProps(s.q('report-description'), 'label', 'placeholder', 'mode', 'fill', 'maxlength')).toEqual({
      label: 'What happened?',
      placeholder: 'Describe the steps and what you expected to happen',
      mode: 'md',
      fill: 'outline',
      maxlength: 5000,
    });
    expect(s.q('report-context')?.textContent?.trim()).toBe(
      'Your account, your businesses, the page you came from and your browser go with your report.',
    );
  });

  it('waits for both fields before «Send report»', async () => {
    const s = await open();
    expect(ionProps(s.q('report-send'), 'disabled')).toEqual({ disabled: true });

    await typeInto(s.q('report-subject'), 'The printer stops');
    expect(ionProps(s.q('report-send'), 'disabled')).toEqual({ disabled: true });
    await typeInto(s.q('report-description'), '   ');
    expect(ionProps(s.q('report-send'), 'disabled')).toEqual({ disabled: true });
    await typeInto(s.q('report-description'), 'Nothing prints.');
    expect(ionProps(s.q('report-send'), 'disabled')).toEqual({ disabled: false });
  });

  it('sends the report with the page it came from and shows «Report sent» with the address support answers to', async () => {
    const s = await open();
    await fill(s, '  The printer stops ', ' Nothing prints. ');

    s.q('report-send')?.click();
    await flush();

    expect(s.calls()).toEqual([
      {
        method: 'POST',
        path: '/api/accounts/support/report',
        body: { subject: 'The printer stops', description: 'Nothing prints.', page: '/businesses' },
      },
    ]);
    expect(s.q('report-subject')).toBeNull();
    expect(s.q('report-sent')?.textContent).toContain('Report sent');
    expect(s.q('report-sent')?.textContent).toContain(
      'Thank you: we have received your report and will reply to laura@example.com as soon as possible.',
    );
  });

  it('«Back» after sending returns to where the person came from', async () => {
    const s = await open();
    await fill(s);
    s.q('report-send')?.click();
    await flush();

    s.q('report-back')?.click();
    await flush();
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(s.router.currentRoute.value.path).toBe('/businesses');
  });

  it('a field refused by the server is said under it, and what was typed stays', async () => {
    const s = await open(() => apiError(422, 'invalid_payload', 'Invalid payload', { fields: { subject: 'Add a subject.' } }));
    await fill(s);

    s.q('report-send')?.click();
    await flush();

    expect(ionProps(s.q('report-subject'), 'errorText', 'value')).toEqual({
      errorText: 'Add a subject.',
      value: 'The printer stops',
    });
    expect(s.q('report-error')).toBeNull();
  });

  it.each([
    [503, 'accounts.report_not_sent', 'We could not send your report. Write to us directly at support@erplora.com.'],
    [429, 'accounts.too_many_attempts', 'Too many attempts. Please try again in a few minutes.'],
  ])('a %s is said above «Send report» and the report can be sent again', async (status, code, message) => {
    const s = await open(() => apiError(status, code, message));
    await fill(s);

    s.q('report-send')?.click();
    await flush();

    expect(s.q('report-error')?.textContent).toContain(message);
    expect(ionProps(s.q('report-description'), 'value')).toEqual({ value: 'Nothing prints.' });
    expect(ionProps(s.q('report-send'), 'disabled')).toEqual({ disabled: false });
    expect(s.q('report-sent')).toBeNull();
  });

  it('without network it says so in the panel\'s words', async () => {
    const s = await open(() => {
      throw new TypeError('Failed to fetch');
    });
    await fill(s);

    s.q('report-send')?.click();
    await flush();

    expect(s.q('report-error')?.textContent?.trim()).not.toBe('');
    expect(s.q('report-error')?.textContent).not.toContain('Failed to fetch');
  });

  it('speaks Spanish', async () => {
    const s = await open(undefined, 'es');

    expect(document.querySelector('ion-title')?.textContent?.trim()).toBe('Reportar un problema');
    expect(ionProps(s.q('report-subject'), 'label')).toEqual({ label: 'Asunto' });
    expect(ionProps(s.q('report-description'), 'label', 'placeholder')).toEqual({
      label: '¿Qué pasó?',
      placeholder: 'Describe los pasos y lo que esperabas que pasara',
    });
    expect(s.q('report-send')?.textContent?.trim()).toBe('Enviar informe');
  });
});
