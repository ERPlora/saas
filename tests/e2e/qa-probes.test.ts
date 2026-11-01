// @vitest-environment node
// `pnpm qa:probes`: the skeleton of a probe file from the exported catalogue (plan 2026-10-31-asistente-conocimiento-y-qa
// §1.5 of erplora-next): one probe per sampled tool, its phrase empty, to be written by hand.
import { describe, expect, it } from 'vitest';

import type { CatalogTool, Probe } from './assistant-probes';
import { defaultOut, type GeneratorDeps, main, parseArgs, skeleton } from './qa-probes';

const tool = (name: string, kind: 'read' | 'write', risk: 'normal' | 'high' = 'normal'): CatalogTool => ({
  name,
  tool_name: name.replace(/\./g, '__'),
  app_label: name.split('.')[0],
  kind,
  permission: `${name.split('.')[0]}.view`,
  risk,
  description: `What ${name} does.`,
  asks: ['one', 'two'],
  input_schema: {},
});

const WEB = [
  tool('accounts.session.list', 'read'),
  tool('assistant.docs.search', 'read'),
  tool('billing.invoice.list', 'read'),
  tool('billing.plan.cancel', 'write', 'high'),
  tool('billing.store.catalog', 'read'),
  tool('hubs.business.create', 'write', 'high'),
  tool('hubs.business.get', 'read'),
  tool('hubs.business.list', 'read'),
];
const APP = WEB.filter((entry) => !['billing.plan.cancel', 'billing.store.catalog'].includes(entry.name));

const existing = (id: string, tool: string, language: 'en' | 'es' = 'es', surface: 'web' | 'app' = 'web'): Probe => ({
  id,
  app: tool.split('.')[0],
  tool,
  role: 'account',
  surface,
  language,
  phrase: 'written',
  expect: 'read',
});

describe('parseArgs', () => {
  it('reads the language, the surface, the apps and the sample (2 per app by default)', () => {
    expect(parseArgs(['--language', 'es'])).toEqual({ language: 'es', surface: 'web', role: 'account', apps: [], sample: 2, out: '' });
    expect(parseArgs(['--language=en', '--surface', 'app', '--apps', 'hubs, billing', '--sample', '3', '--out', 'x.json'])).toEqual({
      language: 'en',
      surface: 'app',
      role: 'account',
      apps: ['hubs', 'billing'],
      sample: 3,
      out: 'x.json',
    });
    expect(parseArgs(['--language', 'es', '--all']).sample).toBe('all');
  });

  it('refuses what it does not know, a missing language, a bad sample and --all with --sample', () => {
    expect(() => parseArgs([])).toThrow('--language en|es is required');
    expect(() => parseArgs(['--language', 'fr'])).toThrow('--language en|es is required');
    expect(() => parseArgs(['--language', 'es', '--surface', 'tablet'])).toThrow('--surface must be web or app');
    expect(() => parseArgs(['--language', 'es', '--sample', '0'])).toThrow('--sample must be a whole number from 1');
    expect(() => parseArgs(['--language', 'es', '--sample', '2', '--all'])).toThrow('--all or --sample, not both');
    expect(() => parseArgs(['--language', 'es', '--role', 'owner'])).toThrow('--role must be account');
    expect(() => parseArgs(['--language', 'es', '--fast'])).toThrow('unknown argument --fast');
  });
});

describe('skeleton', () => {
  const options = { language: 'es' as const, surface: 'web' as const, role: 'account', apps: [], sample: 2 as const, out: '' };

  it('samples tools per app, by name, with the expectation of their kind and an empty phrase', () => {
    const probes = skeleton(options, { web: WEB, surface: WEB }, []);
    expect(probes.map((probe) => [probe.id, probe.expect, probe.decide])).toEqual([
      ['es-web-accounts.session.list-1', 'read', undefined],
      ['es-web-assistant.docs.search-1', 'docs', undefined],
      ['es-web-billing.invoice.list-1', 'read', undefined],
      ['es-web-billing.plan.cancel-1', 'card', 'cancel'],
      ['es-web-hubs.business.create-1', 'card', 'cancel'],
      ['es-web-hubs.business.get-1', 'read', undefined],
    ]);
    expect(probes[3]).toEqual({
      id: 'es-web-billing.plan.cancel-1',
      app: 'billing',
      tool: 'billing.plan.cancel',
      role: 'account',
      surface: 'web',
      language: 'es',
      phrase: '',
      expect: 'card',
      decide: 'cancel',
      notes: 'High risk. What billing.plan.cancel does.',
    });
  });

  it('prefers the tools with fewer probes of the same language and surface, and numbers the ids after them', () => {
    const corpus = [
      existing('es-web-hubs.business.create-1', 'hubs.business.create'),
      existing('es-web-hubs.business.get-1', 'hubs.business.get'),
      existing('es-web-hubs.business.get-2', 'hubs.business.get'),
      existing('en-web-hubs.business.list-1', 'hubs.business.list', 'en'),
    ];
    const probes = skeleton({ ...options, apps: ['hubs'] }, { web: WEB, surface: WEB }, corpus);
    expect(probes.map((probe) => probe.id)).toEqual(['es-web-hubs.business.list-1', 'es-web-hubs.business.create-2']);
  });

  it('takes every tool with --all, and only the apps asked', () => {
    const probes = skeleton({ ...options, sample: 'all', apps: ['billing'] }, { web: WEB, surface: WEB }, []);
    expect(probes.map((probe) => probe.tool)).toEqual(['billing.invoice.list', 'billing.plan.cancel', 'billing.store.catalog']);
  });

  it('adds «refused» probes for the tools the surface does not offer', () => {
    const probes = skeleton({ ...options, surface: 'app', apps: ['billing'] }, { web: WEB, surface: APP }, []);
    expect(probes.map((probe) => [probe.id, probe.expect, probe.notes])).toEqual([
      ['es-app-billing.invoice.list-1', 'read', 'What billing.invoice.list does.'],
      ['es-app-billing.plan.cancel-1', 'refused', 'Not offered on the app surface: What billing.plan.cancel does.'],
      ['es-app-billing.store.catalog-1', 'refused', 'Not offered on the app surface: What billing.store.catalog does.'],
    ]);
  });

  it('refuses an app without tools', () => {
    expect(() => skeleton({ ...options, apps: ['fiscal'] }, { web: WEB, surface: WEB }, [])).toThrow('no tools of fiscal');
  });
});

describe('defaultOut', () => {
  it('names the file by language, surface and day, under the corpus', () => {
    expect(defaultOut({ language: 'es', surface: 'app' }, '2026-11-01', '/repo/tests/e2e/qa/probes')).toBe(
      '/repo/tests/e2e/qa/probes/es-app-2026-11-01.json',
    );
  });
});

describe('main', () => {
  function deps(overrides: Partial<GeneratorDeps> = {}) {
    const written: Record<string, string> = {};
    const lines: string[] = [];
    const exported: string[] = [];
    const base: GeneratorDeps = {
      exportCatalog: (language, surface, role) => {
        exported.push(`${language} ${surface} ${role}`);
        return surface === 'web' ? WEB : APP;
      },
      readCorpus: () => [],
      exists: (path) => path in written,
      write: (path, text) => {
        written[path] = text;
      },
      today: () => '2026-11-01',
      corpusDir: '/repo/tests/e2e/qa/probes',
      log: (line) => lines.push(line),
      ...overrides,
    };
    return { base, written, lines, exported };
  }

  it('exports the catalogues, writes the skeleton and says what to do next', () => {
    const { base, written, lines, exported } = deps();
    expect(main(['--language', 'es', '--surface', 'app', '--apps', 'billing'], base)).toBe(0);
    expect(exported).toEqual(['es app account', 'es web account']);
    const path = '/repo/tests/e2e/qa/probes/es-app-2026-11-01.json';
    expect(written[path].endsWith('\n')).toBe(true);
    expect((JSON.parse(written[path]) as Probe[]).map((probe) => probe.tool)).toEqual([
      'billing.invoice.list',
      'billing.plan.cancel',
      'billing.store.catalog',
    ]);
    expect(lines.join('\n')).toContain(`3 probes (1 read, 0 card, 2 refused, 0 docs) → ${path}`);
    expect(lines.join('\n')).toContain('write every phrase');
  });

  it('exports the web catalogue once for the web surface', () => {
    const { base, exported } = deps();
    expect(main(['--language', 'en', '--out', '/tmp/x.json'], base)).toBe(0);
    expect(exported).toEqual(['en web account']);
  });

  it('never overwrites a file and explains a wrong call', () => {
    const { base, lines } = deps({ exists: () => true });
    expect(main(['--language', 'es'], base)).toBe(1);
    expect(lines.at(-1)).toContain('already exists');
    expect(main(['--surface', 'web'], base)).toBe(2);
    expect(lines.at(-1)).toContain('--language en|es is required');
    expect(lines.at(-1)).toContain('usage: pnpm qa:probes');
  });
});
