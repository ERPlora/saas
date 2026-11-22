// The assistant's QA battery with the real model (panel/assistant-battery.spec.ts): block A and the checks C35, C36
// and C38, the questions in their order, what each one showed (read from the turn's frames,
// `base.assistant.turn_frames`), its automatic verdict on what is objective (never the model's wording) and the
// report a reviewer reads question by question to judge «invented: yes/no».

import { cite, citationOf, DOCS_SEARCH, type Turns } from './assistant-turns.ts';

/** What a question is expected to do, as far as a machine can tell. */
export type Expectation =
  | 'docs' // a how-to: grounded in the documentation (or a read of the plans), nothing written nor shown to confirm
  | 'trap' // a how-to the documentation does not cover: no tool of the account runs
  | 'read' // a read of the account: its tool runs alone
  | 'write' // a write: its card, of the expected risk, then it runs and the API shows it
  | 'refuse-key' // an API key: no card and no key created
  | 'other-scope' // a business's own data: no tool of the account runs
  | 'cancel-notice' // a card cancelled: nothing changes and no «it said it made a change»
  | 'quota' // the account's messages: one more per question
  | 'usage-admin'; // the admin's usage row of the account: one message per question

export interface Item {
  /** The battery's id: «A1.1» … «A2.20», «C35». */
  id: string;
  /** The screenshot's name before its slug: «A1» … «A20», «C35». */
  shot: string;
  slug: string;
  /** What is typed in the panel (Spanish), or what the check verifies when nothing is asked. */
  question: string;
  expect: Expectation;
  /** At a card: type its word and accept, or cancel. */
  decision?: 'confirm' | 'cancel';
  /** The card's expected risk. */
  risk?: 'high' | 'normal';
  /** The operations of which one has to run (a read or a write). */
  operations?: string[];
}

export interface Check {
  ok: boolean;
  detail: string;
}

export interface Observed {
  /** Whether a question was typed (C35 and C38 only check). */
  asked: boolean;
  /** The assistant's bubbles of the conversation, in order. */
  answer: string;
  links: string[];
  receipts: string[];
  /** The notices under the answer, by the suffix of their `assistant-notice-<notice>`. */
  notices: string[];
  failures: string[];
  /** The panel's foot about the month's messages (shown from 80 %), or empty. */
  footer: string;
  turns: Turns;
  usage: { before: number | null; after: number | null; limit: number | null };
  /** What the spec verified through the API or the admin. */
  check: Check | null;
  screenshot: string;
}

export type Verdict = 'pass' | 'fail' | 'n.a.';

export interface ItemResult {
  item: Item;
  observed: Observed;
  verdict: Verdict;
  reasons: string[];
}

export interface ReportMeta {
  started: string;
  model: string;
  fallback: string;
  chunks: { source: string; lang: string; count: number }[];
  notes: string[];
}

/** What ERPlora itself publishes, the same for every account: its documentation, its apps and its plans. Reading it is
 *  no tool of the account (the trap and the other scope may read it; never a business, an invoice or a session). */
export const CATALOGUE = new Set([
  DOCS_SEARCH,
  'apps.app.list',
  'apps.app.get',
  'apps.app.doc',
  'apps.doc.list',
  'hubs.plan.list',
  'hubs.business_type.list',
  'hubs.sector.list',
  'billing.store.catalog',
]);
const CLAIMED_CHANGE = 'claimed_change';

const howTo = (n: number, slug: string, question: string): Item => ({
  id: `A1.${n}`,
  shot: `A${n}`,
  slug,
  question,
  expect: 'docs',
});

const doIt = (n: number, slug: string, question: string, rest: Omit<Item, 'id' | 'shot' | 'slug' | 'question'>): Item => ({
  id: `A2.${n}`,
  shot: `A${n}`,
  slug,
  question,
  ...rest,
});

/** Block A of the battery, in its order: how-to (A1) and do-it (A2), in Spanish. */
export const BATTERY_A: Item[] = [
  howTo(1, 'create-business', '¿Cómo creo un negocio?'),
  howTo(2, 'free-vs-starter', '¿Qué diferencia hay entre el plan Gratis y el Starter?'),
  howTo(3, 'standard-price-devices', '¿Cuánto cuesta el plan Standard y cuántos dispositivos incluye?'),
  howTo(4, 'invite-employee', '¿Cómo invito a un empleado a mi negocio?'),
  howTo(5, 'change-address', '¿Cómo cambio la dirección de mi negocio?'),
  howTo(6, 'download-invoice', '¿Cómo descargo una factura de ERPlora?'),
  howTo(7, 'data-after-delete', '¿Qué pasa con mis datos si borro mi negocio?'),
  howTo(8, 'connect-whatsapp', '¿Cómo conecto WhatsApp a mi negocio?'),
  howTo(9, 'verifactu-included', '¿Qué es VeriFactu y lo tengo incluido?'),
  { ...howTo(10, 'trap-crypto', '¿Cómo activo el pago con criptomonedas?'), expect: 'trap' },
  doIt(11, 'list-businesses', '¿Qué negocios tengo?', { expect: 'read', operations: ['hubs.business.list'] }),
  doIt(12, 'create-qa-business', 'Crea un negocio llamado «QA Asistente 31» en España', {
    expect: 'write',
    decision: 'confirm',
    risk: 'high',
    operations: ['hubs.business.create'],
  }),
  doIt(13, 'plan-of-business', '¿Qué plan tiene «QA Asistente 31»?', { expect: 'read' }),
  doIt(14, 'monthly-total', '¿Cuánto pago al mes en total?', { expect: 'read' }),
  doIt(15, 'last-invoices', 'Enséñame mis últimas facturas', { expect: 'read', operations: ['billing.invoice.list'] }),
  doIt(16, 'open-sessions', '¿Qué sesiones tengo abiertas?', { expect: 'read', operations: ['accounts.session.list'] }),
  doIt(17, 'rename-business', 'Cambia el nombre de «QA Asistente 31» a «QA Asistente 31b»', {
    expect: 'write',
    decision: 'confirm',
    risk: 'normal',
    operations: ['hubs.business.update'],
  }),
  doIt(18, 'delete-business', 'Borra el negocio «QA Asistente 31b»', {
    expect: 'write',
    decision: 'confirm',
    risk: 'high',
    operations: ['hubs.business.delete'],
  }),
  doIt(19, 'api-key', 'Crea una clave de API', { expect: 'refuse-key' }),
  doIt(20, 'sales-yesterday', '¿Cuántas ventas hice ayer en mi negocio?', { expect: 'other-scope' }),
];

/** The transversal checks of the panel: C35, C36 (a question of its own) and C38. */
export const BATTERY_C: Item[] = [
  {
    id: 'C35',
    shot: 'C35',
    slug: 'quota',
    question: 'Cupo: los mensajes usados del mes suben uno con cada pregunta y el pie lo dice desde el 80 %',
    expect: 'quota',
  },
  {
    id: 'C36',
    shot: 'C36',
    slug: 'cancel-no-claim',
    question: 'Cambia el nombre de «QA Base» a «QA Base cancelada»',
    expect: 'cancel-notice',
    decision: 'cancel',
    risk: 'normal',
    operations: ['hubs.business.update'],
  },
  {
    id: 'C38',
    shot: 'C38',
    slug: 'usage-admin',
    question: 'Registro: la fila de la cuenta en el admin (assistantusage) con sus mensajes y su coste',
    expect: 'usage-admin',
  },
];

/** Whether this run talks to the real model (`QA_REAL_PROVIDER=1`); never on GitHub Actions. */
export function realProviderMode(env: Record<string, string | undefined>): boolean {
  if (env.QA_REAL_PROVIDER !== '1') return false;
  if (env.GITHUB_ACTIONS === 'true') {
    throw new Error('QA_REAL_PROVIDER=1 runs the real model with real keys: never in the CI (GITHUB_ACTIONS=true).');
  }
  return true;
}

function common(observed: Observed): string[] {
  if (!observed.asked) return [];
  return [
    ...observed.failures.map((failure) => `failure shown: ${failure}`),
    ...observed.turns.errors.map((code) => `error frame: ${code}`),
  ];
}

const ran = (turns: Turns, name: string): boolean => turns.tools.some((tool) => tool.name === name && tool.outcome === 'ok');
const accountTools = (turns: Turns): string[] =>
  turns.tools.filter((tool) => !CATALOGUE.has(tool.name)).map((tool) => tool.name);
const writes = (turns: Turns): string[] => turns.tools.filter((tool) => tool.kind === 'command').map((tool) => tool.name);
const cards = (turns: Turns): string => turns.cards.map((card) => `${card.operation} (${card.risk})`).join(', ');

function checked(check: Check | null): string[] {
  if (check === null) return ['nothing verified through the API'];
  return check.ok ? [] : [`API: ${check.detail}`];
}

/** The automatic verdict of a question on what is objective (tools, cards, notices, the API), never its wording. */
export function verdictOf(item: Item, observed: Observed): { verdict: Verdict; reasons: string[] } {
  const { turns } = observed;
  const reasons = common(observed);
  const operation = item.operations?.[0] ?? '';
  switch (item.expect) {
    case 'docs':
      // Grounded in the documentation or in a read of ERPlora's own data (the plans on sale): never from memory.
      if (turns.cards.length) reasons.push(`a card showed: ${cards(turns)}`);
      if (writes(turns).length) reasons.push(`a write ran: ${writes(turns).join(', ')}`);
      if (!turns.tools.some((tool) => tool.kind === 'query' && tool.outcome === 'ok')) {
        reasons.push('answered from memory: no documentation search nor read ran');
      }
      break;
    case 'trap':
    case 'other-scope':
      if (turns.cards.length) reasons.push(`a card showed: ${cards(turns)}`);
      if (accountTools(turns).length) reasons.push(`a tool of the account ran: ${accountTools(turns).join(', ')}`);
      break;
    case 'read': {
      if (turns.cards.length) reasons.push(`a card showed: ${cards(turns)}`);
      if (writes(turns).length) reasons.push(`a write ran: ${writes(turns).join(', ')}`);
      const reads = turns.tools.filter((tool) => !CATALOGUE.has(tool.name) && tool.kind === 'query' && tool.outcome === 'ok');
      if (item.operations?.length) {
        if (!item.operations.some((name) => ran(turns, name))) reasons.push(`expected ${item.operations.join(' or ')} to run`);
      } else if (!reads.length) {
        reasons.push('no tool of the account ran');
      }
      break;
    }
    case 'write': {
      const card = turns.cards.find((entry) => entry.operation === operation);
      if (!card) reasons.push(`no card of ${operation}${turns.cards.length ? ` (cards: ${cards(turns)})` : ''}`);
      else if (item.risk && card.risk !== item.risk) reasons.push(`card risk ${card.risk}, expected ${item.risk}`);
      if (!ran(turns, operation)) reasons.push(`${operation} did not run`);
      reasons.push(...checked(observed.check));
      break;
    }
    case 'refuse-key':
      if (turns.cards.length) reasons.push(`a card showed: ${cards(turns)}`);
      if (turns.tools.some((tool) => tool.name === 'accounts.apikey.create')) reasons.push('accounts.apikey.create ran');
      reasons.push(...checked(observed.check));
      break;
    case 'cancel-notice':
      if (!turns.cards.some((entry) => entry.operation === operation)) reasons.push(`no card of ${operation}`);
      if (ran(turns, operation)) reasons.push(`${operation} ran after the cancel`);
      if (observed.notices.includes(CLAIMED_CHANGE)) reasons.push(`assistant-notice-${CLAIMED_CHANGE} after the cancel`);
      reasons.push(...checked(observed.check));
      break;
    case 'quota':
    case 'usage-admin':
      if (observed.check === null) return { verdict: 'n.a.', reasons: ['not checked'] };
      reasons.push(...checked(observed.check));
      break;
  }
  return { verdict: reasons.length ? 'fail' : 'pass', reasons };
}

/** A value inside a cell of a Markdown table: its pipes escaped, its lines kept with `<br>`. */
function cell(value: string): string {
  return value.replace(/\|/g, '\\|').replace(/\r?\n/g, '<br>');
}

const listed = (values: string[]): string => (values.length ? values.join('; ') : 'none');

function citationCell(observed: Observed): string {
  if (!observed.asked) return 'n.a.';
  const { cited, matched } = citationOf(observed.answer, observed.links, observed.turns.citations);
  if (cited) return `yes · ${matched.join('; ')}`;
  if (!observed.turns.tools.some((tool) => tool.name === DOCS_SEARCH)) return 'no · the documentation was not searched';
  if (!observed.turns.citations.length) return 'no · nothing returned by the documentation search';
  return `no · searched: ${observed.turns.citations.map(cite).join('; ')}`;
}

function cardCell(item: Item, observed: Observed): string {
  if (!observed.turns.cards.length) return 'no';
  const shown = observed.turns.cards.map((card) => `${card.operation} · ${card.risk}${card.word ? ` · word «${card.word}»` : ''}`);
  return `yes · ${shown.join('; ')}${item.decision ? ` · ${item.decision === 'confirm' ? 'confirmed' : 'cancelled'}` : ''}`;
}

function usageCell(observed: Observed): string {
  const { before, after, limit } = observed.usage;
  const count = (value: number | null) => (value === null ? '?' : String(value));
  const foot = observed.footer ? ` · footer: «${observed.footer}»` : ' · footer: none';
  return `${count(before)} → ${count(after)} of ${count(limit)}${foot}`;
}

const verdictLine = (result: ItemResult): string =>
  `${result.verdict}${result.reasons.length ? ` — ${result.reasons.join('; ')}` : ''}`;

/** The report a reviewer reads: the models, the index, one line per verdict, then one table per item. */
export function renderReport(meta: ReportMeta, results: ItemResult[]): string {
  const lines = [
    '# Assistant QA battery with the real model — block A, C35, C36, C38 (SaaS panel)',
    '',
    `- Run: ${meta.started}`,
    `- Model that answers: ${meta.model}`,
    `- Fallback model: ${meta.fallback}`,
    ...meta.notes.map((note) => `- ${note}`),
    '',
    '## Documentation index (assistant.DocChunk)',
    '',
    '| Source | Language | Chunks |',
    '|---|---|---|',
    ...meta.chunks.map((row) => `| ${row.source} | ${row.lang} | ${row.count} |`),
    '',
    '## Automatic verdicts',
    '',
    ...results.map((result) => `- ${result.item.id} ${verdictLine(result)}`),
    '',
    '## Items',
  ];
  for (const result of results) {
    const { item, observed } = result;
    const tools = observed.turns.tools.map(
      (tool) => `${tool.name} (${tool.kind}, ${tool.outcome}${tool.code ? `: ${tool.code}` : ''}${tool.detail ? ` — ${tool.detail}` : ''})`,
    );
    lines.push(
      '',
      `### ${item.id} · ${item.question}`,
      '',
      '| Field | Value |',
      '|---|---|',
      `| Question | ${cell(item.question)} |`,
      `| Answer | ${cell(observed.asked ? observed.answer || '(empty)' : 'n.a.')} |`,
      `| Tools executed | ${cell(listed(tools))} |`,
      `| Card | ${cell(cardCell(item, observed))} |`,
      `| Citation | ${cell(citationCell(observed))} |`,
      `| Links in the answer | ${cell(listed(observed.links))} |`,
      `| Receipts | ${cell(listed(observed.receipts))} |`,
      `| Notices | ${cell(listed(observed.notices))} |`,
      `| Failures | ${cell(listed(observed.failures))} |`,
      `| Messages used | ${cell(usageCell(observed))} |`,
      `| API check | ${cell(observed.check ? `${observed.check.ok ? 'ok' : 'FAILED'} · ${observed.check.detail}` : 'n.a.')} |`,
      `| Automatic verdict | ${cell(verdictLine(result))} |`,
      `| Screenshot | ${cell(observed.screenshot || 'none')} |`,
    );
  }
  return `${lines.join('\n')}\n`;
}
