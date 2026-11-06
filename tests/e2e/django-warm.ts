// A line server, as the e2e's specs talk to one (saas#328, saas#352): a process that says `{"ready": true}` and then
// answers one JSON line per JSON line it reads, in order — the warm Django of the panel's specs
// (`tests/e2e/panel/django_warm.py`, `startWarm`) and the Stripe of billing-downgrade.spec.ts
// (`billing_stripe_played.py serve`). Booted once and kept, it spares every call a Python and Django boot (about 1 s
// idle, 57 s and 88 s on a loaded machine, saas#346), and it never blocks this process, which also plays the Hub of a
// spec (saas#176). `fixtures.ts` starts one warm Django per worker (`djangoPrintWarm`).
import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';

/** A line server, as a spec asks it. */
export interface LineServer {
  /** Its answer to `request`; one that says `error` rejects with that traceback, and the next request still runs. */
  ask(request: unknown): Promise<Record<string, unknown>>;
  /** Ends its stdin and waits for the process to end: nothing is answered after. */
  close(): Promise<void>;
}

interface Waiter {
  answered(answer: Record<string, unknown>): void;
  failed(error: Error): void;
}

/**
 * `command args`, once it said it is ready. Its stdout carries only its answers; what it says on its stderr (its last
 * 4000 characters) travels in the error once it ends. It ends with this process (its stdin closes, and its loop with
 * it) and holds none of it up.
 */
export async function startLineServer(
  command: string,
  args: readonly string[],
  options: { cwd?: string; env?: Readonly<Record<string, string>> },
): Promise<LineServer> {
  // What the errors call it: its script (`django_warm.py`, `billing_stripe_played.py`), else its command.
  const name = args.find((arg) => arg.endsWith('.py')) ?? command;
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
      waiter.failed(new Error(`${name} answered no JSON: ${line}`));
    }
  });
  const gone = new Promise<void>((done) => {
    const end = (why: string) => {
      ended = new Error(`${[command, ...args].join(' ').slice(0, 200)} ${why}:\n${said}`);
      for (const waiter of waiting.splice(0)) waiter.failed(ended);
      done();
    };
    child.once('error', (error) => end(`did not start (${error.message})`));
    // 'close', not 'exit': by then its stderr is read whole, so the error says why it ended.
    child.once('close', (code, signal) => end(`ended (${code ?? signal})`));
  });
  // Kept as long as a spec wants it, and no reason for this process to live on: it ends with it.
  child.unref();
  for (const stream of [child.stdin, child.stdout, child.stderr]) (stream as unknown as { unref?: () => void }).unref?.();
  process.once('exit', () => child.kill());

  const ready = await answer();
  if (ready.ready !== true) throw new Error(`${name} did not say it is ready: ${JSON.stringify(ready)}`);
  return {
    async ask(request) {
      const answered = answer();
      if (!ended) child.stdin.write(`${JSON.stringify(request)}\n`);
      const done = await answered;
      if ('error' in done) throw new Error(`${name} could not answer ${JSON.stringify(request)}:\n${String(done.error)}`);
      return done;
    },
    async close() {
      child.stdin.end();
      await gone;
    },
  };
}

/** A warm Django, as a spec asks it. */
export interface WarmDjango {
  /** What `code` printed, trimmed as `djangoPrint` trims it; a failing snippet rejects with its traceback. */
  print(code: string): Promise<string>;
}

/** `command args` speaking the lines of `django_warm.py` (`{"code"}` → `{"out"}`), once it said it is ready. */
export async function startWarm(
  command: string,
  args: readonly string[],
  options: { cwd?: string; env?: Readonly<Record<string, string>> },
): Promise<WarmDjango> {
  const server = await startLineServer(command, args, options);
  return {
    print: async (code) => String((await server.ask({ code })).out).trim(),
  };
}
