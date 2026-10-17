// @vitest-environment node
// The SPA's type-check project has the browser's types and never Node's: `tsconfig.app.json` holds the
// sources that run in the browser, `tsconfig.node.json` the root's config files and
// `tsconfig.vitest.json` the Vitest tests and their helpers (Vue's create-vue layout), all three
// referenced by `tsconfig.json` and run by `pnpm typecheck`. With one project for everything, the
// tests' and the config's imports (vitest, vite, happy-dom) and `@types/qrcode` brought Node's
// globals into the SPA: a `process.env` in a page passed vue-tsc and broke in the browser.
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import ts from 'typescript';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';

import { FRONTEND_APPS } from './vite.config';

const SAAS_DIR = dirname(fileURLToPath(import.meta.url));
const VUE_TSC = createRequire(import.meta.url).resolve('vue-tsc/bin/vue-tsc.js');
/** The projects `tsconfig.json` references, which `vue-tsc --build` checks. */
const PROJECTS = ['tsconfig.app.json', 'tsconfig.node.json', 'tsconfig.vitest.json'];
/** A browser source reading Node's `process`: the SPA's project must reject it. */
const PROBE = 'export const probe = process.env.ERPLORA_PROBE;\n';
/** TS2580 / TS2591: «Cannot find name 'process'» (Node's types are missing). */
const MISSING_NODE_NAME = [2580, 2591];

/** The parsed config at `path` (`.vue` files included, as vue-tsc reads them); errors throw. */
function project(path: string): ts.ParsedCommandLine {
  const parsed = ts.getParsedCommandLineOfConfigFile(
    path,
    undefined,
    {
      ...ts.sys,
      onUnRecoverableConfigFileDiagnostic: (diagnostic) => {
        throw new Error(ts.flattenDiagnosticMessageText(diagnostic.messageText, '\n'));
      },
    },
    undefined,
    undefined,
    [{ extension: 'vue', isMixedContent: true, scriptKind: ts.ScriptKind.Deferred }],
  );
  if (!parsed) throw new Error(`${path} could not be parsed`);
  if (parsed.errors.length > 0) {
    throw new Error(parsed.errors.map((e) => ts.flattenDiagnosticMessageText(e.messageText, '\n')).join('\n'));
  }
  return parsed;
}

function rootFiles(name: string): Set<string> {
  return new Set(project(join(SAAS_DIR, name)).fileNames.map((file) => relative(SAAS_DIR, resolve(file))));
}

/** Every source `pnpm typecheck` checked with a single project: the root's scripts and every frontend. */
function typedSources(): string[] {
  const typed = (name: string) => /\.(ts|js|vue)$/.test(name);
  const root = readdirSync(SAAS_DIR).filter(typed);
  const frontends = ['frontend', ...FRONTEND_APPS.map((app) => join(app, 'frontend'))].flatMap((dir) =>
    readdirSync(join(SAAS_DIR, dir), { recursive: true, encoding: 'utf8' })
      .map((path) => join(dir, path))
      .filter((path) => typed(path) && !path.startsWith(join('frontend', 'dist'))),
  );
  return [...root, ...frontends].sort();
}

function scripts(): Record<string, string> {
  return (JSON.parse(readFileSync(join(SAAS_DIR, 'package.json'), 'utf8')) as { scripts: Record<string, string> })
    .scripts;
}

describe("the SPA's type-check project (tsconfig.app.json)", () => {
  type Diagnostic = { file: string; code: number };
  let probeDir = '';
  let probeFile = '';
  let diagnostics: Diagnostic[] = [];
  let checkedFiles: string[] = [];

  // vue-tsc on the SPA's project plus a probe file, in a directory of its own under node_modules (ignored
  // by git), where the project's `types` resolve as they do from the root. Removed after the run.
  beforeAll(() => {
    const tmp = join(SAAS_DIR, 'node_modules', '.tmp');
    mkdirSync(tmp, { recursive: true });
    probeDir = mkdtempSync(join(tmp, 'spa-node-probe-'));
    probeFile = join(probeDir, 'probe.ts');
    writeFileSync(probeFile, PROBE);
    const config = join(probeDir, 'tsconfig.json');
    writeFileSync(config, JSON.stringify({ extends: join(SAAS_DIR, 'tsconfig.app.json'), files: ['probe.ts'] }));
    const run = spawnSync(process.execPath, [VUE_TSC, '--noEmit', '--pretty', 'false', '--listFiles', '-p', config], {
      cwd: SAAS_DIR,
      encoding: 'utf8',
      timeout: 170_000,
    });
    if (run.error) throw run.error;
    const lines = `${run.stdout}\n${run.stderr}`.split('\n');
    // `<file>(line,col): error TS…`, or `error TS…` alone for the config's own (a missing `extends`).
    diagnostics = lines.flatMap((line) => {
      const match = /^(?:(.+?)\(\d+,\d+\): )?error TS(\d+):/.exec(line);
      return match ? [{ file: match[1] ? resolve(SAAS_DIR, match[1]) : '', code: Number(match[2]) }] : [];
    });
    checkedFiles = lines.filter((line) => line.startsWith('/') && existsSync(line));
  }, 180_000);

  afterAll(() => {
    if (probeDir) rmSync(probeDir, { recursive: true, force: true });
  });

  it("rejects Node's `process` in a browser source", () => {
    const probe = diagnostics.filter(({ file }) => file === probeFile).map(({ code }) => code);
    expect(probe).toHaveLength(1);
    expect(MISSING_NODE_NAME).toContain(probe[0]);
  });

  it('typechecks the rest of the SPA clean, so the only error is the probe', () => {
    expect(checkedFiles.length).toBeGreaterThan(0);
    expect(diagnostics.filter(({ file }) => file !== probeFile)).toEqual([]);
  });

  it("never takes in Node's types, whatever a page imports", () => {
    expect(checkedFiles.length).toBeGreaterThan(0);
    expect(checkedFiles.filter((file) => file.includes('/@types/node/'))).toEqual([]);
  });

  it('holds no test, test helper or config file: those run in Node', () => {
    const spa = [...rootFiles('tsconfig.app.json')];
    expect(spa.filter((file) => /\.test\.ts$|(^|\/)__tests__\//.test(file) || !file.includes('/'))).toEqual([]);
    expect(project(join(SAAS_DIR, 'tsconfig.app.json')).options.types ?? []).not.toContain('node');
  });
});

describe('the type-check projects of pnpm typecheck (tsconfig.json)', () => {
  it('is a solution that only references the SPA, config and Vitest projects', () => {
    const solution = JSON.parse(readFileSync(join(SAAS_DIR, 'tsconfig.json'), 'utf8')) as {
      files?: string[];
      include?: string[];
      references?: { path: string }[];
    };
    expect(solution.files).toEqual([]);
    expect(solution.include).toBeUndefined();
    expect((solution.references ?? []).map(({ path }) => path.replace(/^\.\//, '')).sort()).toEqual(
      [...PROJECTS].sort(),
    );
  });

  it('typechecks every source the single project did: the root, the entry and every app frontend', () => {
    const checked = new Set(PROJECTS.flatMap((name) => [...rootFiles(name)]));
    expect(typedSources().length).toBeGreaterThan(0);
    expect(typedSources().filter((source) => !checked.has(source))).toEqual([]);
  });

  it("gives Node's types to the config and the Vitest tests only", () => {
    expect(project(join(SAAS_DIR, 'tsconfig.node.json')).options.types).toContain('node');
    expect(project(join(SAAS_DIR, 'tsconfig.vitest.json')).options.types).toContain('node');
  });

  it('is run by pnpm typecheck and before every pnpm build, with the e2e after it', () => {
    const steps = (script: string) => script.split('&&').map((step) => step.trim());
    expect(steps(scripts().typecheck)).toEqual(['vue-tsc --build', 'tsc --noEmit -p tests/e2e']);
    expect(steps(scripts().build)[0]).toBe('vue-tsc --build');
  });
});
