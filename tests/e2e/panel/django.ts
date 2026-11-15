import { execFile, execFileSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';

import { djangoEnv } from '../django-env';
import { startWarm, type WarmDjango } from '../django-warm';

const HERE = dirname(fileURLToPath(import.meta.url));
export const SAAS_DIR = resolve(HERE, '..', '..', '..');

/**
 * `tests/e2e/panel/<script> <args…>` (`panel_seed.py seed|clear`, `assistant_seed.py <action> <provider address>`,
 * `whatsapp_hub_seed.py <a> <b> --used N`…), against the run's database (DEBUG on) with `env` over it (`MAILING`,
 * another stack's database): the last line it printed, where the seeds that tell what they made print it.
 */
export function runSeed(script: string, args: string | readonly string[], env: Readonly<Record<string, string>> = {}): string {
  const out = execFileSync('uv', ['run', 'python', `tests/e2e/panel/${script}`, ...[args].flat()], {
    cwd: SAAS_DIR,
    env: { ...djangoEnv(true), ...env },
    encoding: 'utf8',
    stdio: 'pipe',
  });
  return out.trim().split('\n').at(-1) ?? '';
}

const DJANGO_BOOT = 'import django,os;os.environ.setdefault("DJANGO_SETTINGS_MODULE","config.settings");django.setup()';

/**
 * What `code` prints, run with Django set up against the run's database (DEBUG on): the local one of `.env`,
 * or the stack's own (stack.ts). For what a spec reads from the SaaS's side and no page shows.
 *
 * It blocks this process until `code` ends, and the Hub a spec plays (`startHubDouble`) lives in this process: code
 * that calls that Hub runs with `djangoPrintAsync`, or every call waits out its timeout unanswered (saas#176).
 * Each call boots Django cold: about 1 s on an idle machine, 57 s and 88 s on a loaded one, and the test's timeout
 * cannot fire until it returns (saas#346). Inside a test, read what the panel shows through its API, and what only
 * Django knows once for the spec, in a hook.
 */
export function djangoPrint(code: string): string {
  return execFileSync('uv', ['run', 'python', '-c', `${DJANGO_BOOT}\n${code}`], {
    cwd: SAAS_DIR,
    env: djangoEnv(true),
    encoding: 'utf8',
    // stderr kept, not shown: uv's warnings; a failing snippet's traceback travels in the thrown error.
    stdio: ['ignore', 'pipe', 'pipe'],
  }).trim();
}

const execFileAsync = promisify(execFile);

/**
 * `djangoPrint` without blocking this process: the Hub the spec plays answers while `code` runs. For code that calls
 * it, such as a pass of `reconcile_hub_states`. A failing snippet rejects, its traceback in the error.
 */
export async function djangoPrintAsync(code: string): Promise<string> {
  const { stdout } = await execFileAsync('uv', ['run', 'python', '-c', `${DJANGO_BOOT}\n${code}`], {
    cwd: SAAS_DIR,
    env: djangoEnv(true),
    encoding: 'utf8',
  });
  return stdout.trim();
}

const warm = new Map<string, Promise<WarmDjango>>();

/**
 * This worker's warm Django (`tests/e2e/panel/django_warm.py`, django-warm.ts) against the run's database (DEBUG on) with
 * `env` over it (`MAILING`): started on the first call and kept for the worker; another `env`, another process. A spec
 * awaits it in a `beforeAll` (its first `djangoPrintWarm` there does), so that its boot is on no test's clock.
 */
export function warmDjango(env: Readonly<Record<string, string>> = {}): Promise<WarmDjango> {
  const key = JSON.stringify(env);
  let django = warm.get(key);
  if (!django) {
    django = startWarm('uv', ['run', 'python', 'tests/e2e/panel/django_warm.py'], {
      cwd: SAAS_DIR,
      env: { ...djangoEnv(true), ...env },
    });
    warm.set(key, django);
  }
  return django;
}

/**
 * `djangoPrint` for inside a test: what `code` prints, run by this worker's warm Django (`warmDjango`), so the test pays
 * no Django boot and this process never blocks (saas#352). The same snippet reads the same values: each one runs as
 * `python -c` runs it after `django.setup()`; a failing one rejects with its traceback.
 */
export async function djangoPrintWarm(code: string, env: Readonly<Record<string, string>> = {}): Promise<string> {
  return (await warmDjango(env)).print(code);
}

/**
 * `runSeed` for inside a test (or a `beforeEach`): `tests/e2e/panel/<script> <args…>` run as its command line runs it
 * (as `__main__`, with its `sys.argv`) by this worker's warm Django for `env` (`warmDjango`), so the test pays no Django
 * boot and this process never blocks (saas#355); the last line it printed. A seed that exits with a reason rejects.
 */
export async function runSeedWarm(
  script: string,
  args: string | readonly string[],
  env: Readonly<Record<string, string>> = {},
): Promise<string> {
  const argv = JSON.stringify([`tests/e2e/panel/${script}`, ...[args].flat()]);
  const out = await djangoPrintWarm(
    [
      'import runpy, sys',
      'argv, path = sys.argv, list(sys.path)',
      `sys.argv = ${argv}`,
      'try:',
      '    runpy.run_path(sys.argv[0], run_name="__main__")',
      'except SystemExit as exited:',
      '    if exited.code not in (None, 0): raise',
      'finally:',
      '    sys.argv, sys.path[:] = argv, path',
    ].join('\n'),
    env,
  );
  return out.split('\n').at(-1) ?? '';
}
