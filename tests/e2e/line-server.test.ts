// @vitest-environment node
// flow: ninguno — e2e harness (saas#355): the pipe of a process that lives a whole spec and answers one JSON line per
// JSON line it reads (line-server.ts), under the Stripe of billing-downgrade.spec.ts (saas#328) and the warm Django of
// the panel's specs (django-warm.ts, saas#352). Played here by a Node child, so what is checked is the pipe: it waits
// for «ready», answers in order, rejects one call without losing the next, and says why when the process is gone.
import { describe, expect, it } from 'vitest';

import { startLineServer } from './line-server';

/**
 * A line server of the test: `{"echo"}` → itself (after `slow` ms), `{"fail"}` → `{"error"}`, `{"raw"}` → that text,
 * `{"hang"}` → nothing, `{"die"}` → exit 3.
 */
const SERVER = String.raw`
process.stderr.write('booting\n');
process.stdout.write(JSON.stringify({ ready: true }) + '\n');
require('node:readline').createInterface({ input: process.stdin }).on('line', (line) => {
  const asked = JSON.parse(line);
  if (asked.die) { process.stderr.write('dying on purpose\n'); process.exit(3); }
  if (asked.fail) return process.stdout.write(JSON.stringify({ error: 'Traceback: ' + asked.fail }) + '\n');
  if (asked.raw) return process.stdout.write(asked.raw + '\n');
  if (asked.hang) return;
  // As the real ones: one call at a time, so a slow call delays the next instead of being overtaken.
  if (asked.slow) { const until = Date.now() + asked.slow; while (Date.now() < until); }
  process.stdout.write(JSON.stringify(asked) + '\n');
});
`;

const start = (script = SERVER) => startLineServer(process.execPath, ['-e', script], { name: 'test-server' });

describe('startLineServer', () => {
  it('starts once the process says it is ready, and answers each call with its line', async () => {
    const server = await start();
    try {
      await expect(server.ask({ echo: 1 })).resolves.toEqual({ echo: 1 });
      await expect(server.ask({ echo: 'two' })).resolves.toEqual({ echo: 'two' });
    } finally {
      await server.close();
    }
  });

  it('answers calls asked together in the order they were asked', async () => {
    const server = await start();
    try {
      const answers = await Promise.all([server.ask({ slow: 50, n: 1 }), server.ask({ n: 2 }), server.ask({ n: 3 })]);
      expect(answers.map((answer) => answer.n)).toEqual([1, 2, 3]);
    } finally {
      await server.close();
    }
  });

  it('rejects a call the process could not answer with its error, and the next call still answers', async () => {
    const server = await start();
    try {
      await expect(server.ask({ fail: 'boom' })).rejects.toThrow(/test-server could not answer \{"fail":"boom"\}:\nTraceback: boom/);
      await expect(server.ask({ echo: 'after' })).resolves.toEqual({ echo: 'after' });
    } finally {
      await server.close();
    }
  });

  it('rejects an answer that is no JSON', async () => {
    const server = await start();
    try {
      await expect(server.ask({ raw: 'not json' })).rejects.toThrow('test-server answered no JSON: not json');
    } finally {
      await server.close();
    }
  });

  it('rejects the calls waiting and the ones after when the process ends, with what it said on its stderr', async () => {
    const server = await start();
    const waiting = server.ask({ hang: true });
    const dying = server.ask({ die: true });
    await expect(waiting).rejects.toThrow(/ended \(3\):[\s\S]*dying on purpose/);
    await expect(dying).rejects.toThrow(/ended \(3\)/);
    await expect(server.ask({ echo: 'late' })).rejects.toThrow(/ended \(3\)/);
    await server.close();
  });

  it('refuses to start when the process ends before it is ready, with what it said', async () => {
    await expect(start("process.stderr.write('no Django here\\n'); process.exit(1);")).rejects.toThrow(
      /ended \(1\):[\s\S]*no Django here/,
    );
  });

  it('refuses to start when its first line is not «ready»', async () => {
    await expect(start("process.stdout.write('{\"ready\": false}\\n'); setTimeout(() => {}, 5000);")).rejects.toThrow(
      'test-server did not say it is ready: {"ready":false}',
    );
  });

  it('refuses to start a command that does not exist', async () => {
    await expect(startLineServer('no-such-command-355', [])).rejects.toThrow(/did not start/);
  });

  it('closes by ending its input, and waits for the process to end', async () => {
    const server = await start();
    await server.close();
    await expect(server.ask({ echo: 'closed' })).rejects.toThrow(/ended \(0\)/);
  });
});
