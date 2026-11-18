// @vitest-environment node
import { spawnSync, type SpawnSyncReturns } from 'node:child_process';
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { afterAll, beforeAll, describe, expect, it } from 'vitest';

const SAAS_DIR = dirname(fileURLToPath(import.meta.url));
const SCRIPT = join(SAAS_DIR, 'typecheck-declarations.ts');
/** A hand-written types file with both kinds of broken import: a module that does not exist and a name
 * the other file does not export. */
const PROBE = [
  "import type { Missing } from './no-such-module';",
  `import type { NotExported } from '${join(SAAS_DIR, 'frontend', 'sdk-types', 'store')}';`,
  'export type Probe = Missing | NotExported;',
  '',
].join('\n');
/** TS2307: «Cannot find module». TS2305: «Module has no exported member». */
const BROKEN_IMPORTS = [2305, 2307];

function check(project: string): SpawnSyncReturns<string> {
  const run = spawnSync(process.execPath, [SCRIPT, project], {
    cwd: SAAS_DIR,
    encoding: 'utf8',
    timeout: 170_000,
  });
  if (run.error) throw run.error;
  return run;
}

/** `<file>(line,col): error TS<code>` lines of the report. */
function errors(run: SpawnSyncReturns<string>): { file: string; code: number }[] {
  return `${run.stdout}\n${run.stderr}`.split('\n').flatMap((line) => {
    const match = /^(.+?)\(\d+,\d+\): error TS(\d+):/.exec(line);
    return match ? [{ file: match[1], code: Number(match[2]) }] : [];
  });
}

describe('the check of the hand-written declaration files (typecheck-declarations.ts)', () => {
  let probeDir = '';
  let probed: SpawnSyncReturns<string>;

  // The SPA's project plus a probe `.d.ts`, in a directory of its own under node_modules (ignored by git).
  beforeAll(() => {
    const tmp = join(SAAS_DIR, 'node_modules', '.tmp');
    mkdirSync(tmp, { recursive: true });
    probeDir = mkdtempSync(join(tmp, 'declarations-probe-'));
    writeFileSync(join(probeDir, 'probe.d.ts'), PROBE);
    const config = join(probeDir, 'tsconfig.json');
    writeFileSync(config, JSON.stringify({ extends: join(SAAS_DIR, 'tsconfig.app.json'), files: ['probe.d.ts'] }));
    probed = check(config);
  }, 180_000);

  afterAll(() => {
    if (probeDir) rmSync(probeDir, { recursive: true, force: true });
  });

  it('fails on a broken import in a declaration file of the panel', () => {
    expect(probed.status).toBe(1);
    const probe = errors(probed).filter(({ file }) => file.endsWith('probe.d.ts'));
    expect(probe.map(({ code }) => code).sort()).toEqual(BROKEN_IMPORTS);
  });

  it("reports only the panel's own files, never the packages' declarations", () => {
    expect(errors(probed).filter(({ file }) => !file.endsWith('probe.d.ts'))).toEqual([]);
  });

  it("passes the panel's declaration files as they are", () => {
    const run = check(join(SAAS_DIR, 'tsconfig.app.json'));
    expect(errors(run)).toEqual([]);
    expect(run.status).toBe(0);
  }, 180_000);

  it('fails when the project it is given cannot be read', () => {
    const run = check(join(SAAS_DIR, 'tsconfig.missing.json'));
    expect(run.status).not.toBe(0);
    expect(run.stderr).toContain('tsconfig.missing.json');
  });

  it('fails when the project it is given has errors of its own', () => {
    const config = join(probeDir, 'tsconfig.broken.json');
    writeFileSync(config, JSON.stringify({ extends: './missing-base.json', files: ['probe.d.ts'] }));
    const run = check(config);
    expect(run.status).not.toBe(0);
    expect(run.stderr).toContain('missing-base.json');
  });
});
