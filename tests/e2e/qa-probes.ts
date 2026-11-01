// `pnpm qa:probes --language en|es [--surface web|app] [--apps a,b] [--sample N | --all] [--out <file>]`: the skeleton
// of a probe file for the panel assistant's QA with the real model, layer 2 (panel/assistant-probes.spec.ts; plan
// docs/plans/2026-10-31-asistente-conocimiento-y-qa.md of erplora-next, §1.5). It reads the catalogue the panel offers
// on that surface (`manage.py export_assistant_catalog`) and writes one probe per sampled tool with its phrase EMPTY:
// whoever does the QA writes each one (new, natural, never one of the asks) before the spec runs. The expectation comes from
// the tool: the documentation search → «docs», a read → «read», a write → «card» cancelled; the tools of the web that
// the surface does not offer → «refused». The sample takes N tools per app (2 by default), those with fewer probes of
// the same language and surface in the corpus (tests/e2e/qa/probes/) first, then by name. Run by Node itself.
import { spawnSync } from 'node:child_process';
import { existsSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

import { DOCS_SEARCH } from './assistant-battery.ts';
import {
  type CatalogTool,
  loadProbes,
  PANEL_ROLES,
  type Probe,
  probeFiles,
  type ProbeLanguage,
  type ProbeSurface,
  PROBE_LANGUAGES,
  PROBE_SURFACES,
} from './assistant-probes.ts';

const HERE = dirname(fileURLToPath(import.meta.url));
const SAAS_DIR = resolve(HERE, '..', '..');
/** The corpus of probes the spec reads by default. */
export const CORPUS_DIR = join(HERE, 'qa', 'probes');
const USAGE =
  'usage: pnpm qa:probes --language en|es [--surface web|app] [--role account] [--apps a,b] [--sample N | --all] [--out <file>]';

export interface GeneratorOptions {
  language: ProbeLanguage;
  surface: ProbeSurface;
  role: string;
  /** The app labels to sample; all the catalogue's when empty. */
  apps: string[];
  /** Tools per app, or every tool. */
  sample: number | 'all';
  /** Where to write; `defaultOut` when empty. */
  out: string;
}

export interface GeneratorDeps {
  exportCatalog: (language: string, surface: string, role: string) => CatalogTool[];
  readCorpus: () => Probe[];
  exists: (path: string) => boolean;
  write: (path: string, text: string) => void;
  today: () => string;
  corpusDir: string;
  log: (line: string) => void;
}

class UsageError extends Error {}

/** The options of a call; a wrong one is a `UsageError` naming it. */
export function parseArgs(argv: string[]): GeneratorOptions {
  const values: Record<string, string> = {};
  let all = false;
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === '--all') {
      all = true;
      continue;
    }
    const match = /^--(language|surface|role|apps|sample|out)(?:=(.*))?$/.exec(arg);
    if (!match) throw new UsageError(`unknown argument ${arg}`);
    values[match[1]] = match[2] ?? argv[(index += 1)] ?? '';
  }
  const language = values.language ?? '';
  if (!(PROBE_LANGUAGES as readonly string[]).includes(language)) throw new UsageError('--language en|es is required');
  const surface = values.surface ?? 'web';
  if (!(PROBE_SURFACES as readonly string[]).includes(surface)) throw new UsageError('--surface must be web or app');
  const role = values.role ?? PANEL_ROLES[0];
  if (!(PANEL_ROLES as readonly string[]).includes(role)) throw new UsageError(`--role must be ${PANEL_ROLES.join(' or ')}`);
  if (all && values.sample !== undefined) throw new UsageError('--all or --sample, not both');
  const sample = Number(values.sample ?? '2');
  if (!all && !(Number.isInteger(sample) && sample >= 1)) throw new UsageError('--sample must be a whole number from 1');
  return {
    language: language as ProbeLanguage,
    surface: surface as ProbeSurface,
    role,
    apps: (values.apps ?? '')
      .split(',')
      .map((app) => app.trim())
      .filter(Boolean),
    sample: all ? 'all' : sample,
    out: values.out ?? '',
  };
}

/** The skeleton: per app (in order), the sampled tools the surface offers, then the sampled ones it does not. */
export function skeleton(options: GeneratorOptions, catalogs: { web: CatalogTool[]; surface: CatalogTool[] }, corpus: Probe[]): Probe[] {
  const offered = new Set(catalogs.surface.map((tool) => tool.name));
  const labels = [...new Set(catalogs.web.map((tool) => tool.app_label))].sort();
  const unknown = options.apps.filter((app) => !labels.includes(app));
  if (unknown.length) throw new Error(`no tools of ${unknown.join(', ')} for ${options.role} (apps: ${labels.join(', ')})`);
  const apps = options.apps.length ? labels.filter((app) => options.apps.includes(app)) : labels;
  const mine = corpus.filter((probe) => probe.language === options.language && probe.surface === options.surface);
  const covered = (tool: CatalogTool) => mine.filter((probe) => probe.tool === tool.name).length;
  const ids = new Set(corpus.map((probe) => probe.id));
  const pick = (tools: CatalogTool[]) => {
    const ordered = [...tools].sort((a, b) => covered(a) - covered(b) || a.name.localeCompare(b.name));
    return options.sample === 'all' ? ordered : ordered.slice(0, options.sample);
  };
  const probeOf = (tool: CatalogTool, absent: boolean): Probe => {
    let number = covered(tool) + 1;
    const idOf = () => `${options.language}-${options.surface}-${tool.name}-${number}`;
    while (ids.has(idOf())) number += 1;
    ids.add(idOf());
    const write = tool.kind === 'write';
    const expect = absent ? 'refused' : tool.name === DOCS_SEARCH ? 'docs' : write ? 'card' : 'read';
    const note = absent
      ? `Not offered on the ${options.surface} surface: ${tool.description}`
      : `${tool.risk === 'high' ? 'High risk. ' : ''}${tool.description}`;
    return {
      id: idOf(),
      app: tool.app_label,
      tool: tool.name,
      role: options.role,
      surface: options.surface,
      language: options.language,
      phrase: '',
      expect,
      ...(expect === 'card' ? { decide: 'cancel' as const } : {}),
      notes: note,
    };
  };
  return apps.flatMap((app) => {
    const tools = catalogs.web.filter((tool) => tool.app_label === app);
    return [
      ...pick(catalogs.surface.filter((tool) => tool.app_label === app)).map((tool) => probeOf(tool, false)),
      ...pick(tools.filter((tool) => !offered.has(tool.name))).map((tool) => probeOf(tool, true)),
    ];
  });
}

/** `<corpus>/<language>-<surface>-<day>.json`. */
export function defaultOut(options: Pick<GeneratorOptions, 'language' | 'surface'>, today: string, corpusDir: string): string {
  return join(corpusDir, `${options.language}-${options.surface}-${today}.json`);
}

/** The command: 0 written, 1 refused (a file already there, a failed export), 2 a wrong call. */
export function main(argv: string[], deps: GeneratorDeps): number {
  try {
    const options = parseArgs(argv);
    const surface = deps.exportCatalog(options.language, options.surface, options.role);
    const web = options.surface === 'web' ? surface : deps.exportCatalog(options.language, 'web', options.role);
    const probes = skeleton(options, { web, surface }, deps.readCorpus());
    const out = options.out || defaultOut(options, deps.today(), deps.corpusDir);
    if (deps.exists(out)) throw new Error(`${out} already exists: choose another --out or remove it`);
    deps.write(out, `${JSON.stringify(probes, null, 2)}\n`);
    const count = (expect: string) => probes.filter((probe) => probe.expect === expect).length;
    deps.log(`${probes.length} probes (${count('read')} read, ${count('card')} card, ${count('refused')} refused, ${count('docs')} docs) → ${out}`);
    deps.log('Next: write every phrase (new, natural, never one of the asks), then run the spec (tests/e2e/README.md).');
    return 0;
  } catch (error) {
    if (error instanceof UsageError) {
      deps.log(`${error.message}\n${USAGE}`);
      return 2;
    }
    deps.log((error as Error).message);
    return 1;
  }
}

/** The catalogue the panel offers `role` on `surface`, in `language`, as the SaaS exports it. */
function exportCatalog(language: string, surface: string, role: string): CatalogTool[] {
  const args = ['run', 'python', 'manage.py', 'export_assistant_catalog', '--language', language, '--surface', surface, '--role', role];
  const run = spawnSync('uv', args, { cwd: SAAS_DIR, encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
  if (run.status !== 0) throw new Error(`export_assistant_catalog failed (${run.status}): ${(run.stderr ?? '').trim().split('\n').slice(-5).join('\n')}`);
  return JSON.parse(run.stdout) as CatalogTool[];
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  process.exitCode = main(process.argv.slice(2), {
    exportCatalog,
    readCorpus: () => loadProbes(probeFiles(CORPUS_DIR)).map((entry) => entry.probe),
    exists: existsSync,
    write: (path, text) => writeFileSync(path, text),
    today: () => new Date().toISOString().slice(0, 10),
    corpusDir: CORPUS_DIR,
    log: (line) => console.log(line),
  });
}
