// The business the Store sells to: only one the account owns; `?business=` picks it, and an unknown one falls back
// to the first that can buy (not one an unpaid invoice blocks), saying so until the owner picks another.
import { describe, expect, it } from 'vitest';
import { defineComponent } from 'vue';

import { BAKERY, businessPage, businessRow, CAFE, PLAZA, SALON } from './__tests__/fixtures';
import { mountBilling } from './__tests__/mount-billing';
import { useStoreBusiness } from './store-business';

const ROWS = [BAKERY, CAFE, PLAZA, SALON];

async function setup(businessId?: string, rows: unknown[] | null = ROWS) {
  let store!: ReturnType<typeof useStoreBusiness>;
  const Host = defineComponent({
    props: { businessId: { type: String, required: false, default: undefined } },
    emits: ['update:businessId'],
    setup(props, { emit }) {
      store = useStoreBusiness(props, emit);
      return () => null;
    },
  });
  const s = await mountBilling(Host, { props: { businessId } });
  const call = await s.live();
  if (rows) await s.result(call, 'hubs.business.list', businessPage(rows as never));
  return { ...s, call, store: () => store };
}

describe('useStoreBusiness', () => {
  it('asks for the account’s businesses and sells to the first one it owns, never one it only manages', async () => {
    const s = await setup();
    expect(s.client.stream.subscriptions('hubs.business.list').map((sub) => sub.params)).toEqual([{ limit: 100 }]);
    expect(s.store().owned.value.map((row) => row.id)).toEqual(['bakery', 'cafe', 'plaza']);
    expect(s.store().business.value?.id).toBe('bakery');
    expect(s.store().chosenId.value).toBe('bakery');
    expect(s.store().block.value).toBeNull();
    expect(s.store().unknownAsked.value).toBe(false);
    expect(s.store().declinedFor.value).toBeNull();
  });

  it('without ?business= it skips the one an unpaid invoice blocks', async () => {
    const s = await setup(undefined, [PLAZA, BAKERY]);
    expect(s.store().business.value?.id).toBe('bakery');
  });

  it('when every business is blocked it sells to the first, and says why it cannot buy', async () => {
    const s = await setup(undefined, [PLAZA]);
    expect(s.store().business.value?.id).toBe('plaza');
    expect(s.store().block.value).toBe('card_declined');
  });

  it('?business= chooses the business it came from, also a blocked one', async () => {
    const s = await setup('plaza');
    expect(s.store().business.value?.id).toBe('plaza');
    expect(s.store().block.value).toBe('card_declined');
    expect(s.store().unknownAsked.value).toBe(false);
  });

  it('an unknown ?business= falls back to the first that can buy and says so, until the owner picks one', async () => {
    const s = await setup('nope', [PLAZA, BAKERY, CAFE]);
    expect(s.store().business.value?.id).toBe('bakery');
    expect(s.store().unknownAsked.value).toBe(true);
    s.store().chosenId.value = 'cafe';
    expect(s.store().business.value?.id).toBe('cafe');
    expect(s.store().unknownAsked.value).toBe(false);
    expect(s.wrapper.emitted('update:businessId')).toEqual([['cafe']]);
  });

  it('says nothing of an unknown ?business= before the businesses arrive', async () => {
    const s = await setup('nope', null);
    expect(s.store().business.value).toBeNull();
    expect(s.store().unknownAsked.value).toBe(false);
    expect(s.store().chosenId.value).toBe('');
  });

  it('names the business whose card, of the same payer, the bank declined', async () => {
    const norte = businessRow('norte', 'Bar Norte', { payer_id: 'bakery-payer', unpaid_reason: 'card_declined' });
    const s = await setup('bakery', [BAKERY, norte]);
    expect(s.store().declinedFor.value).toBe('Bar Norte');
  });

  it('an account that owns no business: the list is empty and nothing is sold', async () => {
    const s = await setup(undefined, [SALON]);
    expect(s.store().listState.view.value).toBe('empty');
    expect(s.store().business.value).toBeNull();
    expect(s.store().block.value).toBeNull();
  });
});
