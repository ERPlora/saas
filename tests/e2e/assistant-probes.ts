// The probes of the panel assistant's QA with the real model, layer 2 (panel/assistant-probes.spec.ts; plan
// docs/plans/2026-10-31-asistente-conocimiento-y-qa.md of erplora-next, §1.5 and §4 T3): a probe is a NEW natural phrase
// the QA writes for one tool of the exported catalogue (`manage.py export_assistant_catalog`), never one of its
// asks, and what the panel has to do with it. The Hub's probes share this format, so both QAs speak the same
// vocabulary. Here: the probe files and their checks against the catalogue, the decision at a card, the automatic
// verdict of what the panel showed (tools, cards, notices, the outbox; the model's wording only for a refusal), the
// redaction of keys and the Markdown report of a run. Run by Node itself too (qa-probes.ts): imports say their `.ts`.
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';

import { CATALOGUE, type Card, type Citation, citationOf, DOCS_SEARCH, type Turns, type Verdict } from './assistant-battery.ts';

/** What a probe expects the panel to do with its phrase. */
export const PROBE_EXPECTS = ['read', 'card', 'refused', 'docs'] as const;
export type ProbeExpect = (typeof PROBE_EXPECTS)[number];
/** Where the panel is used: the web, and the app's account surface, which sells nothing (`base.assistant.SURFACES`). */
export const PROBE_SURFACES = ['web', 'app'] as const;
export type ProbeSurface = (typeof PROBE_SURFACES)[number];
export const PROBE_LANGUAGES = ['en', 'es'] as const;
export type ProbeLanguage = (typeof PROBE_LANGUAGES)[number];
/** At a card: cancel it (the default: nothing changes) or confirm it. */
export const PROBE_DECISIONS = ['cancel', 'confirm'] as const;
export type ProbeDecision = (typeof PROBE_DECISIONS)[number];
/** The panel's roles (`base.assistant.ROLES`). */
export const PANEL_ROLES = ['account'] as const;
/** How much of the answer the report keeps. */
export const ANSWER_CHARS = 300;
const CLAIMED_CHANGE = 'claimed_change';

export interface Probe {
  /** Unique across every probe file: `<language>-<surface>-<tool>-<n>` as the generator writes it. */
  id: string;
  app: string;
  /** The operation the phrase asks for (`hubs.business.create`); for «refused», one the surface does not offer. */
  tool: string;
  role: string;
  surface: ProbeSurface;
  language: ProbeLanguage;
  /** What the account types: new, natural, never one of the tool's asks. */
  phrase: string;
  expect: ProbeExpect;
  decide?: ProbeDecision;
  /** For «read»: the reads the model may rightly run before the probe's tool (to find the business, say). */
  lookups?: string[];
  notes?: string;
}

/** A tool of the exported catalogue (`live.assistant_qa.export_catalog`). */
export interface CatalogTool {
  name: string;
  tool_name: string;
  app_label: string;
  kind: 'read' | 'write';
  permission: string;
  risk: 'normal' | 'high';
  description: string;
  asks: string[];
  input_schema: unknown;
}

/** What the panel showed for a probe. */
export interface ProbeObserved {
  answer: string;
  links: string[];
  notices: string[];
  failures: string[];
  turns: Turns;
  /** The outbox events (other than the assistant's own) recorded while the probe ran; `null` = not checked. */
  events: string[] | null;
  screenshot: string;
}

export interface ProbeResult {
  probe: Probe;
  source: string;
  /** `null`: the probe was not asked (it did not pass its checks against the catalogue). */
  observed: ProbeObserved | null;
  verdict: Verdict;
  reasons: string[];
}

export interface ProbeReportMeta {
  started: string;
  model: string;
  fallback: string;
  files: string[];
  notes: string[];
}

const FIELDS = new Set(['id', 'app', 'tool', 'role', 'surface', 'language', 'phrase', 'expect', 'decide', 'lookups', 'notes']);
const isText = (value: unknown): value is string => typeof value === 'string' && value.trim() !== '';
const oneOf = (values: readonly string[], value: unknown): boolean => typeof value === 'string' && values.includes(value);

/** The problems of one entry of a probe file, each prefixed by its id (or `#<position>` without one). */
function entryProblems(entry: unknown, position: number): string[] {
  if (!entry || typeof entry !== 'object' || Array.isArray(entry)) return [`#${position}: a probe must be an object`];
  const value = entry as Record<string, unknown>;
  const label = isText(value.id) ? value.id : `#${position}`;
  const problems: string[] = [];
  for (const key of ['id', 'app', 'tool', 'role'] as const) {
    if (!isText(value[key])) problems.push(`${key} must be a non-empty string`);
  }
  if (!oneOf(PROBE_SURFACES, value.surface)) problems.push(`surface must be one of ${PROBE_SURFACES.join(', ')}`);
  if (!oneOf(PROBE_LANGUAGES, value.language)) problems.push(`language must be one of ${PROBE_LANGUAGES.join(', ')}`);
  if (typeof value.phrase !== 'string') problems.push('phrase must be a string');
  if (!oneOf(PROBE_EXPECTS, value.expect)) problems.push(`expect must be one of ${PROBE_EXPECTS.join(', ')}`);
  if (value.decide !== undefined) {
    if (!oneOf(PROBE_DECISIONS, value.decide)) problems.push(`decide must be one of ${PROBE_DECISIONS.join(', ')}`);
    else if (value.expect !== 'card') problems.push('decide is only for expect «card»');
  }
  if (value.lookups !== undefined) {
    if (!Array.isArray(value.lookups) || !value.lookups.every(isText)) problems.push('lookups must be a list of tool names');
    else if (value.expect !== 'read') problems.push('lookups is only for expect «read»');
  }
  if (value.notes !== undefined && typeof value.notes !== 'string') problems.push('notes must be a string');
  for (const key of Object.keys(value)) {
    if (!FIELDS.has(key)) problems.push(`unknown field ${key}`);
  }
  return problems.map((problem) => `${label}: ${problem}`);
}

/** The probes of one file (a JSON list); every wrong field of every probe is named in one error. */
export function parseProbes(raw: unknown, source: string): Probe[] {
  if (!Array.isArray(raw)) throw new Error(`${source}: a list of probes is expected`);
  const problems = raw.flatMap((entry, index) => entryProblems(entry, index + 1));
  if (problems.length) throw new Error(`${source}:\n- ${problems.join('\n- ')}`);
  return raw as Probe[];
}

/** The ids used more than once, in their first order. */
export function duplicateIds(probes: Probe[]): string[] {
  const seen = new Set<string>();
  const twice = new Set<string>();
  for (const { id } of probes) {
    if (seen.has(id)) twice.add(id);
    seen.add(id);
  }
  return [...twice];
}

/** The probe files of `target`: comma-separated paths, each a file (as it is) or a folder (its `.json`, in order);
 *  what does not exist is skipped. */
export function probeFiles(target: string): string[] {
  return target
    .split(',')
    .map((path) => path.trim())
    .filter((path) => path && existsSync(path))
    .flatMap((path) =>
      statSync(path).isDirectory()
        ? readdirSync(path)
            .filter((name) => name.endsWith('.json'))
            .sort()
            .map((name) => join(path, name))
            .filter((file) => statSync(file).isFile())
        : [path],
    );
}

/** Every probe of `files`, with the file it came from; an id used twice across them is refused. */
export function loadProbes(files: string[]): { probe: Probe; source: string }[] {
  const loaded = files.flatMap((source) => {
    let raw: unknown;
    try {
      raw = JSON.parse(readFileSync(source, 'utf8')) as unknown;
    } catch (error) {
      throw new Error(`${source}: not valid JSON (${(error as Error).message})`, { cause: error });
    }
    return parseProbes(raw, source).map((probe) => ({ probe, source }));
  });
  const twice = duplicateIds(loaded.map((entry) => entry.probe));
  if (twice.length) throw new Error(`probe ids used twice: ${twice.join(', ')}`);
  return loaded;
}

const normalized = (text: string): string =>
  text
    .normalize('NFD')
    .replace(/\p{M}+/gu, '')
    .toLocaleLowerCase()
    .replace(/[^\p{L}\p{N}\s]+/gu, '')
    .replace(/\s+/g, ' ')
    .trim();

/** Whether `phrase` is `ask`, without case, accents, punctuation nor extra spaces. */
export function sameAsk(phrase: string, ask: string): boolean {
  return normalized(phrase) === normalized(ask);
}

/** Why `probe` cannot be asked as it is, against the catalogues of its language (the whole one, `web`, and the one of
 *  its surface) and the whole ones of every language (`everyLanguage`: a phrase is none of its tool's asks in any).
 *  Empty when it can. */
export function probeProblems(
  probe: Probe,
  catalogs: { web: CatalogTool[]; surface: CatalogTool[]; everyLanguage: CatalogTool[] },
): string[] {
  if (!probe.phrase.trim()) return ['the phrase is empty: write it'];
  const problems: string[] = [];
  if (!(PANEL_ROLES as readonly string[]).includes(probe.role)) {
    problems.push(`role ${probe.role}: the panel’s roles are ${PANEL_ROLES.join(', ')}`);
  }
  const known = catalogs.web.find((tool) => tool.name === probe.tool);
  const offered = catalogs.surface.find((tool) => tool.name === probe.tool);
  const app = known?.app_label ?? probe.tool.split('.')[0];
  if (probe.app !== app) problems.push(`app ${probe.app}: ${probe.tool} is of ${app}`);
  const asks = catalogs.everyLanguage.filter((tool) => tool.name === probe.tool).flatMap((tool) => tool.asks);
  if (asks.some((ask) => sameAsk(probe.phrase, ask))) {
    problems.push(`the phrase is one of the asks of ${probe.tool}: write a new one`);
  }
  if (probe.expect === 'refused') {
    if (offered) problems.push(`${probe.tool} is offered on the ${probe.surface} surface: «refused» is for what it does not offer`);
    return problems;
  }
  if (!offered) {
    problems.push(`${probe.tool} is not offered on the ${probe.surface} surface: expect «refused»`);
    return problems;
  }
  if (probe.expect === 'docs' && probe.tool !== DOCS_SEARCH) problems.push(`expect «docs» is for ${DOCS_SEARCH}`);
  if (probe.expect === 'read') {
    if (probe.tool === DOCS_SEARCH) problems.push(`${DOCS_SEARCH} answers how-to questions: expect «docs»`);
    else if (offered.kind === 'write') problems.push(`${probe.tool} is a write: expect «card»`);
  }
  if (probe.expect === 'card' && offered.kind === 'read') problems.push(`${probe.tool} is a read: expect «read»`);
  for (const lookup of probe.lookups ?? []) {
    if (catalogs.surface.find((tool) => tool.name === lookup)?.kind !== 'read') {
      problems.push(`lookup ${lookup} is not a read the ${probe.surface} surface offers`);
    }
  }
  return problems;
}

/** At a card: confirm only the probe's own write when the probe says so; cancel anything else. */
export function decisionFor(probe: Probe, card: Card | undefined): ProbeDecision {
  const own = probe.expect === 'card' && probe.decide === 'confirm' && card?.operation === probe.tool;
  return own ? 'confirm' : 'cancel';
}

/** Saying it cannot (Spanish, English): never enough alone, «no puedo» also answers «I have no invoices». */
const UNABLE = [
  /\bno (?:puedo|podemos|puedes|se puede|es posible|me es posible|está disponible|están disponibles|tienes permiso|tiene permiso|tengo permiso)\b|\bsin permiso\b|\bsolo (?:se puede|puedes|puede|lo puede|el|la|los|las|un|una|desde|en)\b/i,
  /\b(?:can['’]?t|cannot|can not|unable to|not able to|not (?:allowed|permitted|available)|(?:is|are)n['’]t (?:allowed|available)|only (?:from|on|in|the|an?|owners?|admins?))\b/i,
];
/** Why: a permission, a role, or where it is done (the app does not sell; erplora.com in the browser does). */
const BECAUSE = [
  /\b(?:permisos?|rol|propietari[oa]s?|dueñ[oa]s?|administrador(?:a|es)?|navegador|erplora\.com|la web|(?:en|desde) (?:la|esta) app)\b/i,
  /\b(?:permissions?|roles?|owners?|admins?|administrators?|browser|erplora\.com|the web|(?:in|from) (?:the|this) app)\b/i,
];
/** The account surface's own words (PLAN-SAAS §3.6, point 6): go to erplora.com from the browser. */
const REDIRECT = /\berplora\.com\b.*\b(?:navegador|browser)\b|\b(?:navegador|browser)\b.*\berplora\.com\b/i;

/** Whether the answer refuses and says why, in one sentence (Spanish or English): it cannot because of a permission,
 *  a role or where it is done, or it sends to erplora.com in the browser. A bare «I cannot», an empty list («I don't
 *  have any invoices yet») or an impersonal «it cannot be used» is no refusal. Only a refusal reads the model's words. */
export function refusalIn(answer: string): boolean {
  return answer
    .split(/(?<=[.!?])\s+|\n+/)
    .some((sentence) => REDIRECT.test(sentence) || (UNABLE.some((p) => p.test(sentence)) && BECAUSE.some((p) => p.test(sentence))));
}

const ok = (turns: Turns, name: string): boolean => turns.tools.some((tool) => tool.name === name && tool.outcome === 'ok');
const unique = (values: string[]): string[] => [...new Set(values)];
const writesOf = (turns: Turns): string[] => unique(turns.tools.filter((tool) => tool.kind === 'command').map((tool) => tool.name));
const cardsOf = (turns: Turns): string => turns.cards.map((card) => `${card.operation} (${card.risk})`).join(', ');

function noCardNorWrite(turns: Turns, reasons: string[]): void {
  if (turns.cards.length) reasons.push(`a card showed: ${cardsOf(turns)}`);
  const writes = writesOf(turns);
  if (writes.length) reasons.push(`a write ran: ${writes.join(', ')}`);
}

function unchanged(events: string[] | null, reasons: string[]): void {
  if (events?.length) reasons.push(`changed: ${events.join(', ')}`);
}

/** Whether the answer cites what the documentation search returned: a section it names or its file (`citationOf`,
 *  as the battery reads it, but never a mere link to the help, which a from-memory answer can carry), or the title of
 *  a Hub app's manual (its first heading: the app's own name, never a common word like the help's «Negocios»). */
function citesDocs(answer: string, citations: Citation[]): boolean {
  if (citationOf(answer, [], citations).cited) return true;
  const said = answer.toLocaleLowerCase();
  return citations.some((citation) => {
    const title = citation.source === 'app_doc' ? (citation.heading.split(' > ')[0]?.trim().toLocaleLowerCase() ?? '') : '';
    return title.length >= 4 && said.includes(title);
  });
}

/** The automatic verdict of a probe on what is objective: the tools that ran, the cards, the notices, the outbox; the
 *  model's words only to hear that it cannot. */
export function probeVerdict(probe: Probe, observed: ProbeObserved, always: readonly string[] = []): { verdict: Verdict; reasons: string[] } {
  const { turns } = observed;
  const reasons = [
    ...observed.failures.map((failure) => `failure shown: ${failure}`),
    ...turns.errors.map((code) => `error frame: ${code}`),
  ];
  const runs = turns.tools.filter((tool) => tool.name === probe.tool);
  const last = runs.at(-1);
  switch (probe.expect) {
    case 'read': {
      if (!last) {
        const names = unique(turns.tools.map((tool) => tool.name));
        reasons.push(`expected ${probe.tool} to run (${names.length ? `ran: ${names.join(', ')}` : 'nothing ran'})`);
      } else if (!ok(turns, probe.tool)) {
        reasons.push(`${probe.tool} ran with ${last.outcome}: ${last.code}${last.detail ? ` — ${last.detail}` : ''}`);
      } else {
        // The first tool the model chose: past the always offered ones and the probe's lookups.
        const skipped = new Set([...always, ...(probe.lookups ?? [])]);
        const first = turns.tools.find((tool) => tool.name === probe.tool || !skipped.has(tool.name));
        if (first && first.name !== probe.tool) reasons.push(`${first.name} ran before ${probe.tool}`);
      }
      noCardNorWrite(turns, reasons);
      unchanged(observed.events, reasons);
      break;
    }
    case 'card': {
      const shown = turns.cards.some((card) => card.operation === probe.tool);
      if (!shown) reasons.push(`no card of ${probe.tool}${turns.cards.length ? ` (cards: ${cardsOf(turns)})` : ''}`);
      else {
        const first = turns.cards[0].operation;
        if (first !== probe.tool) reasons.push(`the first card was ${first}, not ${probe.tool}`);
        const others = turns.cards.filter((card) => card.operation !== probe.tool);
        if (others.length) reasons.push(`another card showed: ${others.map((card) => `${card.operation} (${card.risk})`).join(', ')}`);
      }
      if (probe.decide === 'confirm') {
        if (shown && !ok(turns, probe.tool)) {
          reasons.push(`${probe.tool} did not run after the confirmation${last ? ` (${last.outcome}: ${last.code})` : ''}`);
        }
        break;
      }
      if (ok(turns, probe.tool)) reasons.push(`${probe.tool} ran after the cancel`);
      if (observed.notices.includes(CLAIMED_CHANGE)) reasons.push(`assistant-notice-${CLAIMED_CHANGE} after the cancel`);
      if (observed.events === null) reasons.push('nothing verified in the outbox');
      unchanged(observed.events, reasons);
      break;
    }
    case 'refused':
      noCardNorWrite(turns, reasons);
      if (last) reasons.push(`${probe.tool} ran`);
      if (!refusalIn(observed.answer)) reasons.push('the answer does not say it cannot');
      unchanged(observed.events, reasons);
      break;
    case 'docs': {
      // Grounded in ERPlora's documentation: its search returned excerpts and the answer names one; ERPlora's own
      // published reads (its apps, plans) may help, a tool of the account may not.
      if (!ok(turns, DOCS_SEARCH)) reasons.push(`${DOCS_SEARCH} did not run`);
      else if (!turns.citations.length) reasons.push('the documentation search returned nothing');
      else if (!citesDocs(observed.answer, turns.citations)) reasons.push('the answer cites no documentation');
      const account = unique(turns.tools.filter((tool) => !CATALOGUE.has(tool.name)).map((tool) => tool.name));
      if (account.length) reasons.push(`a tool of the account ran: ${account.join(', ')}`);
      if (turns.cards.length) reasons.push(`a card showed: ${cardsOf(turns)}`);
      unchanged(observed.events, reasons);
      break;
    }
  }
  return { verdict: reasons.length ? 'fail' : 'pass', reasons };
}

const SECRET_SHAPES: [RegExp, string][] = [
  [/\bsk-[A-Za-z0-9_-]{16,}/g, '[redacted]'],
  [/\berpk_(?:live|test)_[A-Za-z0-9_]+/g, '[redacted]'],
  [/\bBearer\s+[A-Za-z0-9._~+/=-]+/g, 'Bearer [redacted]'],
];

/** `text` without the given keys (at least 8 characters each) nor anything shaped like a secret key. */
export function redact(text: string, secrets: (string | undefined)[] = []): string {
  let clean = text;
  for (const secret of secrets) {
    if (secret && secret.trim().length >= 8) clean = clean.split(secret.trim()).join('[redacted]');
  }
  for (const [shape, replacement] of SECRET_SHAPES) clean = clean.replace(shape, replacement);
  return clean;
}

/** `error` (a failed command's, say) as an `Error` whose message carries no key: what reaches the console. */
export function redactedError(error: unknown, secrets: (string | undefined)[] = []): Error {
  const message = error instanceof Error ? error.message : String(error);
  return new Error(redact(message, secrets));
}

/** A value inside a cell of a Markdown table: its pipes escaped, its lines kept with `<br>`. */
const cell = (value: string): string => value.replace(/\|/g, '\\|').replace(/\r?\n/g, '<br>');
const row = (cells: string[]): string => `| ${cells.map(cell).join(' | ')} |`;
const listed = (values: string[]): string => (values.length ? values.join('; ') : 'none');

/** The tools the model chose for a probe; «not asked» for an n.a., «unknown» for a probe that did not finish. */
function chosen(result: ProbeResult): string {
  if (!result.observed) return result.verdict === 'n.a.' ? 'not asked' : 'unknown';
  const names = unique(result.observed.turns.tools.map((tool) => tool.name));
  return names.length ? names.join(', ') : 'none';
}

function cut(answer: string): string {
  if (!answer) return '(empty)';
  return answer.length > ANSWER_CHARS ? `${answer.slice(0, ANSWER_CHARS)}…` : answer;
}

function details(result: ProbeResult): string[] {
  const { probe, observed } = result;
  const verdict = `${result.verdict}${result.reasons.length ? ` — ${result.reasons.join('; ')}` : ''}`;
  const lines = [
    '',
    `### ${probe.id} · ${probe.phrase || '(no phrase)'}`,
    '',
    row(['Field', 'Value']),
    '|---|---|',
    row(['Phrase', probe.phrase]),
    row(['File', result.source]),
    row(['Expected', `${probe.expect} · ${probe.tool}${probe.decide ? ` · ${probe.decide}` : ''} (${probe.role}, ${probe.surface}, ${probe.language})`]),
  ];
  if (probe.notes) lines.push(row(['Notes', probe.notes]));
  if (observed) {
    const tools = observed.turns.tools.map(
      (tool) => `${tool.name} (${tool.kind}, ${tool.outcome}${tool.code ? `: ${tool.code}` : ''}${tool.detail ? ` — ${tool.detail}` : ''})`,
    );
    lines.push(
      row(['Tools executed', listed(tools)]),
      row(['Cards', listed(observed.turns.cards.map((card) => `${card.operation} · ${card.risk}`))]),
      row(['Documentation returned', listed(observed.turns.citations.map((entry) => `${entry.path} › ${entry.heading}`))]),
      row(['Links', listed(observed.links)]),
      row(['Notices', listed(observed.notices)]),
      row(['Failures', listed(observed.failures)]),
      row(['Changes (outbox)', observed.events === null ? 'not checked' : listed(observed.events)]),
      row([`Answer (first ${ANSWER_CHARS} characters)`, cut(observed.answer)]),
      row(['Screenshot', observed.screenshot || 'none']),
    );
  }
  lines.push(row(['Automatic verdict', verdict]));
  return lines;
}

/** The report of a run: the models, the counts, one line per probe (with the tool the model chose), then each probe;
 *  keys are redacted from all of it. */
export function renderProbeReport(meta: ProbeReportMeta, results: ProbeResult[], secrets: (string | undefined)[] = []): string {
  const count = (verdict: Verdict) => results.filter((result) => result.verdict === verdict).length;
  const lines = [
    '# Assistant probes with the real model (SaaS panel)',
    '',
    `- Run: ${meta.started}`,
    `- Model that answers: ${meta.model}`,
    `- Fallback model: ${meta.fallback}`,
    `- Files: ${listed(meta.files)}`,
    `- Result: ${count('pass')} pass · ${count('fail')} fail · ${count('n.a.')} n.a. (${results.length} probes)`,
    ...meta.notes.map((note) => `- ${note}`),
    '',
    '## Verdicts',
    '',
    row(['Probe', 'Surface', 'Language', 'Expect', 'Tool', 'Verdict', 'Chosen', 'Reasons']),
    '|---|---|---|---|---|---|---|---|',
    ...results.map((result) =>
      row([
        result.probe.id,
        result.probe.surface,
        result.probe.language,
        result.probe.expect,
        result.probe.tool,
        result.verdict,
        chosen(result),
        result.reasons.join('; '),
      ]),
    ),
    '',
    '## Probes',
    ...results.flatMap(details),
  ];
  return redact(`${lines.join('\n')}\n`, secrets);
}
