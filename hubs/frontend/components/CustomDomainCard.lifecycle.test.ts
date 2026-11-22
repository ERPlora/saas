// «Own domain» once a business has one: its state and where it is stuck in the server's words, the two records with
// «Copy», the hourly check that stops serving it, removing it and the colour of each state.
// clock: data only — no code under test compares these dates with now.
import { InlineFeedback, StatusPill } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@ionic/vue', async (original) => (await import('../__tests__/module-mocks')).ionicWithModalStub(original));
vi.mock('@erplora/ui/shell', async (original) => (await import('../__tests__/module-mocks')).shellWithToastSpies(original));

import { toastSuccess } from '@erplora/ui/shell';

import { ACTIVE, NONE, PENDING, setup, setUpCustomDomainCard, status } from '../__tests__/custom-domain-card';
import { accessibleName, apiError, flush, ionProps, stubClipboard } from '../__tests__/mount-hubs';

setUpCustomDomainCard();

describe('CustomDomainCard: a domain on its way', () => {
  it('its state and where it is stuck, in the server’s words, and the two records in order with «Copy»', async () => {
    const s = await setup(status(PENDING));
    expect(s.testid('domain-name').text()).toBe('www.minegocio.es');
    expect(s.testid('domain-state').text()).toBe('Waiting for your records');
    expect(s.testid('domain-reason').text()).toContain('Create the validation record: the certificate is waiting for it.');
    const validation = s.testid('domain-record-validation');
    expect(validation.text()).toContain('1. Validation record');
    expect(validation.text()).toContain('Create it first and keep it for good: it renews the certificate.');
    expect(validation.findAll('[data-testid="copy-value"]').map((v) => v.text())).toEqual([
      '_3639ac514e78.www.minegocio.es',
      '_98d2646601fa.xlfgrmvvlj.acm-validations.aws',
    ]);
    const traffic = s.testid('domain-record-traffic');
    expect(traffic.text()).toContain('2. Record that points to ERPlora');
    expect(traffic.text()).toContain('Create it once the certificate is ready');
    expect(traffic.findAll('[data-testid="copy-value"]').map((v) => v.text())).toEqual(['www.minegocio.es', 'hub-h1.erplora.com']);
    expect(s.wrapper.findAll('[data-testid="domain-record-type"]').map((t) => t.text())).toEqual(['CNAME', 'CNAME']);
    expect(s.testid('domain-checks').text()).toContain(
      'If it stops pointing to ERPlora three times in a row, we stop serving your website on it and email you',
    );
  });

  it('each «Copy» copies its own value and says it was copied', async () => {
    const writeText = vi.fn(() => Promise.resolve());
    stubClipboard(writeText);
    const s = await setup(status(PENDING));
    const buttons = s.testid('domain-record-validation').findAll('[data-testid="copy-button"]');
    expect(buttons.map((b) => accessibleName(b))).toEqual(['Copy the name', 'Copy the value']);
    await buttons[1].trigger('click');
    await flush();
    expect(writeText).toHaveBeenCalledWith('_98d2646601fa.xlfgrmvvlj.acm-validations.aws');
    expect(toastSuccess).toHaveBeenCalledWith('Copied');
  });

  it('a validation record ACM has not given yet is on its way; «Look again» asks again', async () => {
    const s = await setup(status({ ...PENDING, validation: null }));
    expect(s.testid('domain-validation-coming').text()).toContain('It is still being prepared and appears here in a few seconds.');
    expect(s.testid('domain-record-validation').findAll('[data-testid="copy-value"]')).toHaveLength(0);
    await s.testid('domain-look-again').trigger('click');
    await flush();
    expect(s.net.streams).toHaveLength(2);
  });

  it('the last check is dated', async () => {
    const s = await setup(status({ ...PENDING, checked_at: '2026-11-05T09:00:00Z' }));
    expect(s.testid('domain-checked-at').text()).toMatch(/^Last check: Nov 5, 2026/);
  });
});

describe('CustomDomainCard: a connected domain', () => {
  it('says it is served there and since when; no failure, no warning of one', async () => {
    const s = await setup(status(ACTIVE));
    expect(s.testid('domain-state').text()).toBe('Connected');
    expect(s.testid('domain-reason').text()).toContain('Your website is served on www.minegocio.es.');
    expect(s.testid('domain-active-since').text()).toMatch(/^Connected since Nov 4, 2026/);
    expect(s.testid('domain-failures').exists()).toBe(false);
    expect(s.testid('domain-record-traffic').exists()).toBe(true);
  });

  it('a check that failed is counted against the three that stop it', async () => {
    const one = await setup(status({ ...ACTIVE, failures: 1, reason: 'cname_missing', reason_label: 'Create the record that points your domain at ERPlora.' }));
    expect(one.testid('domain-failures').text()).toBe(
      'The last check found a problem: at three in a row we stop serving your website on this domain.',
    );
    expect(one.testid('domain-reason').text()).toContain('Create the record that points your domain at ERPlora.');
    one.wrapper.unmount();
    const two = await setup(status({ ...ACTIVE, failures: 2 }));
    expect(two.testid('domain-failures').text()).toBe(
      'The last 2 checks found a problem: at three in a row we stop serving your website on this domain.',
    );
  });
});

describe('CustomDomainCard: a domain that is not connected', () => {
  const LAPSED = {
    ...PENDING,
    state: 'lapsed',
    state_label: 'Not connected',
    reason: 'checks_failed',
    reason_label: 'Your domain stopped pointing at ERPlora, so your website is no longer served on it. It comes back by itself when the record does.',
    failures: 3,
  };

  it('says why in the server’s words, and lets its owner ask for it again or for another one', async () => {
    const s = await setup(status(LAPSED), { api: () => Response.json(PENDING) });
    expect(s.testid('domain-state').text()).toBe('Not connected');
    expect(s.testid('domain-reason').text()).toContain('It comes back by itself when the record does.');
    expect(s.testid('domain-failures').exists()).toBe(false);
    expect(ionProps(s.testid('domain-input'), 'value')).toEqual({ value: 'www.minegocio.es' });
    await s.testid('domain-connect').trigger('click');
    await flush();
    expect(s.calls().map((c) => [c.path, c.body])).toEqual([['/api/hubs/businesses/custom-domain', { id: 'h1', domain: 'www.minegocio.es' }]]);
  });

  it('is still removed by its owner', async () => {
    const s = await setup(status(LAPSED));
    expect(s.testid('domain-remove').exists()).toBe(true);
  });
});

describe('CustomDomainCard: removing it', () => {
  const REMOVING = { ...ACTIVE, state: 'removing', state_label: 'Being removed', reason: '', reason_label: '' };

  it('asks first, says what follows, then removes it and shows it going', async () => {
    const s = await setup(status(ACTIVE), { api: () => Response.json(status(REMOVING)) });
    await s.testid('domain-remove').trigger('click');
    await flush();
    expect(s.q('domain-remove-dialog')!.getAttribute('aria-label')).toBe('Remove www.minegocio.es');
    expect(s.q('domain-remove-dialog')!.textContent).toContain(
      'Your website stops being served on www.minegocio.es and stays at its erplora.com address.',
    );
    expect(s.q('domain-remove-dialog-submit')!.color).toBe('danger');
    s.q('domain-remove-dialog-submit')!.click();
    await flush();
    expect(s.calls().map((c) => [c.method, c.path, c.body])).toEqual([['POST', '/api/hubs/businesses/custom-domain/remove', { id: 'h1' }]]);
    expect(toastSuccess).toHaveBeenCalledWith('www.minegocio.es is being removed');
    expect(s.testid('domain-state').text()).toBe('Being removed');
    expect(s.testid('domain-removing').text()).toContain('Your website is no longer served on www.minegocio.es.');
    expect(s.testid('domain-record-traffic').exists()).toBe(false);
    expect(s.testid('domain-remove').exists()).toBe(false);
  });

  it('a refusal stays in the dialog, which stays open', async () => {
    const s = await setup(status(ACTIVE), { api: () => apiError(409, 'hubs.custom_domains_off', 'Own domains are not available yet.') });
    await s.testid('domain-remove').trigger('click');
    await flush();
    s.q('domain-remove-dialog-submit')!.click();
    await flush();
    expect(s.q('domain-remove-dialog-error')!.textContent).toContain('Own domains are not available yet.');
    expect(toastSuccess).not.toHaveBeenCalled();
    expect(s.testid('domain-state').text()).toBe('Connected');
  });

  it('once gone, the live answer brings the form back', async () => {
    const s = await setup(status(REMOVING));
    await s.show(NONE);
    expect(s.testid('domain-name').exists()).toBe(false);
    expect(s.testid('domain-form').exists()).toBe(true);
  });

  it('a deployment that stopped connecting domains shows the one there is, without changing it', async () => {
    const s = await setup(status(ACTIVE, { available: false }));
    expect(s.testid('domain-state').text()).toBe('Connected');
    expect(s.testid('domain-remove').exists()).toBe(false);
    expect(s.testid('domain-unavailable').exists()).toBe(false);
  });
});

describe('CustomDomainCard: the colours say who has to act', () => {
  const tones = (s: Awaited<ReturnType<typeof setup>>) => ({
    pill: s.wrapper.getComponent(StatusPill).props(),
    reason: s.testid('domain-reason').exists() ? s.wrapper.getComponent(InlineFeedback).props('tone') : null,
  });

  it.each([
    ['waiting for the owner’s records', PENDING, 'warning', false, 'warning'],
    ['waiting for ERPlora, which tries again by itself', { ...PENDING, reason: 'quota_full', reason_label: 'No room.' }, 'warning', false, 'info'],
    ['served', ACTIVE, 'success', false, 'success'],
    ['not served', { ...PENDING, state: 'lapsed', state_label: 'Not connected', reason: 'certificate_failed', reason_label: 'Refused.' }, 'danger', false, 'danger'],
    ['going', { ...ACTIVE, state: 'removing', state_label: 'Being removed' }, 'neutral', true, null],
  ])('%s', async (_, domain, pill, busy, reason) => {
    const s = await setup(status(domain));
    expect(tones(s)).toMatchObject({ pill: { tone: pill, busy }, reason });
  });

  it('the hourly check is said only of a domain it still looks at', async () => {
    for (const [domain, said] of [
      [PENDING, true],
      [ACTIVE, true],
      [{ ...PENDING, state: 'lapsed', state_label: 'Not connected', reason: 'checks_failed', reason_label: 'Gone.' }, false],
      [{ ...ACTIVE, state: 'removing', state_label: 'Being removed' }, false],
    ] as const) {
      const s = await setup(status(domain));
      expect(s.testid('domain-checks').exists(), domain.state).toBe(said);
      s.wrapper.unmount();
    }
  });
});
