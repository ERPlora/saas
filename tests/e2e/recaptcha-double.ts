// Google's reCAPTCHA Enterprise assessments, played for the e2e: the public server (production-like, so reCAPTCHA
// is on and cannot be switched off) asks this one instead (`RECAPTCHA_ENDPOINT`, playwright.config.ts), and its
// pages get the fake enterprise.js of recaptcha.ts. So no run depends on the network nor on how Google scores a
// headless Chrome, and a refused form is a token the spec chose.
//
//   node tests/e2e/recaptcha-double.ts <port>       Playwright starts it as a web server of the run
//
// A token reads `e2e-human:<action>` (valid, made for <action>, score 0.9) or `e2e-bot:<action>` (score 0.1);
// anything else is malformed, as Google answers a token it did not make. `GET /assessments` lists what it was asked
// (`{token, expectedAction}`), `GET /healthz` says it is up. Run by Node itself, without Playwright's loader.
import { createServer, type IncomingMessage, type Server, type ServerResponse } from 'node:http';
import type { AddressInfo } from 'node:net';
import { pathToFileURL } from 'node:url';

/** What the server sends Google (`event`), as far as the double reads it. */
export interface AssessmentEvent {
  token?: unknown;
  expectedAction?: unknown;
}

/** Google's answer, as far as live.recaptcha reads it. */
export interface Assessment {
  tokenProperties: { valid: boolean; action?: string; hostname?: string; invalidReason?: string };
  riskAnalysis: { score: number; reasons: string[] };
}

const KINDS: Record<string, { score: number; reasons: string[] }> = {
  'e2e-human': { score: 0.9, reasons: [] },
  'e2e-bot': { score: 0.1, reasons: ['AUTOMATION'] },
};

/** Google's assessment of an e2e token. */
export function assessmentOf(event: AssessmentEvent): Assessment {
  const token = typeof event.token === 'string' ? event.token : '';
  const separator = token.indexOf(':');
  const kind = separator > 0 ? KINDS[token.slice(0, separator)] : undefined;
  if (!kind) return { tokenProperties: { valid: false, invalidReason: 'MALFORMED' }, riskAnalysis: { score: 0, reasons: [] } };
  return {
    tokenProperties: { valid: true, action: token.slice(separator + 1), hostname: 'localhost' },
    riskAnalysis: { score: kind.score, reasons: kind.reasons },
  };
}

export interface RecaptchaDouble {
  port: number;
  close(): Promise<void>;
}

function send(res: ServerResponse, status: number, body: unknown): void {
  res.writeHead(status, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(body));
}

async function bodyOf(req: IncomingMessage): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const chunk of req) chunks.push(chunk as Buffer);
  return Buffer.concat(chunks).toString('utf8');
}

/** The double on `port` (0: any free one) of 127.0.0.1. */
export function startRecaptchaDouble(port: number): Promise<RecaptchaDouble> {
  const asked: Array<{ token: unknown; expectedAction: unknown }> = [];
  const server: Server = createServer((req, res) => {
    const path = (req.url ?? '/').split('?')[0];
    if (req.method === 'GET' && path === '/healthz') return send(res, 200, { status: 'ok' });
    if (req.method === 'GET' && path === '/assessments') return send(res, 200, asked);
    if (req.method !== 'POST' || !/^\/v1\/projects\/[^/]+\/assessments$/.test(path)) return send(res, 404, { error: 'not found' });
    void bodyOf(req).then((raw) => {
      let event: AssessmentEvent | undefined;
      try {
        event = (JSON.parse(raw) as { event?: AssessmentEvent }).event;
      } catch {
        event = undefined;
      }
      if (!event || typeof event !== 'object') return send(res, 400, { error: { code: 400, message: 'no event' } });
      asked.push({ token: event.token, expectedAction: event.expectedAction });
      return send(res, 200, assessmentOf(event));
    });
  });
  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(port, '127.0.0.1', () => {
      resolve({
        port: (server.address() as AddressInfo).port,
        close: () => new Promise<void>((done) => server.close(() => done())),
      });
    });
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const port = Number(process.argv[2]);
  if (!Number.isInteger(port) || port <= 0) {
    console.error('Usage: node tests/e2e/recaptcha-double.ts <port>');
    process.exitCode = 2;
  } else {
    void startRecaptchaDouble(port).then((double) => console.log(`recaptcha double on 127.0.0.1:${double.port}`));
  }
}
