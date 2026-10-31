// «Download the data» on a business's Summary (PLAN-DB round 2026-10-30, proposals (a), (k), (l); HUBS-F18, HUBS-F20):
// the copies the Hub keeps of the business's data (`hubs.data_copy.list`: when, which, how big), each downloaded with
// a fresh link of the Hub's asked on the click (`hubs.data_copy.link`, 15 minutes). Only its owner (`can.download_data`,
// the server's). A deleted business always shows the card: «not ready yet, we will let you know» while the Hub has no
// copy (or is away), and an error with «Retry» when the panel cannot ask. A live business shows it only once it has a
// copy (made before its data was reset).
// clock: data only — no code under test compares these dates with now.
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastError: vi.fn(() => Promise.resolve()),
}));

import { toastError } from '@erplora/ui/shell';

import { browser } from '../../../billing/frontend/browser';
import { accessibleName, apiError, describeCall, flush, mountHubs } from '../__tests__/mount-hubs';
import DataCopyCard from './DataCopyCard.vue';

const LIST = '/api/hubs/data-copies';
const LINK = '/api/hubs/data-copies/link';
const OFFBOARDING = {
  id: '0193a0c4000070008000000000000001/20261030T101500Z-offboarding.dump',
  kind: 'offboarding',
  created_at: '2026-10-30T10:15:00Z',
  bytes: 48_213_504,
};
const RESET = {
  id: '0193a0c4000070008000000000000001/20261020T080000Z-reset.dump',
  kind: 'reset',
  created_at: '2026-10-20T08:00:00Z',
  bytes: 1_536,
};
const DELETED = { id: 'plaza', name: 'Bar La Plaza', status: 'deleting', can: { download_data: true } };
const LIVE = { ...DELETED, status: 'active' };
const PRESIGNED = 'https://dumps.example.test/copy?X-Amz-Expires=900&X-Amz-Signature=abc';

afterEach(() => {
  vi.mocked(toastError).mockClear();
  vi.restoreAllMocks();
  document.body.innerHTML = '';
});

type Answer = Response | (() => Response | Promise<Response>);

function mountIt(business: Record<string, unknown>, answers: { list?: Answer; link?: Answer } = {}, locale: 'en' | 'es' = 'en') {
  const answer = (value: Answer | undefined, fallback: () => Response) =>
    value === undefined ? fallback() : typeof value === 'function' ? value() : value.clone();
  return mountHubs(DataCopyCard, {
    props: { business },
    locale,
    api: (call) => {
      const { path } = describeCall(call);
      if (path === LIST) return answer(answers.list, () => Response.json({ business_id: 'plaza', available: true, copies: [OFFBOARDING, RESET] }));
      if (path === LINK) return answer(answers.link, () => Response.json({ url: PRESIGNED }));
      return Response.json({});
    },
  });
}

describe('DataCopyCard', () => {
  it('lists the copies of a deleted business, newest first, with when, which and how big', async () => {
    const m = await mountIt(DELETED);
    expect(m.wrapper.find('[data-testid="data-copy-loading"]').exists()).toBe(true);
    await flush();

    expect(m.calls().filter((c) => c.path === LIST).map((c) => c.query)).toEqual([{ business_id: 'plaza' }]);
    const card = m.wrapper.get('[data-testid="data-copy-card"]');
    expect(card.text()).toContain('Download the data');
    expect(card.text()).toContain("A full copy of all the business's data");
    const rows = m.wrapper.findAll('[data-testid="data-copy-row"]');
    expect(rows).toHaveLength(2);
    expect(rows[0].text()).toContain('When it was deleted');
    expect(rows[0].text()).toContain('46 MB');
    expect(rows[0].text()).toContain('2026');
    expect(rows[1].text()).toContain('Before its data was reset');
    expect(rows[1].text()).toContain('1.5 kB');
  });

  it('downloads a copy with a link asked on the click, never one kept from before', async () => {
    const assign = vi.spyOn(browser, 'assign').mockImplementation(() => {});
    const m = await mountIt(DELETED);
    await flush();

    const button = m.wrapper.findAll('[data-testid="data-copy-download"]')[0];
    expect(accessibleName(button)).toMatch(/^Download the copy of .*2026/);
    await button.trigger('click');
    await flush();

    expect(m.calls().filter((c) => c.path === LINK).map((c) => c.query)).toEqual([
      { business_id: 'plaza', copy_id: OFFBOARDING.id },
    ]);
    expect(assign).toHaveBeenCalledExactlyOnceWith(PRESIGNED);
  });

  it('a copy the Hub no longer keeps says the server’s sentence and goes nowhere', async () => {
    const assign = vi.spyOn(browser, 'assign').mockImplementation(() => {});
    const m = await mountIt(DELETED, {
      link: () => apiError(404, 'hubs.data_copy_gone', 'This copy of the data is no longer kept.'),
    });
    await flush();

    await m.wrapper.findAll('[data-testid="data-copy-download"]')[0].trigger('click');
    await flush();

    expect(toastError).toHaveBeenCalledWith('This copy of the data is no longer kept.');
    expect(assign).not.toHaveBeenCalled();
  });

  it('a deleted business without a copy yet says it is not ready and that we will tell', async () => {
    const m = await mountIt(DELETED, { list: Response.json({ business_id: 'plaza', available: true, copies: [] }) });
    await flush();

    expect(m.wrapper.get('[data-testid="data-copy-not-ready"]').text()).toContain(
      'The copy is not ready yet. We will let you know by email when it is.',
    );
    expect(m.wrapper.find('[data-testid="data-copy-row"]').exists()).toBe(false);
  });

  it('a deleted business without a database of its own says it has no copy, and promises nothing', async () => {
    const m = await mountIt(DELETED, { list: Response.json({ business_id: 'plaza', available: false, copies: [] }) });
    await flush();

    expect(m.wrapper.get('[data-testid="data-copy-none"]').text()).toContain('This business has no copy of its data.');
    expect(m.wrapper.find('[data-testid="data-copy-not-ready"]').exists()).toBe(false);
    expect(m.wrapper.text()).not.toContain('We will let you know');
  });

  it('says it has no copy in Spanish', async () => {
    const m = await mountIt(DELETED, { list: Response.json({ business_id: 'plaza', available: false, copies: [] }) }, 'es');
    await flush();

    expect(m.wrapper.get('[data-testid="data-copy-none"]').text()).toContain('Este negocio no tiene copia de datos.');
  });

  it('an error of the panel says so with «Retry», which asks again', async () => {
    let asked = 0;
    const m = await mountIt(DELETED, {
      list: () =>
        asked++ === 0
          ? apiError(500, 'internal_error', 'Something went wrong.')
          : Response.json({ business_id: 'plaza', available: true, copies: [OFFBOARDING] }),
    });
    await flush();

    expect(m.wrapper.get('[data-testid="data-copy-error"]').text()).toContain('We could not load the copies of the data.');
    await m.wrapper.get('[data-testid="data-copy-retry"]').trigger('click');
    await flush();

    expect(m.wrapper.findAll('[data-testid="data-copy-row"]')).toHaveLength(1);
    expect(m.wrapper.find('[data-testid="data-copy-error"]').exists()).toBe(false);
  });

  it('a live business shows its copies once it has one', async () => {
    const m = await mountIt(LIVE, { list: Response.json({ business_id: 'plaza', available: true, copies: [RESET] }) });
    await flush();

    expect(m.wrapper.findAll('[data-testid="data-copy-row"]')).toHaveLength(1);
  });

  it.each([
    ['no copy', Response.json({ business_id: 'plaza', available: true, copies: [] })],
    ['no database of its own', Response.json({ business_id: 'plaza', available: false, copies: [] })],
    ['an error', apiError(500, 'internal_error', 'Something went wrong.')],
  ])('a live business with %s shows nothing', async (_case, list) => {
    const m = await mountIt(LIVE, { list });
    await flush();

    expect(m.wrapper.find('[data-testid="data-copy-card"]').exists()).toBe(false);
    expect(m.wrapper.find('[data-testid="data-copy-loading"]').exists()).toBe(false);
  });

  it('whoever is not its owner sees nothing and asks nothing', async () => {
    const m = await mountIt({ ...DELETED, can: { download_data: false } });
    await flush();

    expect(m.wrapper.find('[data-testid="data-copy-card"]').exists()).toBe(false);
    expect(m.calls()).toEqual([]);
  });

  it('speaks Spanish', async () => {
    const m = await mountIt(DELETED, {}, 'es');
    await flush();

    const card = m.wrapper.get('[data-testid="data-copy-card"]');
    expect(card.text()).toContain('Descargar los datos');
    expect(card.text()).toContain('Al eliminarlo');
    expect(card.text()).toContain('Antes de restablecer sus datos');
    expect(card.text()).toContain('1,5 kB');
    expect(accessibleName(m.wrapper.findAll('[data-testid="data-copy-download"]')[0])).toMatch(/^Descargar la copia del /);
  });

  it('says it is not ready in Spanish', async () => {
    const m = await mountIt(DELETED, { list: Response.json({ business_id: 'plaza', available: true, copies: [] }) }, 'es');
    await flush();

    expect(m.wrapper.get('[data-testid="data-copy-not-ready"]').text()).toContain(
      'La copia todavía no está lista. Te avisaremos por correo cuando lo esté.',
    );
  });
});
