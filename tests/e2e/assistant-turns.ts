// What the panel assistant streamed in the turns of one question (`base.assistant.turn_frames`): the frames of
// its text/event-stream, the tools that ran, the cards, the excerpts the documentation search returned and whether
// an answer cites them.

/** A frame of the panel's turn (`data: {…}` of its text/event-stream). */
export interface Frame {
  type: string;
  [key: string]: unknown;
}

export interface ToolRun {
  name: string;
  kind: string;
  outcome: string;
  code: string;
  /** Why it did not run, from what it answered the model (`live.assistant.error_content`). */
  detail?: string;
}

export interface Card {
  operation: string;
  risk: string;
  word: string;
}

export interface Citation {
  source: string;
  path: string;
  heading: string;
  lang: string;
}

export interface Turns {
  tools: ToolRun[];
  cards: Card[];
  /** The excerpts the documentation search returned: what the answer may cite. */
  citations: Citation[];
  errors: string[];
}

export const DOCS_SEARCH = 'assistant.docs.search';

/** Every `data:` event of a turn's stream, in order; what is not one (a comment, a broken event) is skipped. */
export function parseFrames(body: string): Frame[] {
  const frames: Frame[] = [];
  for (const block of body.split(/\n\n+/)) {
    const data = block
      .split('\n')
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).trimStart())
      .join('\n');
    if (!data) continue;
    try {
      const frame = JSON.parse(data) as unknown;
      if (frame && typeof frame === 'object' && typeof (frame as Frame).type === 'string') frames.push(frame as Frame);
    } catch {
      // A broken event is no frame.
    }
  }
  return frames;
}

const STRING = '"((?:[^"\\\\]|\\\\.)*)"';
const EXCERPT = new RegExp(`\\{"source":${STRING},"path":${STRING},"heading":${STRING}`, 'g');
const LANG = new RegExp(`"lang":${STRING}`);

function unescape(value: string): string {
  try {
    return JSON.parse(`"${value}"`) as string;
  } catch {
    return value;
  }
}

/** The excerpts in a documentation search's result, also when the tool cut it short (`… (cut)`). */
function excerptsOf(content: string): Citation[] {
  const found: Citation[] = [];
  const matches = [...content.matchAll(EXCERPT)];
  matches.forEach((match, index) => {
    const end = index + 1 < matches.length ? matches[index + 1].index : content.length;
    const lang = LANG.exec(content.slice(match.index, end));
    found.push({
      source: unescape(match[1]),
      path: unescape(match[2]),
      heading: unescape(match[3]),
      lang: lang ? unescape(lang[1]) : '',
    });
  });
  return found;
}

const text = (value: unknown): string => (typeof value === 'string' ? value : '');

/** Why a tool did not run, from its answer to the model: its message and the fields it named. */
function errorOf(content: string): string {
  try {
    const error = (JSON.parse(content) as { error?: { message?: unknown; fields?: Record<string, unknown> } }).error;
    if (!error) return '';
    const fields = Object.entries(error.fields ?? {}).map(([field, why]) => `${field}: ${String(why)}`);
    return [text(error.message), ...fields].filter(Boolean).join(' · ');
  } catch {
    return content.slice(0, 300);
  }
}

/** What the tools answered the model, by their call: the `tool` messages each turn's `done` keeps. */
function toolAnswers(frames: Frame[]): Map<string, string> {
  const answers = new Map<string, string>();
  for (const frame of frames.filter((entry) => entry.type === 'done')) {
    const append = Array.isArray(frame.append) ? (frame.append as Record<string, unknown>[]) : [];
    for (const message of append) {
      if (message?.role === 'tool') answers.set(text(message.tool_call_id), text(message.content));
    }
  }
  return answers;
}

/** What the turns of one question streamed: the tools that ran, the cards, the excerpts it may cite, the errors. */
export function summarizeTurns(bodies: string[]): Turns {
  const frames = bodies.flatMap(parseFrames);
  const answers = toolAnswers(frames);
  const searches = new Set(
    frames.filter((frame) => frame.type === 'executed' && frame.name === DOCS_SEARCH).map((frame) => text(frame.call_id)),
  );
  const citations: Citation[] = [];
  const seen = new Set<string>();
  for (const [call, content] of answers) {
    if (!searches.has(call)) continue;
    for (const citation of excerptsOf(content)) {
      const key = `${citation.path}\u0000${citation.heading}\u0000${citation.lang}`;
      if (seen.has(key)) continue;
      seen.add(key);
      citations.push(citation);
    }
  }
  return {
    tools: frames
      .filter((frame) => frame.type === 'executed')
      .map((frame) => {
        const run: ToolRun = { name: text(frame.name), kind: text(frame.kind), outcome: text(frame.outcome), code: text(frame.code) };
        const detail = run.outcome === 'ok' ? '' : errorOf(answers.get(text(frame.call_id)) ?? '');
        return detail ? { ...run, detail } : run;
      }),
    cards: frames
      .filter((frame) => frame.type === 'confirm')
      .map((frame) => {
        const card = (frame.card ?? {}) as Record<string, unknown>;
        return { operation: text(card.operation), risk: text(card.risk), word: text(card.confirm_word) };
      }),
    citations,
    errors: frames.filter((frame) => frame.type === 'error').map((frame) => text(frame.code)),
  };
}

const lastSegment = (heading: string): string => heading.split(' > ').pop()?.trim() ?? '';
export const cite = (citation: Citation): string => `${citation.path} › ${citation.heading}`;

/** Whether the answer cites the documentation: it names a section the search returned (or its file), or links the
 *  public help. */
export function citationOf(answer: string, links: string[], citations: Citation[]): { cited: boolean; matched: string[] } {
  const said = answer.toLocaleLowerCase('es');
  const matched = new Set<string>();
  for (const citation of citations) {
    const section = lastSegment(citation.heading).toLocaleLowerCase('es');
    if ((section.length >= 4 && said.includes(section)) || said.includes(citation.path.toLocaleLowerCase('es'))) {
      matched.add(cite(citation));
    }
  }
  for (const link of links) {
    if (/\/help(\/|$|\?|#)/.test(link)) matched.add(link);
  }
  return { cited: matched.size > 0, matched: [...matched] };
}
