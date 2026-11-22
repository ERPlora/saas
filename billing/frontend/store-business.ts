// The business the Store sells to. Only the owner buys for a business, so the picker lists the businesses the
// account owns; `?business=` chooses the one it came from, and an unknown one falls back to the first that can buy
// (not one an unpaid invoice blocks), saying so.
import { useLive } from '@erplora/ui/sdk';
import { computed, shallowRef } from 'vue';

import { useLiveState } from '../../frontend/live-state';
import { blockOf, declinedCard, ownedBusinesses } from './store';

export function useStoreBusiness(
  props: Readonly<{ businessId?: string }>,
  emit: (event: 'update:businessId', id: string) => void,
) {
  const list = useLive('hubs.business.list', { limit: 100 });
  /** Loading, failed (the query, the stream, or nothing in time), none owned or some: «You have no business to
   *  buy for» only with a real answer. */
  const listState = useLiveState(list, { isEmpty: (data) => ownedBusinesses(data.rows).length === 0 });
  const rows = computed(() => list.data.value?.rows ?? []);
  const owned = computed(() => ownedBusinesses(rows.value));
  /** What the owner picked here; until then, `?business=`. */
  const picked = shallowRef<string | null>(null);
  const wanted = computed(() => picked.value ?? props.businessId ?? null);
  /** The one asked for; else the first that can buy (not one an unpaid invoice blocks); else the first. */
  const business = computed(
    () =>
      owned.value.find((row) => row.id === wanted.value) ??
      owned.value.find((row) => !blockOf(row)) ??
      owned.value[0] ??
      null,
  );
  const unknownAsked = computed(
    () => !picked.value && !!props.businessId && !!list.data.value && !!business.value && business.value.id !== props.businessId,
  );
  const chosenId = computed({
    get: () => business.value?.id ?? '',
    set: (id: string) => {
      picked.value = id;
      emit('update:businessId', id);
    },
  });
  const block = computed(() => (business.value ? blockOf(business.value) : null));
  /** The business whose card, the same payer's as this one, the bank declined: the checkout says so. */
  const declinedFor = computed(() => (business.value ? declinedCard(rows.value, business.value) : null));
  return { listState, owned, business, unknownAsked, chosenId, block, declinedFor };
}
