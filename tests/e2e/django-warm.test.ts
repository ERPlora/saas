// @vitest-environment node
// flow: ninguno — e2e harness (saas#352): the warm Django of the panel's specs (django-warm.ts), the side of this process.
// `tests/e2e/panel/django_warm.py` boots Django once and answers one JSON line per snippet (its own tests:
// config/tests/test_django_warm.py); here a stand-in that speaks the same lines checks what a spec gets back: what each
// snippet printed, trimmed as `djangoPrint` trims it, in the order asked, a failing snippet rejecting with its traceback
// and the next one still answered, and an ended process rejecting every call with what it said on its stderr.
import { describe, expect, it } from 'vitest';

import { startWarm } from './django-warm';

/** A stand-in for django_warm.py: «fail» answers a traceback, «die» ends the process, «garble» answers no JSON, the rest is echoed. */
const STAND_IN = String.raw`
const say = (answer) => process.stdout.write(JSON.stringify(answer) + '\n');
process.stderr.write('booting the stand-in\n');
say({ ready: true });
require('node:readline').createInterface({ input: process.stdin }).on('line', (line) => {
  const { code } = JSON.parse(line);
  if (code === 'fail') say({ error: 'Traceback (most recent call last):\nValueError: no such account\n' });
  else if (code === 'die') { process.stderr.write('ended by the test\n'); process.exit(7); }
  else if (code === 'garble') process.stdout.write('not json\n');
  else say({ out: '  ' + code + '\n\n' });
});
`;

const standIn = (script = STAND_IN) => startWarm(process.execPath, ['-e', script], {});

describe('startWarm', () => {
  it('answers each snippet with what it printed, trimmed as djangoPrint trims it', async () => {
    const django = await standIn();
    expect(await django.print('print(1)')).toBe('print(1)');
    expect(await django.print('a\nb')).toBe('a\nb');
  });

  it('answers snippets asked at once in the order they were asked', async () => {
    const django = await standIn();
    expect(await Promise.all(['one', 'two', 'three'].map((code) => django.print(code)))).toEqual(['one', 'two', 'three']);
  });

  it('rejects a failing snippet with its traceback, and answers the next one', async () => {
    const django = await standIn();
    await expect(django.print('fail')).rejects.toThrow(/ValueError: no such account/);
    await expect(django.print('garble')).rejects.toThrow(/answered no JSON: not json/);
    expect(await django.print('after')).toBe('after');
  });

  it('rejects the call it was answering and every later one once the process ends, with what it said', async () => {
    const django = await standIn();
    await expect(django.print('die')).rejects.toThrow(/ended \(7\)[\s\S]*ended by the test/);
    await expect(django.print('after')).rejects.toThrow(/ended \(7\)/);
  });

  it('rejects when the process ends before it is ready, with what it said', async () => {
    await expect(standIn("process.stderr.write('only runs with DEBUG=True\\n'); process.exit(1)")).rejects.toThrow(
      /ended \(1\)[\s\S]*only runs with DEBUG=True/,
    );
  });

  it('rejects when the command cannot start', async () => {
    await expect(startWarm('/no/such/python', [], {})).rejects.toThrow(/did not start/);
  });
});
