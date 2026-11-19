// @vitest-environment node
// The record a run of the panel's probes keeps of each turn, to compare models (the Hub's bench reports share the
// format, and its `pnpm -s qa:bench-compare` reads both): the calls with their arguments, the verdict, what the account
// spent, the latency, and whether the tool was offered at all.
// clock: data only
import { describe, expect, it } from 'vitest';

import {
  benchModel,
  type BenchMeta,
  benchTurn,
  callsOf,
  type Measured,
  OFFERED_HEAD,
  offeredCode,
  parseUsage,
  spentBetween,
  toolKind,
  usageCode,
  withTurn,
} from './assistant-bench';
import { summarizeTurns } from './assistant-battery';
import type { CatalogTool, Probe, ProbeResult } from './assistant-probes';

const sse = (...frames: object[]): string => frames.map((frame) => `data: ${JSON.stringify(frame)}\n\n`).join('');

const PROBE: Probe = {
  id: 'es-web-hubs.business.create-1',
  app: 'hubs',
  tool: 'hubs.business.create',
  role: 'account',
  surface: 'web',
  language: 'es',
  phrase: 'quiero abrir otro local, llámalo Bar Norte',
  expect: 'card',
};

/** The model asks for the write, the card shows and the account cancels it. */
const CARD = [
  sse(
    { type: 'done', append: [], pending: [{ call_id: 'c1', name: 'hubs__business__create', arguments: '{"name":"Bar Norte"}' }], continuation: 't1' },
  ),
  sse(
    { type: 'confirm', card: { operation: 'hubs.business.create', risk: 'normal', confirm_word: '' }, call: { call_id: 'c1', name: 'hubs__business__create', arguments: '{"name":"Bar Norte"}' } },
    { type: 'done', append: [], pending: [{ call_id: 'c1', name: 'hubs__business__create', arguments: '{"name":"Bar Norte"}' }], continuation: 't1' },
  ),
  sse(
    { type: 'executed', call_id: 'c1', name: 'hubs.business.create', kind: 'command', outcome: 'cancelled', code: '' },
    { type: 'text', text: 'No lo he hecho.' },
    { type: 'done', append: [], pending: [], continuation: null },
  ),
];

function result(overrides: Partial<ProbeResult> = {}): ProbeResult {
  return {
    probe: PROBE,
    source: 'tests/e2e/qa/probes/es-web.json',
    observed: { answer: 'No lo he hecho.', links: [], notices: [], failures: [], turns: summarizeTurns(CARD), events: [], screenshot: 'x.png' },
    verdict: 'pass',
    reasons: [],
    ...overrides,
  };
}

const MEASURED: Measured = {
  bodies: CARD,
  latencyMs: 3100,
  usage: { tokensIn: 4000, tokensOut: 120, tokensEmbedding: 0, costUsd: 0.0018 },
  offered: ['hubs.business.list', 'assistant.docs.search', 'hubs.business.create'],
  kind: 'write',
  error: null,
};

const SEEDED = {
  model: 'qwen3.7-plus (Qwen)',
  fallback: 'gpt-5.4-mini (OpenAI)',
  answer: { provider: 'qwen', kind: 'openai', model: 'qwen3.7-plus', base_url: 'https://q.example.com/v1', price_in: null, price_out: null, fallback: 'gpt-5.4-mini' },
};

const META: BenchMeta = {
  product: 'saas',
  run: 'run-1',
  date: '2026-11-19T10:00:00.000Z',
  model: benchModel(SEEDED.answer),
  files: ['tests/e2e/qa/probes/es-web.json'],
  corpus: 15,
  sample: null,
};

describe('callsOf', () => {
  it('lists every tool the model called, in order, once each, with its parsed arguments and how it ended', () => {
    expect(callsOf(CARD)).toEqual([{ name: 'hubs.business.create', arguments: { name: 'Bar Norte' }, outcome: 'cancelled', code: '' }]);
  });

  it('keeps arguments that are not JSON as written, and a call that never ran as pending', () => {
    const body = sse({ type: 'done', append: [], pending: [{ call_id: 'x', name: 'billing__plan__show', arguments: '{oops' }] });
    expect(callsOf([body])).toEqual([{ name: 'billing.plan.show', arguments: '{oops', outcome: 'pending', code: '' }]);
  });
});

describe('benchTurn', () => {
  it('records the probe, the calls, the card, the verdict, the rounds, the spend and the latency of a turn', () => {
    expect(benchTurn(result(), MEASURED)).toEqual({
      probe: PROBE.id,
      app: 'hubs',
      phrase: PROBE.phrase,
      role: 'account',
      language: 'es',
      surface: 'web',
      expect: 'card',
      kind: 'write',
      tool: 'hubs.business.create',
      lookups: [],
      offered: true,
      calls: callsOf(CARD),
      card: true,
      cards: ['hubs.business.create'],
      verdict: 'pass',
      reasons: [],
      rounds: 3,
      tokensIn: 4000,
      tokensOut: 120,
      tokensEmbedding: 0,
      costUsd: 0.0018,
      latencyMs: 3100,
      error: null,
    });
  });

  it('says the tool was not offered when the ranking left it out', () => {
    expect(benchTurn(result({ verdict: 'fail', reasons: ['x'] }), { ...MEASURED, offered: ['hubs.business.list'] }).offered).toBe(false);
  });

  it('records a turn that never finished as a failure with its error, and one that was not asked as n/a', () => {
    const stuck = benchTurn(result({ observed: null, verdict: 'fail', reasons: ['did not finish: the turn did not end'] }), {
      ...MEASURED,
      bodies: [],
      error: 'did not finish: the turn did not end',
    });
    expect(stuck).toMatchObject({ verdict: 'fail', error: 'did not finish: the turn did not end', card: false, rounds: 0 });
    const skipped = benchTurn(result({ observed: null, verdict: 'n.a.', reasons: ['a copy of an ask'] }), { ...MEASURED, bodies: [], usage: null, latencyMs: null });
    expect(skipped).toMatchObject({ verdict: 'n/a', offered: null, tokensIn: null, costUsd: null, latencyMs: null });
  });

  it('records the error a turn ended with', () => {
    const failed = [sse({ type: 'error', code: 'assistant.provider_unavailable' }, { type: 'done', append: [], pending: [] })];
    const observed = { ...result().observed!, turns: summarizeTurns(failed) };
    expect(benchTurn(result({ observed, verdict: 'fail', reasons: ['y'] }), { ...MEASURED, bodies: failed }).error).toBe('assistant.provider_unavailable');
  });

  it('does not say whether a refused tool was offered', () => {
    expect(benchTurn(result({ probe: { ...PROBE, expect: 'refused' } }), MEASURED).offered).toBeNull();
  });
});

describe('toolKind', () => {
  const web = [{ name: 'hubs.business.create', kind: 'write' }] as CatalogTool[];

  it('is the kind of the probe’s tool in the web catalogue, else what the probe expects', () => {
    expect(toolKind({ ...PROBE, expect: 'refused' }, web)).toBe('write');
    expect(toolKind({ ...PROBE, tool: 'billing.plan.show', expect: 'read' }, web)).toBe('read');
  });
});

describe('usage', () => {
  it('reads the account’s spend as the warm Django prints it, and what one probe added to it', () => {
    const before = parseUsage('1000|100|0|0.100000');
    const after = parseUsage('5000|220|12|0.300000');
    expect(spentBetween(before, after)).toEqual({ tokensIn: 4000, tokensOut: 120, tokensEmbedding: 12, costUsd: 0.2 });
    expect(usageCode('qa@example.com')).toContain('AssistantUsage.objects.filter(user__email="qa@example.com")');
  });

  it('refuses a line it cannot read instead of recording zeros', () => {
    expect(() => parseUsage('nothing')).toThrow(/usage/);
  });
});

describe('offeredCode', () => {
  it('ranks each probe’s phrase as the panel’s turn does, on its surface', () => {
    const code = offeredCode([PROBE]);
    expect(code.startsWith(OFFERED_HEAD)).toBe(true);
    expect(code).toContain('assistant.role_catalog("account", surface=probe["surface"])');
    expect(code).toContain('assistant.relevant(');
    expect(code).toContain(JSON.stringify(JSON.stringify([{ id: PROBE.id, surface: 'web', language: 'es', phrase: PROBE.phrase }])));
  });
});

describe('withTurn', () => {
  const turn = benchTurn(result(), MEASURED);

  it('keeps one turn per probe in the order of the run, and refuses to mix two models in one run', () => {
    const report = withTurn(withTurn(null, META, { ...turn, verdict: 'fail' }, [turn.probe]), META, turn, [turn.probe]);
    expect(report).toEqual({ schema: 1, meta: META, turns: [turn] });
    const other = { ...META, model: { ...META.model, label: 'openai/gpt-x' } };
    expect(() => withTurn(report, other, turn, [turn.probe])).toThrow(/openai\/qwen3.7-plus/);
  });
});

describe('benchModel', () => {
  it('names the model by its kind and id, with its fallback when there is one', () => {
    expect(benchModel(SEEDED.answer)).toEqual({
      label: 'openai/qwen3.7-plus + gpt-5.4-mini',
      provider: 'qwen',
      kind: 'openai',
      id: 'qwen3.7-plus',
      baseUrl: 'https://q.example.com/v1',
      priceIn: null,
      priceOut: null,
      fallback: 'gpt-5.4-mini',
    });
    expect(benchModel({ ...SEEDED.answer, provider: 'qa-answer', price_in: 0.4, price_out: 1.2, fallback: null }).label).toBe('openai/qwen3.7-plus');
  });
});
