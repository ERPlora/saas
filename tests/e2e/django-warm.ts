// The side of this process of a warm Django (saas#352): a process that says `{"ready": true}` and then answers one JSON
// line per JSON line it reads, in order (`tests/e2e/panel/django_warm.py`; the recipe of saas#328's
// `billing_stripe_played.py serve`). Booted once and kept, it spares every call a Django boot (about 1 s idle, 57 s and
// 88 s on a loaded machine, saas#346), and it never blocks this process, which also plays the Hub of a spec (saas#176).
// `fixtures.ts` starts one per worker (`djangoPrintWarm`).
import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';

/** A warm Django, as a spec asks it. */
export interface WarmDjango {
  /** What `code` printed, trimmed as `djangoPrint` trims it; a failing snippet rejects with its traceback. */
  print(code: string): Promise<string>;
}

interface Waiter {
  answered(answer: Record<string, unknown>): void;
  failed(error: Error): void;
}

/**
 * `command args`, speaking the lines of `django_warm.py`: once it said it is ready, its `print`. It ends with this
 * process (its stdin closes and its loop with it) and holds none of it up.
 */
export async function startWarm(
  command: string,
  args: readonly string[],
  options: { cwd?: string; env?: Readonly<Record<string, string>> },
): Promise<WarmDjango> {
  const child = spawn(command, args, { cwd: options.cwd, env: options.env, stdio: ['pipe', 'pipe', 'pipe'] });
  let said = '';
  const tell = (text: string) => {
    said = (said + text).slice(-4000);
  };
  child.stderr.setEncoding('utf8').on('data', tell);
  child.stdin.on('error', (error) => tell(`\n(stdin) ${error.message}`));
  const waiting: Waiter[] = [];
  let ended: Error | null = null;
  const answer = () =>
    ended ? Promise.reject(ended) : new Promise<Record<string, unknown>>((answered, failed) => waiting.push({ answered, failed }));
  createInterface({ input: child.stdout }).on('line', (line) => {
    const waiter = waiting.shift();
    if (!waiter) return tell(`\n(stdout, unasked) ${line}`);
    try {
      waiter.answered(JSON.parse(line) as Record<string, unknown>);
    } catch {
      waiter.failed(new Error(`${args.at(-1) ?? command} answered no JSON: ${line}`));
    }
  });
  const end = (why: string) => {
    ended = new Error(`${[command, ...args].join(' ').slice(0, 200)} ${why}:\n${said}`);
    for (const waiter of waiting.splice(0)) waiter.failed(ended);
  };
  child.once('error', (error) => end(`did not start (${error.message})`));
  // 'close', not 'exit': by then its stderr is read whole, so the error says why it ended.
  child.once('close', (code, signal) => end(`ended (${code ?? signal})`));
  // Kept for the whole worker, and no reason for it to live on: it ends with this process.
  child.unref();
  for (const stream of [child.stdin, child.stdout, child.stderr]) (stream as unknown as { unref?: () => void }).unref?.();
  process.once('exit', () => child.kill());

  const ready = await answer();
  if (ready.ready !== true) throw new Error(`${args.at(-1) ?? command} did not say it is ready: ${JSON.stringify(ready)}`);
  return {
    async print(code) {
      const answered = answer();
      if (!ended) child.stdin.write(`${JSON.stringify({ code })}\n`);
      const done = await answered;
      if ('error' in done) throw new Error(`the warm Django could not run:\n${code}\n${String(done.error)}`);
      return String(done.out).trim();
    },
  };
}
