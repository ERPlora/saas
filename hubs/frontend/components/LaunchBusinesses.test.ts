// The account's businesses on the entry: one is a card with «Open X», several a list with «Open» on each. The page
// holds the opening, so the piece only says which business is opening and hands «Open» back to it.
// clock: data only — no code under test compares these dates with now.
import { describe, expect, it, vi } from 'vitest';

import { iconAction, labelled } from '../../../frontend/__tests__/icon-action';
import { business } from '../__tests__/businesses';
import { setUpLaunchPage } from '../__tests__/launch-page';
import { ionProps, mountHubs } from '../__tests__/mount-hubs';
import LaunchBusinesses from './LaunchBusinesses.vue';

setUpLaunchPage();

const BAKERY = business('bakery', 'Panadería López');
const OWED = business('bakery', 'Panadería López', { status: 'past_due', status_label: 'Payment pending', pay_url: 'https://invoice.stripe.com/i/bakery' });
const BAR = business('bar', 'Bar La Plaza', { last_opened_at: '2026-10-12T10:00:00Z' });
const BAKERY_BEFORE = business('bakery', 'Panadería López', { last_opened_at: '2026-10-01T10:00:00Z' });

async function setup(rows: unknown[], opening: string | null = null) {
  const m = await mountHubs(LaunchBusinesses, { props: { rows, opening } });
  const opens = () => m.wrapper.findAll('[data-testid="launch-open"]');
  const handed = () => m.wrapper.emitted('open') ?? [];
  return { ...m, opens, handed };
}

describe('LaunchBusinesses', () => {
  it('one business is a card whose large «Open X» hands the business to the page', async () => {
    const s = await setup([BAKERY]);
    expect(s.wrapper.findAll('[data-testid="launch-business"]')).toHaveLength(1);
    expect(s.wrapper.find('.launch-list').exists()).toBe(false);
    const [open] = s.opens();
    expect(iconAction(open.element)).toEqual(labelled('Open Panadería López'));
    expect(ionProps(open, 'size', 'fill', 'disabled')).toEqual({ size: 'large', fill: 'solid', disabled: false });
    await open.trigger('click');
    expect(s.handed()).toEqual([[BAKERY]]);
  });

  it('one business that owes puts paying first: «Open» is the second action, outlined and of normal size', async () => {
    const s = await setup([OWED]);
    expect(s.wrapper.find('[data-testid="unpaid-pay"]').exists()).toBe(true);
    const [open] = s.opens();
    expect(ionProps(open, 'size', 'fill')).toEqual({ size: undefined, fill: 'outline' });
    expect(open.classes()).toContain('launch-second');
  });

  it('the way to pay takes the spacing of the action it stands for: the main one alone, a row action in the list', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const one = await setup([OWED]);
    expect(one.wrapper.get('[data-testid="unpaid-pay"]').element.parentElement?.classList).toContain('launch-main');
    const several = await setup([OWED, BAR]);
    expect(several.wrapper.get('[data-testid="unpaid-pay"]').element.parentElement?.classList).toContain('launch-biz__pay');
    expect(warn.mock.calls.flat().filter((line) => String(line).includes('Extraneous non-props attributes'))).toEqual([]);
    warn.mockRestore();
  });

  it('while the page opens the only business, its button says so, spins and cannot be pressed', async () => {
    const s = await setup([BAKERY], 'bakery');
    const [open] = s.opens();
    expect(iconAction(open.element)).toEqual(labelled('Opening Panadería López…'));
    expect(open.find('ion-spinner').exists()).toBe(true);
    expect(ionProps(open, 'disabled')).toEqual({ disabled: true });
  });

  it('while the page opens a business of the list, only its «Open» is named so and spins', async () => {
    const s = await setup([BAR, BAKERY_BEFORE], 'bakery');
    expect(s.opens().map((open) => iconAction(open.element).name)).toEqual(['Open Bar La Plaza', 'Opening Panadería López…']);
    expect(s.opens().map((open) => open.find('ion-spinner').exists())).toEqual([false, true]);
  });

  it('several are a list, only the first tagged as last opened, and «Open» on a row hands that business to the page', async () => {
    const s = await setup([BAR, BAKERY_BEFORE]);
    const tiles = s.wrapper.get('.launch-list').findAll('[data-testid="launch-business"]');
    expect(tiles.map((tile) => tile.get('h2').text())).toEqual(['Bar La Plaza', 'Panadería López']);
    expect(tiles.map((tile) => tile.find('.tag-recent').exists())).toEqual([true, false]);
    expect(s.opens().map((open) => iconAction(open.element))).toEqual([labelled('Open', 'Open Bar La Plaza'), labelled('Open', 'Open Panadería López')]);
    await s.opens()[1].trigger('click');
    expect(s.handed()).toEqual([[BAKERY_BEFORE]]);
  });

  it('while the page opens one of several, only that one spins and no «Open» can be pressed', async () => {
    const s = await setup([BAR, BAKERY], 'bar');
    expect(s.opens().map((open) => open.find('ion-spinner').exists())).toEqual([true, false]);
    expect(s.opens().map((open) => ionProps(open, 'disabled'))).toEqual([{ disabled: true }, { disabled: true }]);
  });
});
