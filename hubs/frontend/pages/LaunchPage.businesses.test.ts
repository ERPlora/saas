// The entry (`/launch`) with businesses: one → «Open X» or «Go to the panel», with why it does not open; several →
// the last opened first. Each business says what it owes and how to pay it, and a deleted one is recovered there.
// clock: data only — no code under test compares these dates with now.
import { applySurface } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@ionic/vue', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ionic/vue')>()),
  IonModal: (await import('../__tests__/ion-modal-stub')).IonModalStub,
}));
vi.mock('@erplora/ui/shell', async (original) => (await import('../__tests__/module-mocks')).shellWithToastSpies(original));

import { accessibleName, describeCall, flush, ionProps } from '../__tests__/mount-hubs';
import { business } from '../__tests__/businesses';
import { INVITATION, page, PREPARING, setUpLaunchPage, showing } from '../__tests__/launch-page';
import { iconAction, labelled } from '../../../frontend/__tests__/icon-action';

const row = business;

setUpLaunchPage();

describe('LaunchPage: one business', () => {
  it('greets, shows the business and opens it, or goes to the panel', async () => {
    const s = await showing(page([row('bakery', 'Panadería López')]));
    expect(s.title()).toBe('Hello, Laura');
    expect(s.wrapper.get('.shell-lead').text()).toBe('What do you want to do?');
    const tile = s.testid('launch-business');
    expect(tile.get('h2').text()).toBe('Panadería López');
    expect(tile.get('.launch-biz__url').text()).toBe('bakery.localhost:8000');
    // It breaks only after a dot, never at a hyphen.
    expect(tile.find('.launch-biz__url .host-name').exists()).toBe(true);
    expect(tile.get('.status-pill').text()).toBe('Active');
    expect(tile.get('.launch-biz__meta').text()).toBe('Plan Starter · Owner');
    const open = s.testid('launch-open');
    expect(iconAction(open.element)).toEqual(labelled('Open Panadería López'));
    await open.trigger('click');
    await flush();
    expect(s.opened()).toEqual([{ id: 'bakery', next: '/' }]);
    expect(s.testid('launch-foot').text()).toBe('In the panel you manage the business, the team and your account.');
  });

  it('«Open» says it is opening and cannot be pressed again until the browser leaves', async () => {
    const s = await showing(page([row('bakery', 'Panadería López')]));
    await s.testid('launch-open').trigger('click');
    await flush();
    expect(s.opened()).toEqual([{ id: 'bakery', next: '/' }]);
    expect(iconAction(s.testid('launch-open').element)).toEqual(labelled('Opening Panadería López…'));
    expect(ionProps(s.testid('launch-open'), 'disabled')).toEqual({ disabled: true });
  });

  it('greets by the account alone when the name is an email', async () => {
    const s = await showing(page([row('bakery', 'Bakery')]), {
      session: { user: { id: 'u1', label: 'owner@example.com' }, permissions: [], menu: [], apps: [], language: 'en' },
    });
    expect(s.title()).toBe('Hello');
  });

  it('being prepared: «Open» is disabled with why, and it opens by itself when ready', async () => {
    const s = await showing(page([row('bakery', 'Bakery', PREPARING)]));
    expect(ionProps(s.testid('launch-open'), 'disabled')).toEqual({ disabled: true });
    expect(s.testid('launch-reason').text()).toBe('We are preparing it. It opens by itself when it is ready.');
    expect(s.wrapper.find('ion-progress-bar').exists()).toBe(true);
    await s.result(s.call, 'hubs.business.list', page([row('bakery', 'Bakery')]), 2);
    expect(s.opened()).toEqual([{ id: 'bakery', next: '/' }]);
  });

  it('a preparation the Hub refused: a danger pill, why, and no way to open it', async () => {
    const s = await showing(page([row('bakery', 'Bakery', { ...PREPARING, open_blocked_reason: 'error', hub_error: 'boom' })]));
    expect(s.testid('launch-business').get('.status-pill').text()).toBe('Not prepared');
    expect(s.testid('launch-reason').text()).toBe('We could not prepare it. We keep retrying; if it keeps failing, contact us.');
    expect(ionProps(s.testid('launch-open'), 'disabled')).toEqual({ disabled: true });
  });

  it('with a payment pending it still opens, and says to pay (without its date, no number of days)', async () => {
    const s = await showing(page([row('bakery', 'Bakery', { status: 'past_due', status_label: 'Payment pending' })]));
    expect(s.testid('launch-business').get('.status-pill').text()).toBe('Payment due');
    expect(s.testid('launch-reason').text()).toBe('There is an unpaid invoice: pay it so the business is not suspended.');
    expect(ionProps(s.testid('launch-open'), 'disabled')).toEqual({ disabled: false });
  });

  it('suspended: no «Open» at all, and inside the app how to pay without a link', async () => {
    applySurface('mobile');
    const s = await showing(page([row('bakery', 'Bakery', { status: 'suspended', can_open: false, open_blocked_reason: 'suspended' })]));
    expect(s.testid('launch-open').exists()).toBe(false);
    expect(s.testid('launch-reason').text()).toBe(
      'Suspended because of an unpaid invoice. Your data is safe. To pay it, go to erplora.com in your browser.',
    );
    expect(s.testid('launch-reason').find('a').exists()).toBe(false);
    expect(s.testid('launch-panel').exists()).toBe(true);
  });
});

describe('LaunchPage: the way to pay', () => {
  const OWED = {
    status: 'past_due',
    status_label: 'Payment pending',
    unpaid_reason: 'payment_failed',
    unpaid_since: '2026-10-10T14:23:00Z',
    pay_url: 'https://invoice.stripe.com/i/bakery',
  };
  const SUSPENDED = { ...OWED, status: 'suspended', status_label: 'Suspended', can_open: false, open_blocked_reason: 'suspended', unpaid_since: '2026-10-09T08:00:00Z' };

  it('past due on the web: its real deadline, «Pay the invoice» first and «Open» second', async () => {
    const s = await showing(page([row('bakery', 'Bakery', OWED)]));
    expect(s.testid('launch-reason').text()).toBe('There is an unpaid invoice. Pay it before Oct 17, 2026 or the business is suspended.');
    expect(ionProps(s.testid('unpaid-pay'), 'href', 'fill', 'size')).toEqual({ href: 'https://invoice.stripe.com/i/bakery', fill: 'solid', size: 'large' });
    expect(ionProps(s.testid('launch-open'), 'fill', 'disabled')).toEqual({ fill: 'outline', disabled: false });
  });

  it('after a declined card: «Change card» first, «Pay» waits', async () => {
    const s = await showing(page([row('bakery', 'Bakery', { ...OWED, unpaid_reason: 'card_declined' })]));
    expect(s.testid('unpaid-change-card').text()).toContain('Change card');
    expect(ionProps(s.testid('unpaid-pay'), 'disabled')).toEqual({ disabled: true });
  });

  it('suspended on the web: since when, and «Pay the invoice» instead of «Open»', async () => {
    const s = await showing(page([row('bakery', 'Bakery', SUSPENDED)]));
    expect(s.testid('launch-reason').text()).toBe(
      'Suspended because of an unpaid invoice since Oct 9, 2026. Your data is safe: pay the invoice and it works again at once.',
    );
    expect(s.testid('unpaid-pay').exists()).toBe(true);
    expect(s.testid('launch-open').exists()).toBe(false);
  });

  it('inside the app: until when and where to pay, no button to pay, «Open» first', async () => {
    applySurface('desktop');
    const s = await showing(page([row('bakery', 'Bakery', OWED)]));
    expect(s.testid('launch-reason').text()).toBe(
      'There is an unpaid invoice: it keeps working until Oct 17, 2026. To pay it, go to erplora.com in your browser.',
    );
    expect(s.testid('unpaid-pay').exists()).toBe(false);
    expect(ionProps(s.testid('launch-open'), 'fill')).toEqual({ fill: 'solid' });
  });

  it('whoever may not pay it (no `pay_url`) keeps «Open» first, with the deadline', async () => {
    const s = await showing(page([row('bakery', 'Bakery', { ...OWED, pay_url: null })]));
    expect(s.testid('unpaid-pay').exists()).toBe(false);
    expect(ionProps(s.testid('launch-open'), 'fill')).toEqual({ fill: 'solid' });
  });

  it('with several businesses, the one that owes says until when and offers to pay it', async () => {
    const s = await showing(page([row('salon', 'Peluquería Ana'), row('bakery', 'Bakery', OWED)]), { locale: 'es' });
    const tiles = s.wrapper.findAll('[data-testid="launch-business"]');
    expect(tiles[1].get('.launch-biz__why').text()).toBe('Hay una factura sin pagar. Págala antes del 17 oct 2026 o el negocio se suspende.');
    expect(tiles[1].find('[data-testid="unpaid-pay"]').exists()).toBe(true);
    expect(tiles[0].find('[data-testid="unpaid-pay"]').exists()).toBe(false);
  });
});

describe('LaunchPage: several businesses', () => {
  const ROWS = [
    row('bakery', 'Panadería López', { last_opened_at: '2026-10-13T09:12:00Z' }),
    row('salon', 'Peluquería Ana', { role: 'hub_manager', role_label: 'Manager', plan: { slug: 'free', name: 'Free' } }),
    row('cafe', 'Café Central', PREPARING),
  ];

  it('lists them in the server’s order (the last opened first), each with its «Open»', async () => {
    const s = await showing(page(ROWS));
    expect(s.title()).toBe('Where are you working today?');
    expect(s.wrapper.get('.shell-lead').text()).toBe('Choose a business to open it.');
    const tiles = s.wrapper.findAll('[data-testid="launch-business"]');
    expect(tiles.map((tile) => tile.get('h2').text())).toEqual(['Panadería López', 'Peluquería Ana', 'Café Central']);
    expect(tiles[0].get('.tag-recent').text()).toBe('Last opened');
    expect(tiles[1].find('.tag-recent').exists()).toBe(false);
    expect(tiles[1].get('.launch-biz__meta').text()).toBe('Manager');
    // With several, nothing opens by itself: the person chooses.
    expect(tiles[2].get('.launch-biz__why').text()).toBe('Ready in a few seconds');
    const opens = s.wrapper.findAll('[data-testid="launch-open"]');
    expect(opens.map((b) => accessibleName(b))).toEqual(['Open Panadería López', 'Open Peluquería Ana', 'Open Café Central']);
    expect(ionProps(opens[2], 'disabled')).toEqual({ disabled: true });
    await opens[1].trigger('click');
    await flush();
    expect(s.opened()).toEqual([{ id: 'salon', next: '/' }]);
  });

  // flow: HUBS-F04 «Si falla»: with several businesses it enters none by itself; the person chooses.
  it('one of them getting ready opens nothing by itself', async () => {
    const s = await showing(page(ROWS));
    await s.result(s.call, 'hubs.business.list', page([ROWS[0], ROWS[1], row('cafe', 'Café Central')]), 2);
    expect(s.opened()).toEqual([]);
    expect(s.navigate).not.toHaveBeenCalled();
  });

  it('offers to create another business in the panel', async () => {
    const s = await showing(page(ROWS));
    await s.testid('launch-create-another').trigger('click');
    await flush();
    expect(s.router.currentRoute.value.fullPath).toBe('/dashboard/businesses?create=1');
  });

  it('points to a pending invitation above the businesses', async () => {
    const s = await showing(page(ROWS, [INVITATION]));
    expect(s.testid('launch-invitation').text()).toContain('You have been invited to Peluquería Ana');
    await s.testid('launch-invitation-open').trigger('click');
    await flush();
    expect(s.router.currentRoute.value.path).toBe('/invitations/m1');
  });
});

describe('LaunchPage: Spanish', () => {
  it('speaks Spanish', async () => {
    const s = await showing(page([row('bakery', 'Panadería López')]), { locale: 'es' });
    expect(s.title()).toBe('Hola, Laura');
    expect(iconAction(s.testid('launch-open').element)).toEqual(labelled('Abrir Panadería López'));
    expect(s.testid('launch-panel').text()).toBe('Ir al panel');
    expect(s.testid('launch-business').get('.status-pill').text()).toBe('Activo');
    expect(document.title).toBe('Entrar - ERPlora');
  });
});

describe('LaunchPage: a deleted business is recovered from the card', () => {
  const DELETED = {
    status: 'deleting',
    status_label: 'Deleted',
    can_open: false,
    open_blocked_reason: 'deleting',
    deletion_requested_at: '2026-10-10T10:00:00Z',
    purge_after: '2027-01-08T10:00:00Z',
    can: { open: false, manage: false, restore: true, delete: false },
  };

  it('one: its owner recovers it, the main action, and it is said; no «Open»', async () => {
    const s = await showing(page([row('bakery', 'Bakery', DELETED)]), {
      api: (call) =>
        describeCall(call).path === '/api/hubs/businesses/restore' ? Response.json({ id: 'bakery', name: 'Bakery', status: 'active' }) : Response.json({}),
    });
    expect(s.testid('launch-reason').text()).toContain('Deleted. You can recover it until Jan 8, 2027');
    const recover = s.testid('recover-business');
    expect(iconAction(recover.element)).toEqual(labelled('Recover business'));
    expect(ionProps(recover, 'size', 'expand')).toEqual({ size: 'large', expand: 'block' });
    expect(s.testid('launch-open').exists()).toBe(false);
    await recover.trigger('click');
    await flush();
    expect(s.calls().find((c) => c.path === '/api/hubs/businesses/restore')?.body).toEqual({ id: 'bakery' });
  });

  it('whoever may not recover it sees why, and no button', async () => {
    const s = await showing(page([row('bakery', 'Bakery', { ...DELETED, role: 'hub_admin', can: { ...DELETED.can, restore: false } })]));
    expect(s.testid('recover-business').exists()).toBe(false);
    expect(s.testid('launch-panel').exists()).toBe(true);
  });

  it('several: the deleted one offers «Recover», named with its business', async () => {
    const s = await showing(page([row('salon', 'Peluquería Ana', { can: DELETED.can }), row('bakery', 'Bakery', DELETED)]));
    const tiles = s.wrapper.findAll('[data-testid="launch-business"]');
    expect(tiles[0].find('[data-testid="recover-business"]').exists()).toBe(false);
    expect(accessibleName(tiles[1].get('[data-testid="recover-business"]'))).toBe('Recover Bakery');
  });
});

describe('LaunchPage: one filled button per business', () => {
  it('several: a business that owes keeps the payment filled and «Open» outlined', async () => {
    const OWED = { status: 'past_due', status_label: 'Payment pending', unpaid_reason: 'payment_failed', unpaid_since: '2026-10-10T14:23:00Z', pay_url: 'https://invoice.stripe.com/i/bakery' };
    const s = await showing(page([row('salon', 'Peluquería Ana'), row('bakery', 'Bakery', OWED)]));
    const tiles = s.wrapper.findAll('[data-testid="launch-business"]');
    expect(ionProps(tiles[1].get('[data-testid="unpaid-pay"]'), 'fill')).toEqual({ fill: 'solid' });
    expect(ionProps(tiles[1].get('[data-testid="launch-open"]'), 'fill')).toEqual({ fill: 'outline' });
    expect(ionProps(tiles[0].get('[data-testid="launch-open"]'), 'fill')).toEqual({ fill: 'solid' });
  });
});
