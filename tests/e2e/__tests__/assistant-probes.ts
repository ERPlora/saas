// What the tests of the assistant's QA probes share (assistant-probes.test.ts, assistant-probes.verdict.test.ts):
// a probe, what the panel showed for it and a tool that ran.
import type { Turns } from '../assistant-turns';
import type { Probe, ProbeObserved } from '../assistant-probes';

export const probe = (overrides: Partial<Probe> = {}): Probe => ({
  id: 'es-web-hubs.business.list-1',
  app: 'hubs',
  tool: 'hubs.business.list',
  role: 'account',
  surface: 'web',
  language: 'es',
  phrase: '¿cuántos locales llevo dados de alta?',
  expect: 'read',
  ...overrides,
});

export const NO_TURNS: Turns = { tools: [], cards: [], citations: [], errors: [] };

export const observed = (overrides: Partial<ProbeObserved> = {}): ProbeObserved => ({
  answer: '',
  links: [],
  notices: [],
  failures: [],
  turns: NO_TURNS,
  events: [],
  screenshot: '',
  ...overrides,
});

export const ran = (name: string, kind: 'query' | 'command', outcome = 'ok', code = '') => ({ name, kind, outcome, code });
