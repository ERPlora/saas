// The account's businesses on the entry: one is a card with «Open X», several a list with «Open» on each. The page
// holds the opening, so the piece only says which business is opening and hands «Open» back to it.
// clock: data only — no code under test compares these dates with now.
import { afterEach, describe, expect, it } from 'vitest';

import { business } from '../__tests__/businesses';
import { ionProps, mountHubs } from '../__tests__/mount-hubs';
import LaunchBusinesses from './LaunchBusinesses.vue';

afterEach(() => {
  document.body.innerHTML = '';
});

const BAKERY = business('bakery', 'Panadería López');
const BAR = business('bar', 'Bar La Plaza', { last_opened_at: '2026-10-12T10:00:00Z' });

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
    expect(open.text()).toBe('Open Panadería López');
    expect(ionProps(open, 'size', 'fill', 'disabled')).toEqual({ size: 'large', fill: 'solid', disabled: false });
    await open.trigger('click');
    expect(s.handed()).toEqual([[BAKERY]]);
  });

  it('while the page opens the only business, its button says so, spins and cannot be pressed', async () => {
    const s = await setup([BAKERY], 'bakery');
    const [open] = s.opens();
    expect(open.text()).toBe('Opening Panadería López…');
    expect(open.find('ion-spinner').exists()).toBe(true);
    expect(ionProps(open, 'disabled')).toEqual({ disabled: true });
  });

  it('several are a list, the first tagged as last opened, and «Open» on a row hands that business to the page', async () => {
    const s = await setup([BAR, BAKERY]);
    const tiles = s.wrapper.get('.launch-list').findAll('[data-testid="launch-business"]');
    expect(tiles.map((tile) => tile.get('h2').text())).toEqual(['Bar La Plaza', 'Panadería López']);
    expect(tiles.map((tile) => tile.find('.tag-recent').exists())).toEqual([true, false]);
    expect(s.opens().map((open) => open.text())).toEqual(['Open', 'Open']);
    await s.opens()[1].trigger('click');
    expect(s.handed()).toEqual([[BAKERY]]);
  });

  it('while the page opens one of several, only that one spins and no «Open» can be pressed', async () => {
    const s = await setup([BAR, BAKERY], 'bar');
    expect(s.opens().map((open) => open.find('ion-spinner').exists())).toEqual([true, false]);
    expect(s.opens().map((open) => ionProps(open, 'disabled'))).toEqual([{ disabled: true }, { disabled: true }]);
  });
});
