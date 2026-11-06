// A process of the e2e that says `{"ready": true}` and then answers one JSON line per JSON line it reads, in order (the
// recipe of saas#328): the Stripe of billing-downgrade.spec.ts (`billing_stripe_played.py serve`) and the warm Django of
// the panel's specs (django-warm.ts, `tests/e2e/panel/django_warm.py`, saas#352). Booted once, it spares every call a
// Python start-up (about 1 s idle, 57 s and 88 s on a loaded machine, saas#346), and it never blocks this process, which
// also plays the Hub of a spec (`startHubDouble`, saas#176). One pipe for both, so neither copies the other (saas#355).
import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';

/** The process, asked one call at a time or several at once: each answer is its call's, in order. */
export interface LineServer {
  /** `request` as one JSON line; the line that answers it. An answer `{"error": <traceback>}` rejects with it. */
  ask(request: unknown): Promise<Record<string, unknown>>;
  /** Its input ended; once the process has ended. */
  close(): Promise<void>;
}

export interface LineServerOptions {
  cwd?: string;
  env?: Readonly<Record<string, string>>;
  /** What its errors call it (its last argument by default). */
  name?: string;
  /** Kept for the whole worker: it holds none of this process up, and ends with it. */
  kept?: boolean;
}

interface Waiter {
  answered(answer: Record<string, unknown>): void;
  failed(error: Error): void;
}

/** How much of what the process wrote on its stderr an error carries: its last traceback. */
const SAID_CHARS = 4000;

/**
 * `command args…`, once it answered `{"ready": true}` as its first line. A process that ends before, or says anything
 * else first, is refused with what it wrote on its stderr; one that ends later rejects the calls waiting and every
 * call after.
 */
export async function startLineServer(command: string, args: readonly string[], options: LineServerOptions = {}): Promise<LineServer> {
  const name = options.name ?? args.at(-1) ?? command;
  const child = spawn(command, args, { cwd: options.cwd, env: options.env, stdio: ['pipe', 'pipe', 'pipe'] });
  let said = '';
  const tell = (text: string) => {
    said = (said + text).slice(-SAID_CHARS);
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
  if (options.kept) {
    child.unref();
    for (const stream of [child.stdin, child.stdout, child.stderr]) (stream as unknown as { unref?: () => void }).unref?.();
    process.once('exit', () => child.kill());
  }

  const ready = await answer();
  if (ready.ready !== true) {
    child.kill();
    await gone;
    throw new Error(`${name} did not say it is ready: ${JSON.stringify(ready)}`);
  }
  return {
    async ask(request) {
      const answered = answer();
      if (!ended) child.stdin.write(`${JSON.stringify(request)}\n`);
      const reply = await answered;
      if ('error' in reply) throw new Error(`${name} could not answer ${JSON.stringify(request)}:\n${String(reply.error)}`);
      return reply;
    },
    async close() {
      child.stdin.end();
      await gone;
    },
  };
}
