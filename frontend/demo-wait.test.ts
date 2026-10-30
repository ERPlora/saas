// The door of a demo being prepared (public/demo.py, `preparing`): the Hub answers «requested» and prepares the demo's
// database afterwards, so the page asks /demo/status/ every second, for 30 seconds at most, and goes where the answer
// says (the jump into the demo once it is ready, or the door with what happened); with no answer in time, the door's
// «not ready yet» with «Try again».
import { describe, expect, it, vi } from 'vitest';

import { POLL_MS, TIMEOUT_MS, waitForDemo } from './demo-wait';

const STATUS_URL = '/demo/status/';
const TIMEOUT_URL = '/demo/?state=not_ready';
const JUMP = 'http://demo-0123abcd.localhost:8000/auth/login?next=/';

/** A door waiting for its demo (or not, `waiting: false`). */
function door(waiting = true): Document {
  const doc = document.implementation.createHTMLDocument('door');
  if (waiting) {
    const card = doc.createElement('div');
    card.setAttribute('data-demo-wait', '');
    card.setAttribute('data-demo-status-url', STATUS_URL);
    card.setAttribute('data-demo-timeout-url', TIMEOUT_URL);
    doc.body.append(card);
  }
  return doc;
}

/** The answers of /demo/status/, one per ask (the last one repeats); `Error` is no answer at all. */
function server(...answers: Array<Record<string, unknown> | number | Error>) {
  let asked = 0;
  const fetch = vi.fn(async () => {
    const answer = answers[Math.min(asked++, answers.length - 1)];
    if (answer instanceof Error) throw answer;
    if (typeof answer === 'number') return new Response('{}', { status: answer });
    return new Response(JSON.stringify(answer), { status: 200, headers: { 'Content-Type': 'application/json' } });
  });
  return fetch as unknown as typeof globalThis.fetch & ReturnType<typeof vi.fn>;
}

/** A clock that only moves while the page waits between two asks. */
function clock() {
  let now = 1_000_000;
  return {
    now: () => now,
    sleep: vi.fn(async (ms: number) => {
      now += ms;
    }),
  };
}

describe('waitForDemo (frontend/demo-wait.ts)', () => {
  it('does nothing on a door that waits for no demo', async () => {
    const fetch = server({ state: 'ready', url: JUMP });

    expect(await waitForDemo(door(false), { fetch, navigate: vi.fn(), ...clock() })).toBeNull();
    expect(fetch).not.toHaveBeenCalled();
  });

  it('asks the status as JSON, with the session, and goes into a demo that is ready', async () => {
    const fetch = server({ state: 'ready', url: JUMP });
    const navigate = vi.fn();

    expect(await waitForDemo(door(), { fetch, navigate, ...clock() })).toBe(JUMP);

    expect(fetch).toHaveBeenCalledWith(STATUS_URL, {
      headers: { Accept: 'application/json' },
      credentials: 'same-origin',
      cache: 'no-store',
    });
    expect(navigate).toHaveBeenCalledExactlyOnceWith(JUMP);
  });

  it('asks again every second while the demo is being prepared', async () => {
    const fetch = server({ state: 'preparing' }, { state: 'preparing' }, { state: 'ready', url: JUMP });
    const navigate = vi.fn();
    const time = clock();

    await waitForDemo(door(), { fetch, navigate, ...time });

    expect(fetch).toHaveBeenCalledTimes(3);
    expect(time.sleep.mock.calls).toEqual([[POLL_MS], [POLL_MS]]);
    expect(navigate).toHaveBeenCalledExactlyOnceWith(JUMP);
  });

  it('goes to the door the answer names when the demo will not come (not ready, ended)', async () => {
    const navigate = vi.fn();

    await waitForDemo(door(), { fetch: server({ state: 'expired', url: '/demo/?state=expired' }), navigate, ...clock() });

    expect(navigate).toHaveBeenCalledExactlyOnceWith('/demo/?state=expired');
  });

  it('gives up after 30 seconds with the door’s «not ready yet»', async () => {
    const fetch = server({ state: 'preparing' });
    const navigate = vi.fn();
    const time = clock();

    expect(await waitForDemo(door(), { fetch, navigate, ...time })).toBe(TIMEOUT_URL);

    expect(TIMEOUT_MS).toBe(30_000);
    expect(POLL_MS).toBe(1_000);
    expect(fetch).toHaveBeenCalledTimes(TIMEOUT_MS / POLL_MS + 1);
    expect(navigate).toHaveBeenCalledExactlyOnceWith(TIMEOUT_URL);
  });

  it('keeps asking through a failed answer or no answer at all, until its time is up', async () => {
    const fetch = server(new TypeError('Failed to fetch'), 502, { state: 'ready', url: JUMP });
    const navigate = vi.fn();

    await waitForDemo(door(), { fetch, navigate, ...clock() });

    expect(fetch).toHaveBeenCalledTimes(3);
    expect(navigate).toHaveBeenCalledExactlyOnceWith(JUMP);
  });

  it.each(['javascript:alert(1)', '//evil.example/x', 'data:text/html,hi', 42])(
    'never follows an address that is not a page (%s)',
    async (url) => {
      const navigate = vi.fn();

      await waitForDemo(door(), { fetch: server({ state: 'ready', url }), navigate, ...clock() });

      expect(navigate).toHaveBeenCalledExactlyOnceWith(TIMEOUT_URL);
    },
  );
});
