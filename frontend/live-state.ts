// What a page driven by `useLive` paints while its data is not there (audit 2026-10-14, R-04 and R-08). The
// SDK's `status` says how the stream is, not what the page may claim: with `/api/live` down (503), no network
// or a query that fails, `data` stays `undefined` and a page that read it as «no rows» lied («Create your first
// business» with four of them) or spun for ever. One reading for every page of the panel:
//   - `loading`: no result yet, and still in time (`LIVE_TIMEOUT_MS`);
//   - `error`: the query failed, the stream was refused (an HTTP error while it retries), or nothing came in
//     time. Data on screen is never replaced by an error: a stream that drops keeps the last result (stale
//     but true; `reconnecting` says it);
//   - `empty` / `ready`: a result of the server, empty or not (`isEmpty`; an empty array by default).
// A result that arrives later (the stream came back by itself) shows at once; `retry()` reopens the stream
// and gives it a fresh time limit. Pages: DataTable's `loading`/`error` props, or `LoadFailed.vue`.
import { type LiveClient, type UseLive, useLiveClient } from '@erplora/ui/sdk';
import { computed, type ComputedRef, getCurrentScope, onScopeDispose, type Ref, shallowRef, watch } from 'vue';

/** How long a page waits for its first result before it says it could not load it. */
export const LIVE_TIMEOUT_MS = 10_000;

export type LiveView = 'loading' | 'error' | 'empty' | 'ready';

export interface LiveStateOptions<T> {
  /** A result that holds nothing (an empty list); an empty array by default, anything else is ready. */
  isEmpty?: (data: T) => boolean;
  /** Time limit of the first result (and of each «Retry»). */
  timeoutMs?: number;
  /** Explicit client (outside components or in tests); injected otherwise. */
  client?: LiveClient;
}

export interface LiveState {
  view: ComputedRef<LiveView>;
  /** `view === 'loading'`. */
  loading: ComputedRef<boolean>;
  /** `view === 'error'`. */
  failed: ComputedRef<boolean>;
  /** Data on screen while the stream recovers: stale, said by a notice. */
  reconnecting: ComputedRef<boolean>;
  /** The failure the server or the SDK reported, if any (none after a time-out). */
  error: Readonly<Ref<UseLive<unknown>['error']['value']>>;
  /** Reopens the stream and waits again, with a fresh time limit. */
  retry(): void;
}

const defaultEmpty = (data: unknown): boolean => Array.isArray(data) && data.length === 0;

export function useLiveState<T>(
  live: Pick<UseLive<T>, 'data' | 'status' | 'error' | 'refresh'>,
  options: LiveStateOptions<T> = {},
): LiveState {
  const client = options.client ?? useLiveClient();
  const timeoutMs = options.timeoutMs ?? LIVE_TIMEOUT_MS;
  const isEmpty = options.isEmpty ?? defaultEmpty;

  const timedOut = shallowRef(false);
  /** «Retry» was pressed and nothing new has been heard since. */
  const retrying = shallowRef(false);
  let cancel: (() => void) | undefined;

  function stopTimer(): void {
    cancel?.();
    cancel = undefined;
  }

  function startTimer(): void {
    stopTimer();
    timedOut.value = false;
    cancel = client.schedule(() => {
      cancel = undefined;
      timedOut.value = true;
      retrying.value = false;
    }, timeoutMs);
  }

  const hasData = computed(() => live.data.value !== undefined);
  // A result ends the wait; a new failure ends a «Retry».
  watch(hasData, (now) => {
    if (now) {
      stopTimer();
      timedOut.value = false;
      retrying.value = false;
    } else {
      startTimer();
    }
  });
  watch(live.error, (now) => {
    if (now) retrying.value = false;
  });
  if (!hasData.value) startTimer();
  if (getCurrentScope()) onScopeDispose(stopTimer);

  const view = computed<LiveView>(() => {
    const data = live.data.value;
    if (data !== undefined) return isEmpty(data as T) ? 'empty' : 'ready';
    if (retrying.value) return 'loading';
    if (timedOut.value) return 'error';
    const status = live.status.value;
    if (status === 'error') return 'error';
    if (status === 'reconnecting' && live.error.value) return 'error';
    return 'loading';
  });

  function retry(): void {
    retrying.value = true;
    startTimer();
    live.refresh();
  }

  return {
    view,
    loading: computed(() => view.value === 'loading'),
    failed: computed(() => view.value === 'error'),
    reconnecting: computed(() => hasData.value && live.status.value === 'reconnecting'),
    error: live.error,
    retry,
  };
}
