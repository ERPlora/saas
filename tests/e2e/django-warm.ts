// The side of this process of a warm Django (saas#352): a process that says `{"ready": true}` and then answers one JSON
// line per JSON line it reads, in order (`tests/e2e/panel/django_warm.py`; the recipe of saas#328's
// `billing_stripe_played.py serve`). Booted once and kept, it spares every call a Django boot (about 1 s idle, 57 s and
// 88 s on a loaded machine, saas#346), and it never blocks this process, which also plays the Hub of a spec (saas#176).
// `fixtures.ts` starts one per worker (`djangoPrintWarm`).
import { startLineServer } from './line-server';

/** A warm Django, as a spec asks it. */
export interface WarmDjango {
  /** What `code` printed, trimmed as `djangoPrint` trims it; a failing snippet rejects with its traceback. */
  print(code: string): Promise<string>;
}

/**
 * `command args`, speaking the lines of `django_warm.py` through the e2e's line pipe (line-server.ts, shared with the
 * Stripe of billing-downgrade.spec.ts): once it said it is ready, its `print`. It ends with this process (its stdin
 * closes and its loop with it) and holds none of it up.
 */
export async function startWarm(
  command: string,
  args: readonly string[],
  options: { cwd?: string; env?: Readonly<Record<string, string>> },
): Promise<WarmDjango> {
  const lines = await startLineServer(command, args, { ...options, kept: true });
  return {
    async print(code) {
      return String((await lines.ask({ code })).out).trim();
    },
  };
}
