// @vitest-environment node
// The probes of the assistant's QA with the real model (panel/assistant-probes.spec.ts): their files, their checks
// against the exported catalogue, the redaction of keys and the report of a run. The automatic verdict of what the
// panel showed is in assistant-probes.verdict.test.ts.
import { mkdirSync, mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { NO_TURNS, observed, probe, ran } from './__tests__/assistant-probes';
import {
  ANSWER_CHARS,
  type CatalogTool,
  decisionFor,
  duplicateIds,
  loadProbes,
  parseProbes,
  probeFiles,
  probeProblems,
  type ProbeResult,
  redact,
  redactedError,
  refusalIn,
  renderProbeReport,
  sameAsk,
} from './assistant-probes';

const CORPUS = join(dirname(fileURLToPath(import.meta.url)), 'qa', 'probes');

const tool = (name: string, kind: 'read' | 'write', asks: string[], risk: 'normal' | 'high' = 'normal'): CatalogTool => ({
  name,
  tool_name: name.replace(/\./g, '__'),
  app_label: name.split('.')[0],
  kind,
  permission: `${name.split('.')[0]}.view`,
  risk,
  description: `What ${name} does.`,
  asks,
  input_schema: { type: 'object', properties: {} },
});

const LIST = tool('hubs.business.list', 'read', ['¿qué negocios tengo?', 'enséñame mis negocios']);
const CREATE = tool('hubs.business.create', 'write', ['créame otro negocio en Valencia', 'abre un negocio nuevo'], 'high');
const DOCS = tool('assistant.docs.search', 'read', ['¿cómo configuro la impresora de cocina?', '¿qué diferencia hay entre planes?']);
const CANCEL = tool('billing.plan.cancel', 'write', ['cancela el plan del bar', 'ya no quiero pagar el Starter'], 'high');
const WEB = [LIST, CREATE, DOCS, CANCEL];
const APP = [LIST, CREATE, DOCS];

describe('parseProbes', () => {
  it('reads a file of probes, with the optional decision and notes', () => {
    const raw = [probe(), probe({ id: 'b', tool: 'hubs.business.create', expect: 'card', decide: 'confirm', notes: 'n' })];
    expect(parseProbes(raw, 'a.json')).toEqual(raw);
  });

  it('accepts an empty phrase: the skeleton the generator writes before the phrases', () => {
    expect(parseProbes([probe({ phrase: '' })], 'a.json')[0].phrase).toBe('');
  });

  it('refuses a file that is not a list', () => {
    expect(() => parseProbes({ probes: [] }, 'a.json')).toThrow('a.json: a list of probes is expected');
  });

  it('names every wrong field of every probe, by its id or its position', () => {
    const wrong = [
      { ...probe(), expect: 'write', surface: 'tablet' },
      { ...probe({ id: 'c' }), decide: 'maybe' },
      { ...probe(), id: '' },
      { ...probe({ id: 'd' }), extra: 1 },
    ];
    let message = '';
    try {
      parseProbes(wrong, 'a.json');
    } catch (error) {
      message = (error as Error).message;
    }
    expect(message).toContain('a.json');
    expect(message).toContain('es-web-hubs.business.list-1: expect must be one of read, card, refused, docs');
    expect(message).toContain('es-web-hubs.business.list-1: surface must be one of web, app');
    expect(message).toContain('c: decide must be one of cancel, confirm');
    expect(message).toContain('#3: id must be a non-empty string');
    expect(message).toContain('d: unknown field extra');
  });

  it('takes lookups only on a read, as a list of tool names', () => {
    expect(parseProbes([probe({ lookups: ['hubs.business.get'] })], 'a.json')[0].lookups).toEqual(['hubs.business.get']);
    expect(() => parseProbes([{ ...probe(), lookups: 'hubs.business.get' }], 'a.json')).toThrow('lookups must be a list of tool names');
    expect(() => parseProbes([{ ...probe(), lookups: [''] }], 'a.json')).toThrow('lookups must be a list of tool names');
    const card = probe({ tool: 'hubs.business.create', expect: 'card', lookups: ['hubs.business.list'] });
    expect(() => parseProbes([card], 'a.json')).toThrow('lookups is only for expect «read»');
  });

  it('allows a decision only on a card', () => {
    expect(() => parseProbes([probe({ decide: 'cancel' })], 'a.json')).toThrow('decide is only for expect «card»');
  });
});

describe('duplicateIds', () => {
  it('names the ids used more than once', () => {
    expect(duplicateIds([probe(), probe({ id: 'x' }), probe()])).toEqual(['es-web-hubs.business.list-1']);
  });
});

describe('probeFiles and loadProbes', () => {
  it('lists the JSON files of a folder in order, takes a file as it is and skips what is missing', () => {
    const dir = mkdtempSync(join(tmpdir(), 'probes-'));
    mkdirSync(join(dir, 'sub'));
    writeFileSync(join(dir, 'b.json'), '[]');
    writeFileSync(join(dir, 'a.json'), '[]');
    writeFileSync(join(dir, 'notes.md'), '');
    expect(probeFiles(dir)).toEqual([join(dir, 'a.json'), join(dir, 'b.json')]);
    expect(probeFiles(`${join(dir, 'b.json')},${join(dir, 'a.json')}`)).toEqual([join(dir, 'b.json'), join(dir, 'a.json')]);
    expect(probeFiles(join(dir, 'missing'))).toEqual([]);
  });

  it('loads every file with its source and refuses an id used twice across files', () => {
    const dir = mkdtempSync(join(tmpdir(), 'probes-'));
    writeFileSync(join(dir, 'a.json'), JSON.stringify([probe()]));
    writeFileSync(join(dir, 'b.json'), JSON.stringify([probe({ id: 'other' })]));
    expect(loadProbes(probeFiles(dir)).map((entry) => [entry.probe.id, entry.source])).toEqual([
      ['es-web-hubs.business.list-1', join(dir, 'a.json')],
      ['other', join(dir, 'b.json')],
    ]);
    writeFileSync(join(dir, 'c.json'), JSON.stringify([probe()]));
    expect(() => loadProbes(probeFiles(dir))).toThrow('probe ids used twice: es-web-hubs.business.list-1');
  });
});

describe('sameAsk', () => {
  it('compares without case, accents, punctuation nor extra spaces', () => {
    expect(sameAsk('  ¿Qué  NEGOCIOS tengo? ', '¿qué negocios tengo?')).toBe(true);
    expect(sameAsk('que negocios tengo', '¿qué negocios tengo?')).toBe(true);
    expect(sameAsk('Creame, otro negocio en Valencia!', 'créame otro negocio en Valencia')).toBe(true);
    expect(sameAsk('whats my plan', "what's my plan?")).toBe(true);
    expect(sameAsk('¿qué negocios tengo ahora?', '¿qué negocios tengo?')).toBe(false);
  });
});

describe('probeProblems', () => {
  const EN_LIST = tool('hubs.business.list', 'read', ['what businesses do I have?', 'show my businesses']);
  const catalogs = { web: WEB, surface: WEB, everyLanguage: [...WEB, EN_LIST] };
  const onApp = { web: WEB, surface: APP, everyLanguage: WEB };

  it('finds nothing wrong in a new phrase for a tool of the surface', () => {
    expect(probeProblems(probe(), catalogs)).toEqual([]);
  });

  it('refuses an empty phrase', () => {
    expect(probeProblems(probe({ phrase: ' ' }), catalogs)).toEqual(['the phrase is empty: write it']);
  });

  it('refuses a phrase that is one of the tool’s asks, in any language, accents and punctuation aside', () => {
    const copied = ['the phrase is one of the asks of hubs.business.list: write a new one'];
    expect(probeProblems(probe({ phrase: 'Enseñame mis negocios!' }), catalogs)).toEqual(copied);
    // The English ask on a Spanish probe.
    expect(probeProblems(probe({ phrase: 'Show my businesses' }), catalogs)).toEqual(copied);
  });

  it('refuses a role the panel does not have', () => {
    expect(probeProblems(probe({ role: 'owner' }), catalogs)).toEqual(['role owner: the panel’s roles are account']);
  });

  it('refuses a tool the surface does not offer for a read, a card or the documentation', () => {
    expect(probeProblems(probe({ tool: 'billing.plan.cancel', app: 'billing', expect: 'card', surface: 'app' }), onApp)).toEqual([
      'billing.plan.cancel is not offered on the app surface: expect «refused»',
    ]);
  });

  it('wants a read for «read», a write for «card» and the documentation search for «docs»', () => {
    expect(probeProblems(probe({ tool: 'hubs.business.create', expect: 'read' }), catalogs)).toEqual([
      'hubs.business.create is a write: expect «card»',
    ]);
    expect(probeProblems(probe({ expect: 'card' }), catalogs)).toEqual(['hubs.business.list is a read: expect «read»']);
    expect(probeProblems(probe({ expect: 'docs' }), catalogs)).toEqual(['expect «docs» is for assistant.docs.search']);
    expect(probeProblems(probe({ tool: 'assistant.docs.search', app: 'assistant', expect: 'read' }), catalogs)).toEqual([
      'assistant.docs.search answers how-to questions: expect «docs»',
    ]);
  });

  it('refuses «refused» for a tool the surface offers, and takes it for one it does not', () => {
    expect(probeProblems(probe({ expect: 'refused' }), catalogs)).toEqual([
      'hubs.business.list is offered on the web surface: «refused» is for what it does not offer',
    ]);
    const refused = probe({ tool: 'billing.plan.cancel', app: 'billing', surface: 'app', expect: 'refused', phrase: 'dame de baja' });
    expect(probeProblems(refused, onApp)).toEqual([]);
    // An operation that is no tool anywhere (the API keys are created on their page only).
    expect(probeProblems(probe({ tool: 'accounts.apikey.create', app: 'accounts', expect: 'refused' }), catalogs)).toEqual([]);
  });

  it('wants the app of the tool', () => {
    expect(probeProblems(probe({ app: 'billing' }), catalogs)).toEqual(['app billing: hubs.business.list is of hubs']);
    expect(probeProblems(probe({ tool: 'accounts.apikey.create', app: 'hubs', expect: 'refused' }), catalogs)).toEqual([
      'app hubs: accounts.apikey.create is of accounts',
    ]);
  });

  it('wants lookups that are reads the surface offers', () => {
    expect(probeProblems(probe({ surface: 'app', lookups: ['assistant.docs.search'] }), onApp)).toEqual([]);
    expect(probeProblems(probe({ surface: 'app', lookups: ['hubs.business.create', 'billing.plan.cancel'] }), onApp)).toEqual([
      'lookup hubs.business.create is not a read the app surface offers',
      'lookup billing.plan.cancel is not a read the app surface offers',
    ]);
  });
});

describe('decisionFor', () => {
  const card = { operation: 'hubs.business.create', risk: 'high', word: 'CREAR' };
  it('confirms only the card of the probe’s write when it says so; cancels everything else', () => {
    const write = probe({ tool: 'hubs.business.create', expect: 'card', decide: 'confirm' });
    expect(decisionFor(write, card)).toBe('confirm');
    expect(decisionFor({ ...write, decide: undefined }, card)).toBe('cancel');
    expect(decisionFor({ ...write, decide: 'cancel' }, card)).toBe('cancel');
    expect(decisionFor(write, { ...card, operation: 'hubs.business.delete' })).toBe('cancel');
    expect(decisionFor(write, undefined)).toBe('cancel');
    expect(decisionFor(probe({ tool: 'hubs.business.create', expect: 'refused' }), card)).toBe('cancel');
  });
});

describe('refusalIn', () => {
  it('hears a refusal that says why: the app, the browser, a permission or a role (Spanish and English)', () => {
    expect(refusalIn('Desde aquí no puedo cancelar el plan: hazlo en la web.')).toBe(true);
    expect(refusalIn('Esa opción no está disponible en la app.')).toBe(true);
    expect(refusalIn('No tienes permiso para borrar el negocio.')).toBe(true);
    expect(refusalIn('Solo el propietario puede cederlo.')).toBe(true);
    expect(refusalIn('I can’t cancel your plan from the app.')).toBe(true);
    expect(refusalIn("That isn't available in the app.")).toBe(true);
    expect(refusalIn('Only an admin or the owner can change roles.')).toBe(true);
  });

  it('hears a redirect to erplora.com in the browser as a refusal', () => {
    expect(refusalIn('Para eso, entra en erplora.com desde el navegador.')).toBe(true);
    expect(refusalIn('Open erplora.com in your browser to change the plan.')).toBe(true);
  });

  it('does not take a bare «I cannot», an empty list or an impersonal «cannot» for a refusal', () => {
    expect(refusalIn('No puedo hacerlo.')).toBe(false);
    expect(refusalIn("I can't do that.")).toBe(false);
    expect(refusalIn("I don't have any invoices yet.")).toBe(false);
    expect(refusalIn('No tengo facturas tuyas todavía.')).toBe(false);
    expect(refusalIn('Hecho: he cancelado el plan del bar.')).toBe(false);
    // What the panel answered in the app to «¿me vale el cupón PRIMAVERA20?»: the checkout explained.
    expect(refusalIn('En el pago seguro, pulsa «¿Tienes un código promocional?». Si tu negocio ya paga, el cupón no se puede usar.')).toBe(false);
    expect(refusalIn('That code is not available for paid plans.')).toBe(false);
  });
});

describe('redactedError', () => {
  it('keeps the message of a failed command without the keys it might carry', () => {
    const error = new Error('Command failed: uv run …\nQA_QWEN_API_KEY=qwen-secret-value-123 sk-abcdefghijklmnopqrstuvwx');
    const clean = redactedError(error, ['qwen-secret-value-123']);
    expect(clean).toBeInstanceOf(Error);
    expect(clean.message).toBe('Command failed: uv run …\nQA_QWEN_API_KEY=[redacted] [redacted]');
    expect(redactedError('plain text', []).message).toBe('plain text');
  });
});

describe('redact', () => {
  it('hides the keys it is given and anything shaped like a secret key', () => {
    const text = 'key sk-proj-abcdefghijklmnop0123456789 and qwen-secret-value-123 and erpk_live_AbC123xyz and Bearer abc.def-ghi';
    expect(redact(text, ['qwen-secret-value-123', undefined, ''])).toBe(
      'key [redacted] and [redacted] and [redacted] and Bearer [redacted]',
    );
  });
});

describe('renderProbeReport', () => {
  const meta = { started: 'run-1', model: 'qwen3.7-plus (Qwen)', fallback: 'gpt-5.4-mini (OpenAI)', files: ['a.json'], notes: ['note'] };
  const pass: ProbeResult = {
    probe: probe(),
    source: 'a.json',
    observed: observed({ answer: 'x'.repeat(400), turns: { ...NO_TURNS, tools: [ran('hubs.business.list', 'query')] }, screenshot: 's.png' }),
    verdict: 'pass',
    reasons: [],
  };
  const fail: ProbeResult = {
    probe: probe({ id: 'w', tool: 'hubs.business.create', expect: 'card', phrase: 'móntame | otro' }),
    source: 'a.json',
    observed: observed({ answer: 'tu clave sk-abcdefghijklmnopqrstuvwx', turns: { ...NO_TURNS, cards: [] } }),
    verdict: 'fail',
    reasons: ['no card of hubs.business.create'],
  };
  const notAsked: ProbeResult = { probe: probe({ id: 'n', phrase: '' }), source: 'a.json', observed: null, verdict: 'n.a.', reasons: ['the phrase is empty: write it'] };

  it('counts the verdicts, lists each probe with the tool chosen and cuts the answer', () => {
    const report = renderProbeReport(meta, [pass, fail, notAsked]);
    expect(report).toContain('- Result: 1 pass · 1 fail · 1 n.a. (3 probes)');
    expect(report).toContain('| es-web-hubs.business.list-1 | web | es | read | hubs.business.list | pass | hubs.business.list |  |');
    expect(report).toContain('| w | web | es | card | hubs.business.create | fail | none | no card of hubs.business.create |');
    expect(report).toContain('| n | web | es | read | hubs.business.list | n.a. | not asked | the phrase is empty: write it |');
    expect(report).toContain(`| Answer (first ${ANSWER_CHARS} characters) | ${'x'.repeat(ANSWER_CHARS)}… |`);
    expect(report).toContain('### w · móntame | otro');
    expect(report).toContain('| Phrase | móntame \\| otro |');
  });

  it('says «unknown» for the tool chosen when the probe did not finish', () => {
    const unfinished: ProbeResult = { ...notAsked, probe: probe({ id: 'u' }), verdict: 'fail', reasons: ['did not finish: timeout'] };
    expect(renderProbeReport(meta, [unfinished])).toContain('| u | web | es | read | hubs.business.list | fail | unknown | did not finish: timeout |');
  });

  it('never writes a key', () => {
    const report = renderProbeReport(meta, [fail], ['qwen-secret-value-123']);
    expect(report).not.toContain('sk-abcdefghijklmnopqrstuvwx');
    expect(report).toContain('tu clave [redacted]');
  });
});

describe('the corpus (tests/e2e/qa/probes/)', () => {
  it('loads, every id once and every phrase written', () => {
    const corpus = loadProbes(probeFiles(CORPUS));
    expect(corpus.length).toBeGreaterThan(0);
    expect(corpus.filter((entry) => !entry.probe.phrase.trim()).map((entry) => entry.probe.id)).toEqual([]);
  });
});
