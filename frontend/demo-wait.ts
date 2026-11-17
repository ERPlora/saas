// The door of a demo being prepared (public/templates/public/demo/index.html, `preparing`; public/demo.py): the Hub
// answers «requested» and prepares the demo's database afterwards, so the page asks /demo/status/ every second, for 30
// seconds at most, and goes where the answer says (`url`: the jump into the demo once it is ready, or the door with what
// happened). No answer in time is the door's «Your demo is not ready yet» with «Try again»
// (`data-demo-timeout-url`). The server decides every state; this only asks and follows.

/** How long the page waits between two asks. */
export const POLL_MS = 1_000;
/** How long the page waits for the demo before it says it is not ready yet. */
export const TIMEOUT_MS = 30_000;

/** What `waitForDemo` uses of the browser (the tests give their own). */
export interface WaitDeps {
  fetch: typeof globalThis.fetch;
  navigate: (url: string) => void;
  sleep: (ms: number) => Promise<void>;
  now: () => number;
}

const BROWSER: WaitDeps = {
  fetch: (...args) => globalThis.fetch(...args),
  navigate: (url) => window.location.assign(url),
  sleep: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
  now: () => Date.now(),
};

/** An address the page may go to: a page of this site (`/…`) or of a hub (`http(s)://…`), nothing else. */
function followable(url: unknown): url is string {
  return typeof url === 'string' && /^(https?:\/\/|\/(?!\/))/.test(url);
}

interface StatusAnswer {
  url: string | null;
  state: string | null;
}

/** The status's answer, or `null` while there is none (a failed answer or no answer). */
async function ask(statusUrl: string, deps: WaitDeps): Promise<StatusAnswer | null> {
  try {
    const response = await deps.fetch(statusUrl, {
      headers: { Accept: 'application/json' },
      credentials: 'same-origin',
      cache: 'no-store',
    });
    if (!response.ok) return null;
    const answer: unknown = await response.json();
    const url = answer && typeof answer === 'object' ? (answer as { url?: unknown }).url : undefined;
    const state = answer && typeof answer === 'object' ? (answer as { state?: unknown }).state : undefined;
    return { url: followable(url) ? url : null, state: typeof state === 'string' ? state : null };
  } catch {
    // No answer this time (the network, a page that is not JSON): the next ask may have one.
    return null;
  }
}

/** The server's state and its translated copy, supplied by the Django template in both languages. */
function show(card: HTMLElement, state: string): void {
  card.dataset.demoState = state;
  if (state !== 'preparing' && state !== 'maintenance') return;
  const title = state === 'maintenance' ? card.dataset.demoMaintenanceTitle : card.dataset.demoPreparingTitle;
  const body = state === 'maintenance' ? card.dataset.demoMaintenanceBody : card.dataset.demoPreparingBody;
  const titleElement = card.querySelector<HTMLElement>('[data-demo-title]');
  const bodyElement = card.querySelector<HTMLElement>('[data-demo-body]');
  const preparingIcon = card.querySelector<HTMLElement>('[data-demo-preparing-icon]');
  const maintenanceIcon = card.querySelector<HTMLElement>('[data-demo-maintenance-icon]');
  if (preparingIcon) preparingIcon.hidden = state === 'maintenance';
  if (maintenanceIcon) maintenanceIcon.hidden = state !== 'maintenance';
  if (titleElement && title) titleElement.textContent = title;
  if (bodyElement && body) bodyElement.textContent = body;
}

/**
 * Waits for the browser's demo on a door that says it is being prepared (`[data-demo-wait]`), then goes where the
 * status says, or to the door's «not ready yet» after `TIMEOUT_MS`. The address it went to; `null` on any other page.
 */
export async function waitForDemo(doc: Document, overrides: Partial<WaitDeps> = {}): Promise<string | null> {
  const card = doc.querySelector<HTMLElement>('[data-demo-wait]');
  const statusUrl = card?.dataset.demoStatusUrl;
  const timeoutUrl = card?.dataset.demoTimeoutUrl;
  if (!statusUrl || !timeoutUrl) return null;
  const deps = { ...BROWSER, ...overrides };
  // The 30 seconds count from the last maintenance answer: a pause never times out, and its lift gives the Hub the
  // same time to prepare the demo as a door without one.
  let started = deps.now();
  for (;;) {
    const answer = await ask(statusUrl, deps);
    if (answer?.state) show(card, answer.state);
    const paused = card.dataset.demoState === 'maintenance';
    if (paused) started = deps.now();
    const timedOut = !paused && deps.now() - started >= TIMEOUT_MS;
    const next = answer?.url ?? (timedOut ? timeoutUrl : null);
    if (next !== null) {
      deps.navigate(next);
      return next;
    }
    await deps.sleep(POLL_MS);
  }
}
