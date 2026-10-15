// Test helper of the account pages that talk to allauth.headless: a fake of its browser API, as a
// stubbed `fetch` that answers by method and path (`'POST /auth/2fa/authenticate'`), and the
// answers allauth gives. A list of answers is served in order, its last one repeated after.
import { ALLAUTH_BROWSER_BASE } from '@erplora/ui/sdk';
import { vi } from 'vitest';

export type Answer = () => Response | Promise<Response>;

export interface Call {
  method: string;
  path: string;
  body: unknown;
  headers: Record<string, string>;
}

export function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

const USER = { id: 1, email: 'owner@example.com', display: 'Owner', has_usable_password: true };

/** `GET …/auth/session` (and any auth call) of a signed-in user. */
export const signedIn: Answer = () => json(200, { status: 200, data: { user: USER, methods: [] }, meta: { is_authenticated: true } });
/** The anonymous state, nothing pending. */
export const anonymous: Answer = () => json(401, { status: 401, data: { flows: [{ id: 'login' }] }, meta: { is_authenticated: false } });
/** The anonymous state of a login waiting for its second factor. */
export const pendingSecondFactor: Answer = () =>
  json(401, {
    status: 401,
    data: { flows: [{ id: 'login' }, { id: 'mfa_authenticate', is_pending: true }] },
    meta: { is_authenticated: false },
  });
/** The anonymous state of a sign-up (or a login of an unverified address) waiting for its mailed code. */
export const pendingEmailVerification: Answer = () =>
  json(401, {
    status: 401,
    data: { flows: [{ id: 'login' }, { id: 'verify_email', is_pending: true }] },
    meta: { is_authenticated: false },
  });
/** The anonymous state of a password login waiting for the code mailed to the account (every sign-in). */
export const pendingLoginCode: Answer = () =>
  json(401, {
    status: 401,
    data: { flows: [{ id: 'login' }, { id: 'login_by_code', is_pending: true }] },
    meta: { is_authenticated: false },
  });
/** allauth's answer when nothing is limited any more: too many requests (a 429 carries no errors). */
export const tooManyRequests: Answer = () => json(429, { status: 429 });
/** A protected account call while the recent login is too old: the flows that can confirm it. */
export const reauthenticationRequired =
  (flows: string[] = ['reauthenticate', 'mfa_reauthenticate']): Answer =>
  () =>
    json(401, { status: 401, data: { user: USER, methods: [], flows: flows.map((id) => ({ id })) }, meta: { is_authenticated: true } });
/** allauth's rejection of one input (`param`) or of the whole form (no `param`). */
export const rejected =
  (message: string, param?: string, code = 'invalid'): Answer =>
  () =>
    json(400, { status: 400, errors: [{ message, code, ...(param ? { param } : {}) }] });
export const ok =
  (data?: unknown): Answer =>
  () =>
    json(200, data === undefined ? { status: 200 } : { status: 200, data });
export const notFound: Answer = () => json(404, { status: 404 });
export const conflict: Answer = () => json(409, { status: 409 });
export const offline: Answer = () => Promise.reject(new TypeError('Failed to fetch'));
/** An answer that waits until the test releases it. */
export function held(answer: Answer): { answer: Answer; release: () => void } {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => (release = resolve));
  return { answer: () => gate.then(answer), release };
}

/** Stubs `fetch` with the fake; `serve` adds or replaces answers, `calls` lists every request. */
export function fakeAllauth(answers: Record<string, Answer | Answer[]> = {}) {
  const table = new Map<string, Answer[]>();
  const calls: Call[] = [];
  const serve = (more: Record<string, Answer | Answer[]>) => {
    for (const [key, answer] of Object.entries(more)) table.set(key, Array.isArray(answer) ? [...answer] : [answer]);
  };
  serve(answers);
  const fetch = vi.fn((url: string, init: RequestInit) => {
    const method = init.method ?? 'GET';
    const path = url.startsWith(ALLAUTH_BROWSER_BASE) ? url.slice(ALLAUTH_BROWSER_BASE.length) : url;
    calls.push({
      method,
      path,
      body: typeof init.body === 'string' ? JSON.parse(init.body) : undefined,
      headers: { ...(init.headers as Record<string, string> | undefined) },
    });
    const queue = table.get(`${method} ${path}`);
    if (!queue) return Promise.resolve(json(599, { status: 599, errors: [{ message: `No fake answer for ${method} ${path}` }] }));
    const answer = queue.length > 1 ? queue.shift()! : queue[0];
    return Promise.resolve(answer());
  });
  vi.stubGlobal('fetch', fetch);
  /** The requests made to `method path`, in order. */
  const callsTo = (key: string) => calls.filter((call) => `${call.method} ${call.path}` === key);
  return { fetch, calls, callsTo, serve };
}
