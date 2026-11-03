// The AI provider of the panel's assistant's e2e (panel/assistant-panel.spec.ts, ASSISTANT-F25): a real HTTP server on
// 127.0.0.1 that speaks OpenAI's API (`/v1/models`, streamed `/v1/chat/completions`, `/v1/embeddings`). The panel's
// Django calls it through the gateway in its own process, as the model the seed sets to answer
// (`assistant_seed.py panel http://127.0.0.1:<port>/v1`): no test reaches a real provider nor types a real key. What it
// answers depends on the conversation, as a model would, in the language the panel's instructions ask for:
// - «which businesses» (`negocios`, `businesses`): reads them (`hubs__business__list`), then names them and links
//   Businesses;
// - «create a business called <name>» (`crea`, `create`): asks for the write `hubs__business__create` with that name,
//   then says whether it ran (the person said no: nothing changed);
// - anything else: a short greeting.
// Each answer comes in pieces, a little apart, so the panel paints the bubble «writing» before the first word.
import { createServer, type IncomingMessage, type Server, type ServerResponse } from 'node:http';

/** The business the spec asks the assistant to create (and declines). */
export const NEW_BUSINESS = 'E2E Panel Nuevo';

export interface Message {
  role: string;
  content?: unknown;
  tool_call_id?: string;
  tool_calls?: { id?: string; type?: string; function?: { name?: string; arguments?: string } }[];
}

export interface Seen {
  path: string;
  body: Record<string, unknown> | null;
}

/** Milliseconds between two pieces of an answer. */
const PIECE_MS = 120;

function textOf(content: unknown): string {
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) {
    return content.map((part) => (part && typeof part === 'object' && 'text' in part ? String(part.text) : '')).join(' ');
  }
  return '';
}

/** Whether the panel's instructions ask for Spanish (base/assistant.py `instructions`: «Answer in Spanish»). */
function spanish(messages: Message[]): boolean {
  const system = messages.find((message) => message.role === 'system');
  return /Answer in Spanish/.test(textOf(system?.content));
}

/** Whether a tool's result says it did not run: `{"error": {"code": …}}` (live.assistant `error_content`). */
function refused(result: string): boolean {
  try {
    const answer = JSON.parse(result) as { error?: { code?: unknown } } | null;
    return typeof answer?.error?.code === 'string';
  } catch {
    return false;
  }
}

/** The names of the businesses `hubs.business.list` answered, in its order. */
function businessNames(result: string): string[] {
  try {
    const answer = JSON.parse(result) as { rows?: { name?: unknown }[] };
    return (answer.rows ?? []).map((row) => String(row.name ?? '')).filter(Boolean);
  } catch {
    return [];
  }
}

/** «A», «A y B», «A, B y C» (or «and»), each in bold. */
function listed(names: string[], and: string): string {
  const bold = names.map((name) => `**${name}**`);
  return bold.length > 1 ? `${bold.slice(0, -1).join(', ')} ${and} ${bold.at(-1)}` : (bold[0] ?? '');
}

const chunk = (delta: Record<string, unknown>, finish: string | null = null) => ({
  object: 'chat.completion.chunk',
  choices: [{ index: 0, delta, finish_reason: finish }],
});
const usage = { object: 'chat.completion.chunk', choices: [], usage: { prompt_tokens: 900, completion_tokens: 60 } };

export interface Answer {
  status: number;
  frames: unknown[];
  delayMs: number;
}

const text = (value: string): Answer => ({
  status: 200,
  delayMs: PIECE_MS,
  frames: [...value.match(/[\s\S]{1,24}/g)!.map((piece) => chunk({ content: piece })), chunk({}, 'stop'), usage],
});

/** A tool call in fragments, as OpenAI streams it. */
const call = (name: string, args: Record<string, unknown>): Answer => ({
  status: 200,
  delayMs: PIECE_MS,
  frames: [
    chunk({ tool_calls: [{ index: 0, id: `call_${Date.now().toString(36)}`, type: 'function', function: { name, arguments: '' } }] }),
    chunk({ tool_calls: [{ index: 0, function: { arguments: JSON.stringify(args) } }] }),
    chunk({}, 'tool_calls'),
    usage,
  ],
});

/** The answer to a conversation, as the frames of a stream. */
export function answerTo(messages: Message[]): Answer {
  const es = spanish(messages);
  const last = messages.at(-1);
  if (last?.role === 'tool') {
    const result = textOf(last.content);
    const asked = messages
      .flatMap((message) => message.tool_calls ?? [])
      .find((toolCall) => toolCall.id === last.tool_call_id)?.function?.name;
    if (asked === 'hubs__business__list') {
      const names = businessNames(result);
      if (!names.length) return text(es ? 'Todavía no tienes ningún negocio.' : 'You have no business yet.');
      return text(
        es
          ? `Tienes ${names.length} ${names.length === 1 ? 'negocio' : 'negocios'}: ${listed(names, 'y')}. Los ves en [Negocios](/dashboard/businesses).`
          : `You have ${names.length} ${names.length === 1 ? 'business' : 'businesses'}: ${listed(names, 'and')}. See them in [Businesses](/dashboard/businesses).`,
      );
    }
    if (asked === 'hubs__business__create') {
      if (refused(result)) {
        return text(es ? 'No he creado el negocio: no ha cambiado nada.' : 'I did not create the business: nothing changed.');
      }
      const name = businessNames(JSON.stringify({ rows: [JSON.parse(result) as unknown] }))[0] ?? NEW_BUSINESS;
      return text(es ? `Hecho: ${name} está creado.` : `Done: ${name} is created.`);
    }
    return text(refused(result) ? (es ? 'No lo he hecho.' : 'I did not do it.') : es ? 'Hecho.' : 'Done.');
  }
  const question = textOf([...messages].reverse().find((message) => message.role === 'user')?.content);
  const create = /\b(?:crea|create)\b.*?(?:llamado|called)\s+«?([^»?.]+)»?/i.exec(question);
  if (create) return call('hubs__business__create', { name: create[1].trim(), country: 'ES' });
  if (/negocios|businesses/i.test(question)) return call('hubs__business__list', {});
  return text(es ? 'Hola, soy el asistente de prueba.' : 'Hello, I am the test assistant.');
}

function read(request: IncomingMessage): Promise<Record<string, unknown> | null> {
  return new Promise((resolve) => {
    const parts: Buffer[] = [];
    request.on('data', (part: Buffer) => parts.push(part));
    request.on('end', () => {
      const raw = Buffer.concat(parts).toString('utf8');
      if (!raw) return resolve(null);
      try {
        resolve(JSON.parse(raw) as Record<string, unknown>);
      } catch {
        resolve({ raw: raw.slice(0, 200) });
      }
    });
  });
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export interface Provider {
  /** Its API's base address, `/v1` included (the provider's `base_url`). */
  url: string;
  seen: Seen[];
  close(): Promise<void>;
}

/** Starts the provider on `port` (0: any free one). */
export async function startProvider(port: number): Promise<Provider> {
  const seen: Seen[] = [];
  const server: Server = createServer(async (request: IncomingMessage, response: ServerResponse) => {
    const path = (request.url ?? '').split('?', 1)[0];
    const body = await read(request);
    seen.push({ path, body });
    const json = (status: number, value: unknown) => {
      response.writeHead(status, { 'Content-Type': 'application/json' });
      response.end(JSON.stringify(value));
    };
    if (request.method === 'GET' && path === '/v1/models') {
      return json(200, { object: 'list', data: [{ id: 'gpt-e2e-large', object: 'model' }, { id: 'gpt-e2e-mini', object: 'model' }] });
    }
    if (path === '/v1/embeddings') {
      const inputs = Array.isArray(body?.input) ? body.input : [body?.input];
      return json(200, {
        object: 'list',
        data: inputs.map((_, index) => ({ index, embedding: [0.1, 0.2, 0.3] })),
        usage: { prompt_tokens: 4, total_tokens: 4 },
      });
    }
    if (path === '/v1/chat/completions') {
      const answer = answerTo((body?.messages as Message[] | undefined) ?? []);
      response.writeHead(200, { 'Content-Type': 'text/event-stream' });
      for (const frame of answer.frames) {
        response.write(`data: ${JSON.stringify(frame)}\n\n`);
        if (answer.delayMs) await sleep(answer.delayMs);
      }
      response.end('data: [DONE]\n\n');
      return;
    }
    json(404, { error: { message: `No route ${request.method} ${path}` } });
  });
  await new Promise<void>((resolve, reject) => {
    server.once('error', reject);
    server.listen(port, '127.0.0.1', () => resolve());
  });
  const address = server.address();
  const bound = typeof address === 'object' && address ? address.port : port;
  return {
    url: `http://127.0.0.1:${bound}/v1`,
    seen,
    close: () =>
      new Promise((resolve) => {
        server.closeAllConnections();
        server.close(() => resolve());
      }),
  };
}
