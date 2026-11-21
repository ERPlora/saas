// @vitest-environment node
// The automatic verdict of what the panel showed for a probe of the assistant's QA with the real model
// (panel/assistant-probes.spec.ts).
import { describe, expect, it } from 'vitest';

import { NO_TURNS, observed, probe, ran } from './__tests__/assistant-probes';
import { probeVerdict } from './assistant-probes';

describe('probeVerdict', () => {
  /** What every turn of the panel offers (`base.assistant.ALWAYS`). */
  const ALWAYS = ['hubs.business.list', 'assistant.docs.search'];
  const invoices = probe({ id: 'i', app: 'billing', tool: 'billing.invoice.list', phrase: '¿qué me habéis cobrado?' });

  it('passes a read whose tool ran first (after the always offered ones), with no card and no change', () => {
    const shown = observed({
      turns: { ...NO_TURNS, tools: [ran('hubs.business.list', 'query'), ran('billing.invoice.list', 'query'), ran('hubs.business.get', 'query')] },
    });
    expect(probeVerdict(invoices, shown, ALWAYS)).toEqual({ verdict: 'pass', reasons: [] });
    // A read of an always offered tool is its own first.
    const own = observed({ turns: { ...NO_TURNS, tools: [ran('hubs.business.list', 'query')] } });
    expect(probeVerdict(probe(), own, ALWAYS)).toEqual({ verdict: 'pass', reasons: [] });
  });

  it('fails a read when another tool of the account ran before it, unless the probe names it a lookup', () => {
    const shown = observed({ turns: { ...NO_TURNS, tools: [ran('hubs.business.get', 'query'), ran('billing.invoice.list', 'query')] } });
    expect(probeVerdict(invoices, shown, ALWAYS).reasons).toEqual(['hubs.business.get ran before billing.invoice.list']);
    expect(probeVerdict({ ...invoices, lookups: ['hubs.business.get'] }, shown, ALWAYS)).toEqual({ verdict: 'pass', reasons: [] });
  });

  it('fails a read when its tool did not run, a card showed, a write ran or something changed', () => {
    const shown = observed({
      turns: {
        ...NO_TURNS,
        tools: [ran('hubs.business.get', 'query'), ran('hubs.business.create', 'command', 'cancelled')],
        cards: [{ operation: 'hubs.business.create', risk: 'high', word: 'CREAR' }],
      },
      events: ['hubs.business.updated'],
    });
    expect(probeVerdict(probe(), shown, ALWAYS).reasons).toEqual([
      'expected hubs.business.list to run (ran: hubs.business.get, hubs.business.create)',
      'a card showed: hubs.business.create (high)',
      'a write ran: hubs.business.create',
      'changed: hubs.business.updated',
    ]);
  });

  it('says why the expected read failed when it ran with an error', () => {
    const shown = observed({ turns: { ...NO_TURNS, tools: [{ ...ran('hubs.business.list', 'query', 'error', 'invalid_payload'), detail: 'limit: too big' }] } });
    expect(probeVerdict(probe(), shown, ALWAYS).reasons).toEqual(['hubs.business.list ran with error: invalid_payload — limit: too big']);
  });

  it('fails any probe that showed a failure or streamed an error', () => {
    const shown = observed({
      turns: { ...NO_TURNS, tools: [ran('hubs.business.list', 'query')], errors: ['provider_down'] },
      failures: ['Something went wrong'],
    });
    expect(probeVerdict(probe(), shown, ALWAYS).reasons).toEqual(['failure shown: Something went wrong', 'error frame: provider_down']);
  });

  const write = probe({ id: 'w', tool: 'hubs.business.create', expect: 'card', phrase: 'móntame otro local' });
  const card = { operation: 'hubs.business.create', risk: 'high', word: 'CREAR' };
  const other = { operation: 'hubs.business.update', risk: 'normal', word: '' };

  it('passes a cancelled card: its card showed, the write did not run and nothing changed', () => {
    const shown = observed({
      turns: { ...NO_TURNS, tools: [ran('hubs.business.create', 'command', 'cancelled', 'base.assistant_not_confirmed')], cards: [card] },
    });
    expect(probeVerdict(write, shown, ALWAYS)).toEqual({ verdict: 'pass', reasons: [] });
  });

  it('fails a second card of the write after its cancel: a no is an answer (saas#193)', () => {
    const shown = observed({
      turns: { ...NO_TURNS, tools: [ran('hubs.business.create', 'command', 'cancelled', 'base.assistant_not_confirmed')], cards: [card, card] },
    });
    expect(probeVerdict(write, shown, ALWAYS).reasons).toEqual(['hubs.business.create asked again after the cancel']);
  });

  it('fails a cancelled card that ran anyway, claimed a change, changed something or was never checked', () => {
    const shown = observed({
      turns: { ...NO_TURNS, tools: [ran('hubs.business.create', 'command')], cards: [card] },
      notices: ['claimed_change'],
      events: ['hubs.business.created'],
    });
    expect(probeVerdict(write, shown, ALWAYS).reasons).toEqual([
      'hubs.business.create ran after the cancel',
      'assistant-notice-claimed_change after the cancel',
      'changed: hubs.business.created',
    ]);
    expect(probeVerdict(write, observed({ turns: { ...NO_TURNS, cards: [card] }, events: null }), ALWAYS).reasons).toEqual([
      'nothing verified in the outbox',
    ]);
  });

  it('fails a card that never showed, naming the cards that did', () => {
    expect(probeVerdict(write, observed({ turns: { ...NO_TURNS, cards: [other] } }), ALWAYS).reasons).toEqual([
      'no card of hubs.business.create (cards: hubs.business.update (normal))',
    ]);
    expect(probeVerdict(write, observed(), ALWAYS).reasons).toEqual(['no card of hubs.business.create']);
  });

  it('fails a card whose first card was another write, or that showed another card too', () => {
    expect(probeVerdict(write, observed({ turns: { ...NO_TURNS, cards: [other, card] } }), ALWAYS).reasons).toEqual([
      'the first card was hubs.business.update, not hubs.business.create',
      'another card showed: hubs.business.update (normal)',
    ]);
    expect(probeVerdict(write, observed({ turns: { ...NO_TURNS, cards: [card, other] } }), ALWAYS).reasons).toEqual([
      'another card showed: hubs.business.update (normal)',
    ]);
  });

  it('passes a confirmed card whose write ran; fails it when it did not', () => {
    const confirm = { ...write, decide: 'confirm' as const };
    const done = observed({ turns: { ...NO_TURNS, tools: [ran('hubs.business.create', 'command')], cards: [card] }, events: ['hubs.business.created'] });
    expect(probeVerdict(confirm, done, ALWAYS)).toEqual({ verdict: 'pass', reasons: [] });
    const failed = observed({ turns: { ...NO_TURNS, tools: [ran('hubs.business.create', 'command', 'error', 'conflict')], cards: [card] } });
    expect(probeVerdict(confirm, failed, ALWAYS).reasons).toEqual(['hubs.business.create did not run after the confirmation (error: conflict)']);
  });

  const refused = probe({ id: 'r', app: 'billing', tool: 'billing.plan.cancel', surface: 'app', expect: 'refused', phrase: 'dame de baja' });

  it('passes a refusal: no card, no write, the tool did not run and the answer says why it cannot (reads allowed)', () => {
    const shown = observed({
      answer: 'Desde la app no puedo cancelar planes; hazlo en erplora.com.',
      turns: { ...NO_TURNS, tools: [ran('hubs.business.list', 'query')] },
    });
    expect(probeVerdict(refused, shown, ALWAYS)).toEqual({ verdict: 'pass', reasons: [] });
  });

  it('fails a refusal that showed a card, wrote, or never said why it cannot', () => {
    const shown = observed({
      answer: 'No puedo.',
      turns: {
        ...NO_TURNS,
        tools: [ran('hubs.business.update', 'command', 'cancelled')],
        cards: [{ operation: 'hubs.business.update', risk: 'normal', word: '' }],
      },
    });
    expect(probeVerdict(refused, shown, ALWAYS).reasons).toEqual([
      'a card showed: hubs.business.update (normal)',
      'a write ran: hubs.business.update',
      'the answer does not say it cannot',
    ]);
  });

  const docs = probe({ id: 'd', app: 'assistant', tool: 'assistant.docs.search', expect: 'docs', phrase: '¿y lo de las facturas cómo va?' });
  const HELP = { source: 'help', path: 'docs/es/help/businesses.md', heading: 'Negocios > Crear un negocio', lang: 'es' };

  it('passes a how-to whose documentation search returned excerpts the answer names (ERPlora’s own reads allowed)', () => {
    const shown = observed({
      answer: 'Ve a **Crear un negocio**: pulsa el botón.',
      turns: { ...NO_TURNS, tools: [ran('assistant.docs.search', 'query'), ran('apps.app.get', 'query')], citations: [HELP] },
    });
    expect(probeVerdict(docs, shown, ALWAYS)).toEqual({ verdict: 'pass', reasons: [] });
  });

  it('takes the title of a Hub app’s manual the search returned as a citation, not the first heading of the help', () => {
    const search = (citation: typeof HELP) => ({ ...NO_TURNS, tools: [ran('assistant.docs.search', 'query')], citations: [citation] });
    // A real answer of the panel: the WhatsApp inbox's manual, named by its title.
    const manual = search({
      source: 'app_doc',
      path: 'app_doc:whatsapp_inbox',
      heading: 'Bandeja de WhatsApp > Flujos > WHATSAPP_INBOX-F33 Enviar una plantilla',
      lang: 'es',
    });
    expect(probeVerdict(docs, observed({ answer: 'ERPlora tiene la app Bandeja de WhatsApp: conéctala en sus Ajustes.', turns: manual }), ALWAYS)).toEqual({
      verdict: 'pass',
      reasons: [],
    });
    expect(probeVerdict(docs, observed({ answer: 'Tus negocios están en Negocios.', turns: search(HELP) }), ALWAYS).reasons).toEqual([
      'the answer cites no documentation',
    ]);
  });

  it('fails a how-to that did not search (an app manual read alone is not enough), or whose search returned nothing', () => {
    const manualOnly = observed({ answer: 'Pulsa el botón.', turns: { ...NO_TURNS, tools: [ran('apps.app.doc', 'query')] } });
    expect(probeVerdict(docs, manualOnly, ALWAYS).reasons).toEqual(['assistant.docs.search did not run']);
    const empty = observed({ answer: 'Pulsa el botón.', turns: { ...NO_TURNS, tools: [ran('assistant.docs.search', 'query')] } });
    expect(probeVerdict(docs, empty, ALWAYS).reasons).toEqual(['the documentation search returned nothing']);
  });

  it('does not take a link to the help for a citation: the answer has to name what the search returned', () => {
    const fromMemory = observed({
      answer: 'Pulsa el botón de arriba; tienes más en la ayuda.',
      links: ['https://x/help'],
      turns: { ...NO_TURNS, tools: [ran('assistant.docs.search', 'query')], citations: [HELP] },
    });
    expect(probeVerdict(docs, fromMemory, ALWAYS).reasons).toEqual(['the answer cites no documentation']);
  });

  it('fails a how-to when a tool of the account ran', () => {
    const shown = observed({
      answer: 'Ve a **Crear un negocio**.',
      turns: { ...NO_TURNS, tools: [ran('assistant.docs.search', 'query'), ran('hubs.business.list', 'query')], citations: [HELP] },
    });
    expect(probeVerdict(docs, shown, ALWAYS).reasons).toEqual(['a tool of the account ran: hubs.business.list']);
  });
});
