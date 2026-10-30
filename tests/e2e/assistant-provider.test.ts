// @vitest-environment node
// The AI provider of the panel's assistant's e2e (assistant-provider.ts): what it answers to each conversation, in
// OpenAI's streamed shape, as the gateway of the panel's Django reads it, and its server on 127.0.0.1.
import { afterEach, describe, expect, it } from 'vitest';

import { answerTo, type Message, NEW_BUSINESS, startProvider } from './assistant-provider';

type Chunk = { choices: { delta: { content?: string; tool_calls?: { function: { name?: string; arguments?: string } }[] }; finish_reason: string | null }[] };

const SPANISH = { role: 'system', content: 'You are the assistant of erplora.com… Answer in Spanish, short and plain.' };
const ENGLISH = { role: 'system', content: 'You are the assistant of erplora.com… Answer in English, short and plain.' };

/** What a streamed answer says, in one piece. */
function said(frames: unknown[]): string {
  return (frames as Chunk[]).flatMap((chunk) => chunk.choices ?? []).map((choice) => choice.delta.content ?? '').join('');
}

/** The tool a streamed answer asks for, with its arguments in one piece. */
function asked(frames: unknown[]): { name: string; arguments: string } | null {
  const calls = (frames as Chunk[]).flatMap((chunk) => chunk.choices ?? []).flatMap((choice) => choice.delta.tool_calls ?? []);
  if (!calls.length) return null;
  return { name: calls.map((call) => call.function.name ?? '').join(''), arguments: calls.map((call) => call.function.arguments ?? '').join('') };
}

/** A conversation where the model asked for `name` and the tool answered `content`. */
function answered(system: Message, question: string, name: string, content: string): Message[] {
  return [
    system,
    { role: 'user', content: question },
    { role: 'assistant', content: '', tool_calls: [{ id: 'call_1', type: 'function', function: { name, arguments: '{}' } }] },
    { role: 'tool', tool_call_id: 'call_1', content },
  ];
}

describe('answerTo', () => {
  it('reads the businesses when asked which ones there are, in Spanish or in English', () => {
    expect(asked(answerTo([SPANISH, { role: 'user', content: '¿Qué negocios tengo?' }]).frames)).toEqual({
      name: 'hubs__business__list',
      arguments: '{}',
    });
    expect(asked(answerTo([ENGLISH, { role: 'user', content: 'Which businesses do I have?' }]).frames)?.name).toBe(
      'hubs__business__list',
    );
  });

  it('names the businesses the read returned, in the language of the instructions, linking the screen', () => {
    const rows = JSON.stringify({ rows: [{ name: 'E2E Asistente Panel' }, { name: 'Bar Lena' }], total: 2 });

    const es = said(answerTo(answered(SPANISH, '¿Qué negocios tengo?', 'hubs__business__list', rows)).frames);
    const en = said(answerTo(answered(ENGLISH, 'Which businesses do I have?', 'hubs__business__list', rows)).frames);

    expect(es).toBe('Tienes 2 negocios: **E2E Asistente Panel** y **Bar Lena**. Los ves en [Negocios](/dashboard/businesses).');
    expect(en).toBe('You have 2 businesses: **E2E Asistente Panel** and **Bar Lena**. See them in [Businesses](/dashboard/businesses).');
  });

  it('says it when the read found none', () => {
    const none = JSON.stringify({ rows: [], total: 0 });
    expect(said(answerTo(answered(ENGLISH, 'Which businesses do I have?', 'hubs__business__list', none)).frames)).toBe(
      'You have no business yet.',
    );
  });

  it('asks to create the business it is told to create, by its name', () => {
    const answer = answerTo([SPANISH, { role: 'user', content: `Crea un negocio llamado ${NEW_BUSINESS}` }]);
    expect(asked(answer.frames)).toEqual({
      name: 'hubs__business__create',
      arguments: JSON.stringify({ name: NEW_BUSINESS, country: 'ES' }),
    });
  });

  it('says nothing was created when the person said no, and that it was when it ran', () => {
    const refused = JSON.stringify({ error: { code: 'base.assistant_not_confirmed', message: 'Not confirmed.' } });
    const created = JSON.stringify({ id: 'b1', name: NEW_BUSINESS });
    const question = `Create a business called ${NEW_BUSINESS}`;

    expect(said(answerTo(answered(ENGLISH, question, 'hubs__business__create', refused)).frames)).toBe(
      'I did not create the business: nothing changed.',
    );
    expect(said(answerTo(answered(SPANISH, question, 'hubs__business__create', refused)).frames)).toBe(
      'No he creado el negocio: no ha cambiado nada.',
    );
    expect(said(answerTo(answered(ENGLISH, question, 'hubs__business__create', created)).frames)).toBe(
      `Done: ${NEW_BUSINESS} is created.`,
    );
  });

  it('greets anything else', () => {
    expect(said(answerTo([ENGLISH, { role: 'user', content: 'Hello' }]).frames)).toBe('Hello, I am the test assistant.');
    expect(said(answerTo([SPANISH, { role: 'user', content: 'Hola' }]).frames)).toBe('Hola, soy el asistente de prueba.');
  });

  it('ends every answer as OpenAI does: its finish, then its usage', () => {
    const frames = answerTo([ENGLISH, { role: 'user', content: 'Hello' }]).frames as Array<Record<string, unknown>>;
    const finishes = (frames as Chunk[]).flatMap((chunk) => chunk.choices ?? []).map((choice) => choice.finish_reason).filter(Boolean);
    expect(finishes).toEqual(['stop']);
    expect(frames.at(-1)).toMatchObject({ choices: [], usage: { prompt_tokens: expect.any(Number) } });
  });
});

describe('startProvider', () => {
  let close: (() => Promise<void>) | undefined;

  afterEach(async () => {
    await close?.();
    close = undefined;
  });

  it('serves the models, a streamed answer ending in [DONE], and remembers what was asked', async () => {
    const provider = await startProvider(0);
    close = provider.close;

    const models = await (await fetch(`${provider.url}/models`)).json();
    const answer = await fetch(`${provider.url}/chat/completions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages: [ENGLISH, { role: 'user', content: 'Hello' }], stream: true }),
    });
    const text = await answer.text();

    expect(models.data.map((model: { id: string }) => model.id)).toContain('gpt-e2e-large');
    expect(answer.headers.get('content-type')).toBe('text/event-stream');
    expect(text.trim().endsWith('data: [DONE]')).toBe(true);
    expect(text).toContain('Hello, I am the test assistant.'.slice(0, 10));
    expect(provider.seen.map((request) => request.path)).toEqual(['/v1/models', '/v1/chat/completions']);
  });

  it('answers 404 to a path it does not serve', async () => {
    const provider = await startProvider(0);
    close = provider.close;
    expect((await fetch(`${provider.url}/nothing`)).status).toBe(404);
  });
});
