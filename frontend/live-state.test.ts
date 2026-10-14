// What a page driven by `useLive` says while its data is not there (audit 2026-10-14, R-04 and R-08): loading
// (no result yet), error (the query or the stream failed, or nothing came in time) and, only with a real
// result from the server, empty or ready. Never «empty» on a failure, never a spinner for ever; a «Retry»
// reopens the stream, and a result that arrives later (the stream came back by itself) shows at once.
import { useLive } from '@erplora/ui/sdk';
import { describe, expect, it } from 'vitest';
import { effectScope } from 'vue';

import {
  BYE,
  createTestClient,
  errorFrame,
  flush,
  HELLO,
  resultFrame,
} from '../packages/ui/src/sdk/__tests__/live-harness';
import { OPERATION_ROUTES } from './generated/operation-routes';
import { LIVE_TIMEOUT_MS, useLiveState } from './live-state';

const OP = 'hubs.business.list';
const PAGE = { rows: [], total: 0, limit: 50, offset: 0, invitations: [], ownership_offers: [] };
const ROW = { id: 'b1', name: 'Bar' };

type Overrides = Parameters<typeof createTestClient>[0];

/** A page's `useLive` + `useLiveState`, inside a scope as a component would hold them. */
function setup(options: { overrides?: Overrides; isEmpty?: (data: typeof PAGE) => boolean } = {}) {
  const harness = createTestClient({ routes: OPERATION_ROUTES, ...options.overrides });
  const scope = effectScope();
  const state = scope.run(() => {
    const live = useLive(OP, { limit: 50, offset: 0 }, { client: harness.client });
    return { live, ...useLiveState(live, { client: harness.client, isEmpty: options.isEmpty as never }) };
  })!;
  const subId = () => harness.client.stream.subscriptions(OP)[0].id;
  return { ...harness, scope, state, subId };
}

describe('useLiveState', () => {
  it('is loading until the first result, then ready with rows', async () => {
    const t = setup({ isEmpty: (data) => data.rows.length === 0 });
    expect(t.state.view.value).toBe('loading');
    expect(t.state.loading.value).toBe(true);
    const call = await t.goLive();
    expect(t.state.view.value).toBe('loading');
    call.push(resultFrame(t.subId(), { ...PAGE, rows: [ROW], total: 1 }, 1));
    await flush();
    expect(t.state.view.value).toBe('ready');
    expect(t.state.loading.value).toBe(false);
    expect(t.state.failed.value).toBe(false);
  });

  it('is empty only with a result of the server that holds nothing', async () => {
    const t = setup({ isEmpty: (data) => data.rows.length === 0 });
    const call = await t.goLive();
    call.push(resultFrame(t.subId(), PAGE, 1));
    await flush();
    expect(t.state.view.value).toBe('empty');
  });

  it('without `isEmpty`, any result of the server is ready', async () => {
    const t = setup();
    const call = await t.goLive();
    call.push(resultFrame(t.subId(), PAGE, 1));
    await flush();
    expect(t.state.view.value).toBe('ready');
  });

  it('says error, not empty, when the query fails', async () => {
    const t = setup({ isEmpty: (data) => data.rows.length === 0 });
    const call = await t.goLive();
    call.push(errorFrame(t.subId(), 'internal_error'));
    await flush();
    expect(t.state.view.value).toBe('error');
    expect(t.state.failed.value).toBe(true);
    expect(t.state.error.value?.code).toBe('internal_error');
  });

  it('says error when /api/live answers 503, even while the stream keeps retrying', async () => {
    const harnessNet: { live: number } = { live: 0 };
    const t = setup({
      isEmpty: (data) => data.rows.length === 0,
      overrides: {
        fetchImpl: (url: string) => {
          if (url.startsWith('/api/live?')) harnessNet.live += 1;
          return Promise.resolve(
            Response.json(
              { error: { code: 'service_unavailable', message: 'Service unavailable' } },
              { status: 503 },
            ),
          );
        },
      },
    });
    await t.clock.advance(150);
    expect(harnessNet.live).toBe(1);
    expect(t.state.live.status.value).toBe('reconnecting');
    expect(t.state.view.value).toBe('error');
  });

  it('says error when the stream dies without an answer (no network), after the time limit', async () => {
    const t = setup({ isEmpty: (data) => data.rows.length === 0 });
    const call = await t.goLive();
    call.push(BYE);
    await flush();
    expect(t.state.live.status.value).toBe('reconnecting');
    expect(t.state.view.value).toBe('loading');
    await t.clock.advance(LIVE_TIMEOUT_MS);
    expect(t.state.view.value).toBe('error');
  });

  it('never spins for ever: no result in time is an error', async () => {
    const t = setup();
    await t.clock.advance(LIVE_TIMEOUT_MS - 1);
    expect(t.state.view.value).toBe('loading');
    await t.clock.advance(1);
    expect(t.state.view.value).toBe('error');
  });

  it('shows a result that arrives after the error (the stream came back by itself)', async () => {
    const t = setup({ isEmpty: (data) => data.rows.length === 0 });
    const call = await t.goLive();
    call.push(errorFrame(t.subId(), 'internal_error'));
    await flush();
    expect(t.state.view.value).toBe('error');
    call.push(resultFrame(t.subId(), { ...PAGE, rows: [ROW], total: 1 }, 2));
    await flush();
    expect(t.state.view.value).toBe('ready');
  });

  it('«Retry» reopens the stream and loads again, with a fresh time limit', async () => {
    const t = setup({ isEmpty: (data) => data.rows.length === 0 });
    await t.goLive();
    await t.clock.advance(LIVE_TIMEOUT_MS);
    expect(t.state.view.value).toBe('error');
    const before = t.net.streams.length;
    t.state.retry();
    await flush();
    expect(t.net.streams.length).toBe(before + 1);
    expect(t.state.view.value).toBe('loading');
    const call = t.net.lastStream();
    call.push(HELLO);
    call.push(resultFrame(t.subId(), { ...PAGE, rows: [ROW], total: 1 }, 1));
    await flush();
    expect(t.state.view.value).toBe('ready');
  });

  it('after «Retry», a new failure is an error again at once', async () => {
    const t = setup();
    const call = await t.goLive();
    call.push(errorFrame(t.subId(), 'internal_error'));
    await flush();
    t.state.retry();
    await flush();
    expect(t.state.view.value).toBe('loading');
    const again = t.net.lastStream();
    again.push(HELLO);
    again.push(errorFrame(t.subId(), 'internal_error'));
    await flush();
    expect(t.state.view.value).toBe('error');
  });

  it('keeps the data it has while the stream reconnects: stale but true', async () => {
    const t = setup({ isEmpty: (data) => data.rows.length === 0 });
    const call = await t.goLive();
    call.push(resultFrame(t.subId(), { ...PAGE, rows: [ROW], total: 1 }, 1));
    await flush();
    call.push(BYE);
    await flush();
    await t.clock.advance(LIVE_TIMEOUT_MS * 2);
    expect(t.state.live.status.value).toBe('reconnecting');
    expect(t.state.view.value).toBe('ready');
    expect(t.state.reconnecting.value).toBe(true);
  });
});
