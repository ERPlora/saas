// @vitest-environment node
// `pnpm typecheck` covers the e2e: `tests/e2e/tsconfig.json` is the project of every `.ts` of this
// folder (specs, fixtures, helpers and their Vitest tests), with `node` in its `types`, and the
// typecheck script runs it after the frontend's. Without it Playwright only strips the types of a spec,
// so a type error in one ran, and passed `pnpm typecheck`, unnoticed (the Vitest project reaches 3 of
// these files through `vite.config.test.ts`).
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

import ts from 'typescript';
import { describe, expect, it } from 'vitest';

const E2E_DIR = dirname(fileURLToPath(import.meta.url));
const SAAS_DIR = resolve(E2E_DIR, '..', '..');
/** A panel spec: only Playwright runs it, nothing else imports it. */
const PANEL_SPEC = join(E2E_DIR, 'panel', 'login.spec.ts');

/** Every `.ts` under tests/e2e, relative to the saas, except the run artifacts (`.artifacts/`, ignored by git). */
function e2eSources(): string[] {
  return readdirSync(E2E_DIR, { recursive: true, encoding: 'utf8' })
    .filter((path) => path.endsWith('.ts') && !path.split(sep).includes('.artifacts'))
    .map((path) => relative(SAAS_DIR, join(E2E_DIR, path)))
    .sort();
}

/** The parsed `tsconfig.json` at `path`; a config that cannot be read or has errors throws. */
function project(path: string): ts.ParsedCommandLine {
  const parsed = ts.getParsedCommandLineOfConfigFile(path, undefined, {
    ...ts.sys,
    onUnRecoverableConfigFileDiagnostic: (diagnostic) => {
      throw new Error(ts.flattenDiagnosticMessageText(diagnostic.messageText, '\n'));
    },
  });
  if (!parsed) throw new Error(`${path} could not be parsed`);
  if (parsed.errors.length > 0) {
    throw new Error(parsed.errors.map((e) => ts.flattenDiagnosticMessageText(e.messageText, '\n')).join('\n'));
  }
  return parsed;
}

describe('the e2e type-check project (tests/e2e/tsconfig.json)', () => {
  it('takes in every .ts of tests/e2e', () => {
    const checked = new Set(project(join(E2E_DIR, 'tsconfig.json')).fileNames.map((f) => relative(SAAS_DIR, f)));
    expect(e2eSources().length).toBeGreaterThan(0);
    expect(e2eSources().filter((source) => !checked.has(source))).toEqual([]);
  });

  it('reports a type error planted in a panel spec', () => {
    const e2e = project(join(E2E_DIR, 'tsconfig.json'));
    const planted = `${readFileSync(PANEL_SPEC, 'utf8')}\nexport const planted: number = 'not a number';\n`;
    const host = ts.createCompilerHost(e2e.options);
    const getSourceFile = host.getSourceFile.bind(host);
    host.getSourceFile = (fileName, languageVersion, onError, shouldCreate) =>
      resolve(fileName) === PANEL_SPEC
        ? ts.createSourceFile(fileName, planted, languageVersion)
        : getSourceFile(fileName, languageVersion, onError, shouldCreate);
    const program = ts.createProgram({ rootNames: e2e.fileNames, options: e2e.options, host });
    const spec = program.getSourceFiles().find((file) => resolve(file.fileName) === PANEL_SPEC);
    expect(spec, 'the panel spec is not in the e2e project').toBeDefined();
    // TS2322: Type 'string' is not assignable to type 'number'.
    expect(program.getSemanticDiagnostics(spec).map((d) => d.code)).toContain(2322);
  }, 60_000);

  // The SPA's project never gets Node's types, not even through an import (tsconfig.test.ts).
  it("gives Node's types to the e2e and does not add them to the SPA's types", () => {
    expect(project(join(E2E_DIR, 'tsconfig.json')).options.types).toContain('node');
    expect(project(join(SAAS_DIR, 'tsconfig.app.json')).options.types ?? []).not.toContain('node');
  });

  it('is run by pnpm typecheck, as the CI runs it', () => {
    const { scripts } = JSON.parse(readFileSync(join(SAAS_DIR, 'package.json'), 'utf8')) as {
      scripts: Record<string, string>;
    };
    expect(scripts.typecheck.split('&&').map((step) => step.trim())).toContain('tsc --noEmit -p tests/e2e');
  });
});
