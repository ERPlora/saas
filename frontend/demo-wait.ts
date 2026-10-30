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

/** The `url` of the status's answer, or `null` while there is none to follow (still preparing, or no answer). */
async function ask(statusUrl: string, deps: WaitDeps): Promise<string | null> {
  try {
    const response = await deps.fetch(statusUrl, {
      headers: { Accept: 'application/json' },
      credentials: 'same-origin',
      cache: 'no-store',
    });
    if (!response.ok) return null;
    const answer: unknown = await response.json();
    const url = answer && typeof answer === 'object' ? (answer as { url?: unknown }).url : undefined;
    return followable(url) ? url : null;
  } catch {
    // No answer this time (the network, a page that is not JSON): the next ask may have one.
    return null;
  }
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
  const started = deps.now();
  for (;;) {
    const url = await ask(statusUrl, deps);
    const next = url ?? (deps.now() - started >= TIMEOUT_MS ? timeoutUrl : null);
    if (next !== null) {
      deps.navigate(next);
      return next;
    }
    await deps.sleep(POLL_MS);
  }
}
