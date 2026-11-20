// What a run of the panel's probes with the real model keeps of each turn, to compare models on the same phrases: the
// tools the model called in order with their arguments, the card, the verdict, the rounds, the tokens and the cost the
// account spent (its usage rows before and after the probe), the latency, and whether the probe's tool was among the
// tools the turn offered (a ranking failure is the same for every model). The report is
// `.artifacts/qa/probes/<run>/bench.json`, in the Hub's format: the Hub's `pnpm -s qa:bench-compare` compares several.
// Pure, so Vitest proves it (assistant-bench.test.ts).
import { type Frame, parseFrames } from './assistant-battery.ts';
import type { CatalogTool, Probe, ProbeResult } from './assistant-probes.ts';

export type BenchVerdict = 'pass' | 'fail' | 'n/a';

/** A tool the model called: its operation, the arguments it gave and how the call ended (`pending`: it never ran). */
export interface BenchCall {
  name: string;
  arguments: unknown;
  outcome: string;
  code: string;
}

export interface Usage {
  tokensIn: number;
  tokensOut: number;
  tokensEmbedding: number;
  costUsd: number;
}

export interface BenchTurn {
  probe: string;
  app: string;
  phrase: string;
  role: string;
  language: string;
  /** The panel's surface it was asked on: `web` or `app`. */
  surface: string;
  expect: string;
  kind: 'read' | 'write';
  tool: string;
  lookups: string[];
  /** Whether the tool was among the tools offered on the first round; null when it does not apply (refused, n/a). */
  offered: boolean | null;
  calls: BenchCall[];
  card: boolean;
  cards: string[];
  verdict: BenchVerdict;
  reasons: string[];
  /** The turn's requests to the assistant: the first, and one more after each round of tools or each card. */
  rounds: number;
  tokensIn: number | null;
  tokensOut: number | null;
  tokensEmbedding: number | null;
  costUsd: number | null;
  latencyMs: number | null;
  error: string | null;
}

export interface BenchModel {
  label: string;
  provider: string;
  kind: string;
  id: string;
  baseUrl: string;
  priceIn: number | null;
  priceOut: number | null;
  fallback: string | null;
}

export interface BenchMeta {
  product: 'hub' | 'saas';
  run: string;
  date: string;
  model: BenchModel;
  files: string[];
  corpus: number;
  sample: { size: number; seed: number } | null;
}

export interface BenchReport {
  schema: 1;
  meta: BenchMeta;
  turns: BenchTurn[];
}

/** What the spec measured around one probe, besides what its verdict read. */
export interface Measured {
  bodies: string[];
  latencyMs: number | null;
  usage: Usage | null;
  offered: string[] | null;
  kind: 'read' | 'write';
  error: string | null;
}

/** The model that answered, as `assistant_seed.py real` prints it. */
export interface SeededAnswer {
  provider: string;
  kind: string;
  model: string;
  base_url: string;
  price_in: number | null;
  price_out: number | null;
  fallback: string | null;
}

export function benchModel(answer: SeededAnswer): BenchModel {
  const named = `${answer.kind}/${answer.model}`;
  return {
    label: answer.fallback ? `${named} + ${answer.fallback}` : named,
    provider: answer.provider,
    kind: answer.kind,
    id: answer.model,
    baseUrl: answer.base_url,
    priceIn: answer.price_in,
    priceOut: answer.price_out,
    fallback: answer.fallback,
  };
}

const operationName = (name: string): string => name.split('__').join('.');

function argumentsOf(raw: unknown): unknown {
  if (typeof raw !== 'string') return raw ?? null;
  try {
    return JSON.parse(raw) as unknown;
  } catch {
    return raw;
  }
}

function remember(calls: Map<string, BenchCall>, call: unknown): void {
  const asked = (call ?? {}) as Record<string, unknown>;
  const id = String(asked.call_id ?? '');
  if (!id || calls.has(id)) return;
  calls.set(id, { name: operationName(String(asked.name ?? '')), arguments: argumentsOf(asked.arguments), outcome: 'pending', code: '' });
}

function ran(calls: Map<string, BenchCall>, frame: Frame): void {
  const id = String(frame.call_id ?? '');
  const row = calls.get(id) ?? { name: '', arguments: null, outcome: '', code: '' };
  calls.set(id, { ...row, name: String(frame.name), outcome: String(frame.outcome ?? ''), code: String(frame.code ?? '') });
}

/** Every tool the model called over a probe's turns, in order and once each, with its arguments and its end. */
export function callsOf(bodies: string[]): BenchCall[] {
  const calls = new Map<string, BenchCall>();
  for (const frame of bodies.flatMap(parseFrames)) {
    // The model's calls come in each round's `done` (a card's call too, before it shows); what ran, in `executed`.
    if (frame.type === 'done') for (const call of (frame.pending ?? []) as unknown[]) remember(calls, call);
    else if (frame.type === 'executed') ran(calls, frame);
  }
  return [...calls.values()];
}

/** Whether the probe's tool reads or writes: the web catalogue (every tool of the panel) says it, else the probe. */
export function toolKind(probe: Probe, web: CatalogTool[]): 'read' | 'write' {
  return web.find((tool) => tool.name === probe.tool)?.kind ?? (probe.expect === 'card' ? 'write' : 'read');
}

type Spend = Pick<BenchTurn, 'tokensIn' | 'tokensOut' | 'tokensEmbedding' | 'costUsd'>;

const spendOf = (usage: Usage | null): Spend => ({
  tokensIn: usage?.tokensIn ?? null,
  tokensOut: usage?.tokensOut ?? null,
  tokensEmbedding: usage?.tokensEmbedding ?? null,
  costUsd: usage?.costUsd ?? null,
});

/** The record of one probe's turn. */
export function benchTurn(result: ProbeResult, measured: Measured): BenchTurn {
  const { probe, observed } = result;
  const verdict: BenchVerdict = result.verdict === 'n.a.' ? 'n/a' : result.verdict;
  const asked = verdict !== 'n/a';
  const ranked = asked && probe.expect !== 'refused' ? measured.offered : null;
  const cards = observed?.turns.cards.map((card) => card.operation) ?? [];
  return {
    probe: probe.id,
    app: probe.app,
    phrase: probe.phrase,
    role: probe.role,
    language: probe.language,
    surface: probe.surface,
    expect: probe.expect,
    kind: measured.kind,
    tool: probe.tool,
    lookups: probe.lookups ?? [],
    offered: ranked ? ranked.includes(probe.tool) : null,
    calls: callsOf(measured.bodies),
    card: cards.length > 0,
    cards,
    verdict,
    reasons: result.reasons,
    rounds: measured.bodies.length,
    ...spendOf(asked ? measured.usage : null),
    latencyMs: asked ? measured.latencyMs : null,
    error: measured.error ?? (observed?.turns.errors.join(', ') || null),
  };
}

/** What the account has spent, as one line `tokens in|tokens out|embedding tokens|cost` (for `djangoPrintWarm`). */
export function usageCode(email: string): string {
  return [
    'from django.db.models import Sum',
    'from assistant.models import AssistantUsage',
    `row = AssistantUsage.objects.filter(user__email=${JSON.stringify(email)}).aggregate(`,
    '    i=Sum("tokens_input"), o=Sum("tokens_output"), e=Sum("tokens_embedding"), c=Sum("cost_usd"))',
    'print(f"{row[\'i\'] or 0}|{row[\'o\'] or 0}|{row[\'e\'] or 0}|{row[\'c\'] or 0}")',
  ].join('\n');
}

export function parseUsage(line: string): Usage {
  const values = line.trim().split('|').map(Number);
  if (values.length !== 4 || values.some((value) => !Number.isFinite(value))) {
    throw new Error(`the account's usage could not be read: «${line.trim().slice(0, 200)}»`);
  }
  const [tokensIn, tokensOut, tokensEmbedding, costUsd] = values;
  return { tokensIn, tokensOut, tokensEmbedding, costUsd };
}

/** What one probe spent: the account's usage after it, less before it (the cost to the database's six decimals). */
export function spentBetween(before: Usage, after: Usage): Usage {
  return {
    tokensIn: after.tokensIn - before.tokensIn,
    tokensOut: after.tokensOut - before.tokensOut,
    tokensEmbedding: after.tokensEmbedding - before.tokensEmbedding,
    costUsd: Number((after.costUsd - before.costUsd).toFixed(6)),
  };
}

/** The start of `offeredCode`: the panel's own catalogue and ranking (`base.assistant`). */
export const OFFERED_HEAD = 'import json\nfrom base import assistant\n';

/** The tools the panel's turn offers each probe's phrase on its surface, as one line of JSON by probe (for
 *  `djangoPrintWarm`): its catalogue of an account (`role_catalog`) ranked as a turn ranks its last question. */
export function offeredCode(probes: Probe[]): string {
  const asked = probes.map(({ id, surface, language, phrase }) => ({ id, surface, language, phrase }));
  return [
    OFFERED_HEAD.trimEnd(),
    `probes = json.loads(${JSON.stringify(JSON.stringify(asked))})`,
    'offered = {}',
    'for probe in probes:',
    '    tools = assistant.role_catalog("account", surface=probe["surface"])',
    '    offered[probe["id"]] = [op.name for op in assistant.relevant(tools, [probe["phrase"]], probe["language"])]',
    'print(json.dumps(offered))',
  ].join('\n');
}

/** The run's report with `turn` in it (a probe asked again replaces its turn), in the order of the run's probes. */
export function withTurn(report: BenchReport | null, meta: BenchMeta, turn: BenchTurn, order: string[]): BenchReport {
  const kept = report && report.meta.run === meta.run ? report : null;
  if (kept && kept.meta.model.label !== meta.model.label) {
    throw new Error(`the run ${meta.run} was answered by ${kept.meta.model.label}, not ${meta.model.label}: ask it in a new run`);
  }
  const turns = [...(kept?.turns ?? []).filter((row) => row.probe !== turn.probe), turn];
  const place = (row: BenchTurn) => order.indexOf(row.probe);
  return { schema: 1, meta: kept?.meta ?? meta, turns: turns.sort((a, b) => place(a) - place(b)) };
}
