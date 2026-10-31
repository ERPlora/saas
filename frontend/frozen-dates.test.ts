// A test that writes a calendar date (an ISO date-time such as a module's `valid_until`) next to code that
// compares it with now passes until the real clock reaches that date, and then fails with nothing changed:
// StoreShop's «Keep» vanished at 12:00 UTC on 2026-10-31 and the failing `test / frontend` blocked the deploy of
// main. So every test file Vitest runs that writes an ISO date-time either freezes the clock
// (`vi.useFakeTimers({ toFake: ['Date'] })` + `vi.setSystemTime(…)`, or `vi.useFakeTimers({ now: … })`) or says,
// on a line of its own, that its dates are only data no code compares with now: `// clock: data only`.
// A guard over the files of `vite.config.ts` `test.include`, so a new test cannot bring the trap back.
// clock: data only — the samples below are what the guard reads, not dates any code compares with now.
import { globSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import viteConfig from '../vite.config';

const SAAS_DIR = join(dirname(fileURLToPath(import.meta.url)), '..');

/** An ISO date-time literal (`2026-10-31T12:00:00Z`): a date pinned to the calendar, not to the test's clock. */
const ISO_DATE_TIME = /\b20\d\d-[01]\d-[0-3]\dT/;
/** The clock set to a fixed instant: `vi.setSystemTime(…)` or fake timers that start at a given `now`. */
const FROZEN_CLOCK = /\bvi\.setSystemTime\(|\bvi\.useFakeTimers\(\{[^)]*\bnow\s*:/;
/** The file's own word that its dates are only data (formatted, sent, compared with each other). */
const DATA_ONLY = /^[ \t]*\/\/ clock: data only\b/m;

/** Whether a test file's result may depend on the day it runs: it pins a date and leaves the clock real. */
function clockBound(source: string): boolean {
  return ISO_DATE_TIME.test(source) && !FROZEN_CLOCK.test(source) && !DATA_ONLY.test(source);
}

/** The test files Vitest runs (`test.include` of vite.config.ts), relative to saas/. */
function testFiles(): string[] {
  const include = viteConfig.test?.include ?? [];
  return [...new Set(globSync(include, { cwd: SAAS_DIR }))].sort();
}

describe('tests and the real clock', () => {
  it('reads a pinned date with a real clock as bound to the day, and a frozen clock or the data-only word as safe', () => {
    const pinned = "const out = { valid_until: '2026-10-31T12:00:00Z' };\n";
    expect(clockBound(pinned)).toBe(true);
    expect(clockBound(`${pinned}vi.useFakeTimers({ toFake: ['Date'] });\nvi.setSystemTime(new Date());\n`)).toBe(false);
    expect(clockBound(`${pinned}vi.useFakeTimers({ now: new Date('2026-10-20T10:00:00Z') });\n`)).toBe(false);
    // Fake timers without a `now` start at the real time: the date still runs out.
    expect(clockBound(`${pinned}vi.useFakeTimers();\n`)).toBe(true);
    expect(clockBound(`// clock: data only — shown, never compared with now\n${pinned}`)).toBe(false);
    // The word counts on a line of its own, not quoted inside a string or after code.
    expect(clockBound(`${pinned}const note = '// clock: data only';\n`)).toBe(true);
    expect(clockBound(`${pinned}foo(); // clock: data only\n`)).toBe(true);
    // A plain day or a number with dashes is not a date-time.
    expect(clockBound("const day = '2026-10-31';\nconst ref = 'ERP-2026-00123';\n")).toBe(false);
  });

  it('reads the files Vitest runs, this one among them', () => {
    const files = testFiles();
    expect(files).toContain('frontend/frozen-dates.test.ts');
    expect(files).toContain('billing/frontend/components/StoreShop.test.ts');
    expect(files.some((file) => file.includes('node_modules'))).toBe(false);
  });

  it('no test file pins a date and leaves the clock real without saying its dates are only data', () => {
    const bound = testFiles().filter((file) => clockBound(readFileSync(join(SAAS_DIR, file), 'utf8')));
    expect(bound).toEqual([]);
  });
});
