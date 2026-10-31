// @vitest-environment node
// The helpers of the assistant's QA battery with the real model (panel/assistant-battery.spec.ts, plan
// 2026-10-31-qa-asistente block A and C35/C36/C38): the turn's frames as the panel's Django streams them, what each
// question showed, its automatic verdict and the report the supervising chat reads.
import { describe, expect, it } from 'vitest';

import {
  BATTERY_A,
  BATTERY_C,
  citationOf,
  type Item,
  type Observed,
  parseFrames,
  realProviderMode,
  renderReport,
  summarizeTurns,
  verdictOf,
} from './assistant-battery';

/** One server-sent event of the turn, as `assistant.turn.sse` writes it. */
const sse = (frame: unknown): string => `data: ${JSON.stringify(frame)}\n\n`;

const SEARCH_CONTENT = JSON.stringify({
  results: [
    {
      source: 'help',
      path: 'docs/es/help/businesses.md',
      heading: 'Negocios > Crear un negocio',
      text: 'Pulsa «Crear negocio»…',
      score: 0.71,
      lang: 'es',
    },
    {
      source: 'plans',
      path: 'plans',
      heading: 'Planes > Standard',
      text: '29 € al mes…',
      score: 0.52,
      lang: 'es',
    },
  ],
});

/** A how-to question: the model searched the documentation, then answered. */
const SEARCHED = [
  sse({ type: 'text', text: '' }) +
    sse({ type: 'done', append: [], pending: [{ call_id: 'c1', name: 'assistant__docs__search', arguments: '{}' }] }),
  sse({
    type: 'executed',
    call_id: 'c1',
    name: 'assistant.docs.search',
    app: 'assistant',
    app_name: '',
    screen: '',
    kind: 'query',
    outcome: 'ok',
    code: '',
  }) +
    sse({ type: 'text', text: 'Pulsa «Crear negocio» en Negocios.' }) +
    sse({ type: 'usage', used: 3, limit: 30 }) +
    sse({
      type: 'done',
      append: [{ role: 'tool', tool_call_id: 'c1', content: SEARCH_CONTENT }],
      pending: [],
      continuation: null,
    }),
];

function observed(overrides: Partial<Observed> = {}): Observed {
  return {
    asked: true,
    answer: '',
    links: [],
    receipts: [],
    notices: [],
    failures: [],
    footer: '',
    turns: { tools: [], cards: [], citations: [], errors: [] },
    usage: { before: 0, after: 1, limit: 30 },
    check: null,
    screenshot: '/tmp/x.png',
    ...overrides,
  };
}

const item = (id: string): Item => {
  const found = [...BATTERY_A, ...BATTERY_C].find((entry) => entry.id === id);
  if (!found) throw new Error(`no item ${id}`);
  return found;
};

const DOCS = { name: 'assistant.docs.search', kind: 'query', outcome: 'ok', code: '' };

describe('parseFrames', () => {
  it('reads every `data:` event of the stream, in order, and skips what is not one', () => {
    const body = `${sse({ type: 'text', text: 'Ho' })}: keep-alive\n\n${sse({ type: 'text', text: 'la' })}data: {broken\n\n`;
    expect(parseFrames(body)).toEqual([
      { type: 'text', text: 'Ho' },
      { type: 'text', text: 'la' },
    ]);
  });
});

describe('summarizeTurns', () => {
  it('names the tools that ran, in order, with their kind and outcome', () => {
    const turns = summarizeTurns([
      ...SEARCHED,
      sse({ type: 'executed', call_id: 'c2', name: 'hubs.business.create', kind: 'command', outcome: 'cancelled', code: 'base.assistant_not_confirmed' }),
    ]);
    expect(turns.tools).toEqual([
      DOCS,
      { name: 'hubs.business.create', kind: 'command', outcome: 'cancelled', code: 'base.assistant_not_confirmed' },
    ]);
  });

  it('keeps each card the panel showed: its operation, its risk and the word it asks to type', () => {
    const turns = summarizeTurns([
      sse({
        type: 'confirm',
        card: { operation: 'hubs.business.delete', risk: 'high', confirm_word: 'QA Asistente 31b', fields: [] },
        call: { call_id: 'c9' },
      }),
    ]);
    expect(turns.cards).toEqual([{ operation: 'hubs.business.delete', risk: 'high', word: 'QA Asistente 31b' }]);
  });

  it('takes the excerpts the documentation search returned as what the answer may cite', () => {
    expect(summarizeTurns(SEARCHED).citations).toEqual([
      { source: 'help', path: 'docs/es/help/businesses.md', heading: 'Negocios > Crear un negocio', lang: 'es' },
      { source: 'plans', path: 'plans', heading: 'Planes > Standard', lang: 'es' },
    ]);
  });

  it('still reads the excerpts of a search result the tool cut short', () => {
    const cut = `${SEARCH_CONTENT.slice(0, SEARCH_CONTENT.indexOf('29 €'))} …(cut)`;
    const turns = summarizeTurns([
      SEARCHED[0],
      sse({ type: 'executed', call_id: 'c1', name: 'assistant.docs.search', kind: 'query', outcome: 'ok', code: '' }) +
        sse({ type: 'done', append: [{ role: 'tool', tool_call_id: 'c1', content: cut }], pending: [] }),
    ]);
    expect(turns.citations.map((citation) => citation.path)).toEqual(['docs/es/help/businesses.md', 'plans']);
  });

  it("never takes another tool's result for an excerpt of the documentation", () => {
    const turns = summarizeTurns([
      sse({ type: 'executed', call_id: 'c3', name: 'hubs.business.list', kind: 'query', outcome: 'ok', code: '' }) +
        sse({ type: 'done', append: [{ role: 'tool', tool_call_id: 'c3', content: SEARCH_CONTENT }], pending: [] }),
    ]);
    expect(turns.citations).toEqual([]);
  });

  it('keeps why a tool did not run, from what it answered the model (its message and the fields it named)', () => {
    const content = JSON.stringify({
      error: { code: 'invalid_payload', message: 'Invalid payload', fields: { country: 'Choose a country of the list.' } },
    });
    const turns = summarizeTurns([
      sse({ type: 'executed', call_id: 'c4', name: 'hubs.business.create', kind: 'command', outcome: 'error', code: 'invalid_payload' }) +
        sse({ type: 'done', append: [{ role: 'tool', tool_call_id: 'c4', content }], pending: [] }),
    ]);
    expect(turns.tools).toEqual([
      {
        name: 'hubs.business.create',
        kind: 'command',
        outcome: 'error',
        code: 'invalid_payload',
        detail: 'Invalid payload · country: Choose a country of the list.',
      },
    ]);
  });

  it('keeps the codes of the errors the turn streamed', () => {
    expect(summarizeTurns([sse({ type: 'error', code: 'assistant.provider_failed', retriable: true })]).errors).toEqual([
      'assistant.provider_failed',
    ]);
  });
});

describe('citationOf', () => {
  const citations = summarizeTurns(SEARCHED).citations;

  it('is a citation when the answer names a section the search returned', () => {
    expect(citationOf('Mira «Crear un negocio» en la ayuda.', [], citations)).toEqual({
      cited: true,
      matched: ['docs/es/help/businesses.md › Negocios > Crear un negocio'],
    });
  });

  it('is a citation when the answer links a page of the help', () => {
    expect(citationOf('Aquí lo tienes.', ['http://localhost:8532/help/businesses'], []).cited).toBe(true);
  });

  it('is no citation when the answer says nothing of what the search returned', () => {
    expect(citationOf('Pulsa el botón.', ['http://localhost:8532/dashboard/businesses'], citations)).toEqual({
      cited: false,
      matched: [],
    });
  });
});

describe('realProviderMode', () => {
  it('is off unless QA_REAL_PROVIDER=1 is exported', () => {
    expect(realProviderMode({})).toBe(false);
    expect(realProviderMode({ QA_REAL_PROVIDER: '0' })).toBe(false);
    expect(realProviderMode({ QA_REAL_PROVIDER: '1' })).toBe(true);
  });

  it('refuses to run on GitHub Actions: the real model and its keys never go to the CI', () => {
    expect(() => realProviderMode({ QA_REAL_PROVIDER: '1', GITHUB_ACTIONS: 'true' })).toThrow(/never in the CI/);
    expect(realProviderMode({ GITHUB_ACTIONS: 'true' })).toBe(false);
  });
});

describe('the battery', () => {
  it("holds block A's twenty questions in its order, each with its own screenshot name", () => {
    expect(BATTERY_A.map((entry) => entry.id)).toEqual([
      ...Array.from({ length: 10 }, (_, index) => `A1.${index + 1}`),
      ...Array.from({ length: 10 }, (_, index) => `A2.${index + 11}`),
    ]);
    expect(item('A1.1').question).toBe('¿Cómo creo un negocio?');
    expect(item('A2.12').question).toBe('Crea un negocio llamado «QA Asistente 31» en España');
    expect(new Set(BATTERY_A.map((entry) => entry.slug)).size).toBe(BATTERY_A.length);
  });

  it('confirms the writes of A2 and cancels the one of C36', () => {
    expect(['A2.12', 'A2.17', 'A2.18'].map((id) => [item(id).decision, item(id).risk])).toEqual([
      ['confirm', 'high'],
      ['confirm', 'normal'],
      ['confirm', 'high'],
    ]);
    expect(item('C36').decision).toBe('cancel');
  });
});

describe('verdictOf', () => {
  it('passes a how-to question answered from the documentation, nothing run nor shown to confirm', () => {
    expect(verdictOf(item('A1.1'), observed({ turns: summarizeTurns(SEARCHED) }))).toEqual({ verdict: 'pass', reasons: [] });
  });

  it('passes a how-to question answered from a read of what ERPlora sells (the plans), nothing written', () => {
    const plans = { tools: [{ name: 'hubs.plan.list', kind: 'query', outcome: 'ok', code: '' }], cards: [], citations: [], errors: [] };
    expect(verdictOf(item('A1.2'), observed({ turns: plans }))).toEqual({ verdict: 'pass', reasons: [] });
  });

  it('fails a how-to question answered with no tool at all: from memory, neither the documentation nor any data', () => {
    const result = verdictOf(item('A1.2'), observed());
    expect(result.verdict).toBe('fail');
    expect(result.reasons).toEqual(['answered from memory: no documentation search nor read ran']);
  });

  it('fails a how-to question that showed a card or ran a write', () => {
    const turns = {
      ...summarizeTurns(SEARCHED),
      cards: [{ operation: 'hubs.business.create', risk: 'high', word: 'CONFIRMAR' }],
    };
    expect(verdictOf(item('A1.1'), observed({ turns })).verdict).toBe('fail');
  });

  it('fails any question the panel answered with a failure', () => {
    const result = verdictOf(item('A1.1'), observed({ turns: summarizeTurns(SEARCHED), failures: ['El asistente no responde'] }));
    expect(result.verdict).toBe('fail');
    expect(result.reasons.join(' ')).toMatch(/El asistente no responde/);
  });

  it('fails the trap and the other scope when a tool of the account ran', () => {
    const turns = { tools: [DOCS, { name: 'hubs.business.list', kind: 'query', outcome: 'ok', code: '' }], cards: [], citations: [], errors: [] };
    expect(verdictOf(item('A1.10'), observed({ turns })).verdict).toBe('fail');
    expect(verdictOf(item('A2.20'), observed({ turns })).verdict).toBe('fail');
    expect(verdictOf(item('A2.20'), observed({ turns: { ...turns, tools: [DOCS] } })).verdict).toBe('pass');
  });

  it("passes the trap that read ERPlora's own catalogue (its apps, its plans) besides the documentation", () => {
    const catalogue = {
      tools: [DOCS, { name: 'apps.app.list', kind: 'query', outcome: 'ok', code: '' }, { name: 'hubs.plan.list', kind: 'query', outcome: 'ok', code: '' }],
      cards: [],
      citations: [],
      errors: [],
    };
    expect(verdictOf(item('A1.10'), observed({ turns: catalogue }))).toEqual({ verdict: 'pass', reasons: [] });
  });

  it("fails a read of the account's own data answered only from ERPlora's catalogue", () => {
    const plans = { tools: [{ name: 'hubs.plan.list', kind: 'query', outcome: 'ok', code: '' }], cards: [], citations: [], errors: [] };
    expect(verdictOf(item('A2.13'), observed({ turns: plans })).reasons).toEqual(['no tool of the account ran']);
    const own = { ...plans, tools: [{ name: 'hubs.business.get', kind: 'query', outcome: 'ok', code: '' }] };
    expect(verdictOf(item('A2.13'), observed({ turns: own })).verdict).toBe('pass');
  });

  it('passes a read only when its operation ran', () => {
    const listed = { tools: [{ name: 'hubs.business.list', kind: 'query', outcome: 'ok', code: '' }], cards: [], citations: [], errors: [] };
    expect(verdictOf(item('A2.11'), observed({ turns: listed })).verdict).toBe('pass');
    expect(verdictOf(item('A2.11'), observed({ turns: { ...listed, tools: [DOCS] } })).verdict).toBe('fail');
  });

  it('passes a write with its card of the expected risk, its operation done and the API showing it', () => {
    const turns = {
      tools: [{ name: 'hubs.business.create', kind: 'command', outcome: 'ok', code: '' }],
      cards: [{ operation: 'hubs.business.create', risk: 'high', word: 'CONFIRMAR' }],
      citations: [],
      errors: [],
    };
    const done = observed({ turns, check: { ok: true, detail: 'QA Asistente 31 listed' } });
    expect(verdictOf(item('A2.12'), done)).toEqual({ verdict: 'pass', reasons: [] });
    expect(verdictOf(item('A2.12'), { ...done, check: { ok: false, detail: 'not listed' } }).verdict).toBe('fail');
    const normal = { ...turns, cards: [{ operation: 'hubs.business.create', risk: 'normal', word: '' }] };
    expect(verdictOf(item('A2.12'), observed({ turns: normal, check: done.check })).verdict).toBe('fail');
  });

  it('passes the API key only when no card showed and no key was created', () => {
    expect(verdictOf(item('A2.19'), observed({ check: { ok: true, detail: '0 → 0 keys' } })).verdict).toBe('pass');
    const card = { tools: [], cards: [{ operation: 'accounts.apikey.create', risk: 'high', word: 'CONFIRMAR' }], citations: [], errors: [] };
    expect(verdictOf(item('A2.19'), observed({ turns: card, check: { ok: true, detail: '0 → 0' } })).verdict).toBe('fail');
  });

  it('fails the cancelled card of C36 when the answer is flagged as claiming a change', () => {
    const turns = {
      tools: [{ name: 'hubs.business.update', kind: 'command', outcome: 'cancelled', code: 'base.assistant_not_confirmed' }],
      cards: [{ operation: 'hubs.business.update', risk: 'normal', word: '' }],
      citations: [],
      errors: [],
    };
    const check = { ok: true, detail: 'QA Base unchanged' };
    expect(verdictOf(item('C36'), observed({ turns, check })).verdict).toBe('pass');
    expect(verdictOf(item('C36'), observed({ turns, check, notices: ['claimed_change'] })).verdict).toBe('fail');
  });

  it("leaves C35 and C38 to the spec's own check", () => {
    expect(verdictOf(item('C35'), observed({ asked: false, check: { ok: true, detail: '+1 each' } })).verdict).toBe('pass');
    expect(verdictOf(item('C38'), observed({ asked: false, check: { ok: false, detail: '20 ≠ 21' } })).verdict).toBe('fail');
    expect(verdictOf(item('C38'), observed({ asked: false, check: null })).verdict).toBe('n.a.');
  });
});

describe('renderReport', () => {
  const answer = 'Ve a **Negocios** | pulsa «Crear negocio».\nListo.';
  const turns = summarizeTurns(SEARCHED);
  const report = renderReport(
    {
      started: 'run-1',
      model: 'qwen3.7-plus (Qwen)',
      fallback: 'gpt-5.4-mini (OpenAI)',
      chunks: [
        { source: 'help', lang: 'es', count: 12 },
        { source: 'app_doc', lang: 'en', count: 40 },
      ],
      notes: ['AppDoc rows from the Hub\'s register_apps'],
    },
    [
      {
        item: item('A1.1'),
        observed: observed({ answer, turns, notices: ['claimed_change'], screenshot: '/tmp/qa/A1-create-business.png' }),
        verdict: 'pass',
        reasons: [],
      },
    ],
  );

  it('writes one table per question with its full answer, tools, card, citation, notices, verdict and screenshot', () => {
    expect(report).toContain('### A1.1 · ¿Cómo creo un negocio?');
    expect(report).toContain('| Answer | Ve a **Negocios** \\| pulsa «Crear negocio».<br>Listo. |');
    expect(report).toContain('| Tools executed | assistant.docs.search (query, ok) |');
    expect(report).toContain('| Card | no |');
    expect(report).toContain('| Citation | no · searched: docs/es/help/businesses.md › Negocios > Crear un negocio; plans › Planes > Standard |');
    expect(report).toContain('| Notices | claimed_change |');
    expect(report).toContain('| Automatic verdict | pass |');
    expect(report).toContain('| Screenshot | /tmp/qa/A1-create-business.png |');
  });

  it('says when the documentation was not searched at all, and why a tool did not run', () => {
    const failed = {
      tools: [{ name: 'hubs.business.create', kind: 'command', outcome: 'error', code: 'invalid_payload', detail: 'Invalid payload' }],
      cards: [],
      citations: [],
      errors: [],
    };
    const text = renderReport({ started: 'run-2', model: 'm', fallback: 'f', chunks: [], notes: [] }, [
      { item: item('A2.12'), observed: observed({ turns: failed }), verdict: 'fail', reasons: [] },
    ]);
    expect(text).toContain('| Citation | no · the documentation was not searched |');
    expect(text).toContain('| Tools executed | hubs.business.create (command, error: invalid_payload — Invalid payload) |');
  });

  it('starts with the models, the chunks of the index per source and one line per verdict', () => {
    expect(report).toContain('qwen3.7-plus (Qwen)');
    expect(report).toContain('gpt-5.4-mini (OpenAI)');
    expect(report).toContain('| help | es | 12 |');
    expect(report).toContain('| app_doc | en | 40 |');
    expect(report).toContain('- A1.1 pass');
  });
});
