// What the Billing section asks of the browser itself, in one place (the tests watch it instead of leaving
// the page):
//   - `assign`: a top-level navigation to Stripe (its page to pay an invoice, its Customer Portal);
//   - `download`: a file the API answers as an attachment (an invoice's PDF, the CSV of the list), asked for
//     with the session cookie and saved only when the answer IS that file (audit 2026-10-14, R-05: a link
//     with `download` saved the 503 of the invoice service as `pdf.json`, and the page said nothing). Any
//     other answer is thrown as the API's error (`parseErrorEnvelope`), for the page to say it.
// The one raw `fetch` of the SPA: the SDK's `api.call` reads JSON only and a file needs its bytes.
import { ApiError, type InputOf, type OpName, parseErrorEnvelope } from '@erplora/ui/sdk';

import { OPERATION_ROUTES } from '../../frontend/generated/operation-routes';

/** The files Billing downloads, by the type it asks for. */
export type FileType = 'application/pdf' | 'text/csv';

/** Its name when the server gives none. */
const FALLBACK_NAMES: Readonly<Record<FileType, string>> = {
  'application/pdf': 'invoice.pdf',
  'text/csv': 'invoices.csv',
};

/** How long the saved file's object URL lives: the browser has started the download well before. */
export const REVOKE_AFTER_MS = 10_000;

/** The file name of a `Content-Disposition` header (RFC 6266: `filename*` first, then `filename`); `''` without one. */
export function attachmentName(header: string | null): string {
  if (!header) return '';
  const encoded = /filename\*\s*=\s*[\w-]+'[^']*'([^;]+)/i.exec(header);
  if (encoded) {
    try {
      return decodeURIComponent(encoded[1].trim().replace(/^"(.*)"$/, '$1'));
    } catch {
      // A malformed encoded name: the plain one, if any.
    }
  }
  const plain = /filename\s*=\s*(?:"([^"]*)"|([^;]+))/i.exec(header);
  return plain ? (plain[1] ?? plain[2] ?? '').trim() : '';
}

/** Saves `blob` as `name` through a same-origin link, and lets its object URL go afterwards. */
function save(blob: Blob, name: string): void {
  const href = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = href;
  link.download = name;
  link.rel = 'noopener';
  link.hidden = true;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(href), REVOKE_AFTER_MS);
}

export const browser = {
  assign(url: string): void {
    window.location.assign(url);
  },
  /** Downloads the file of `url` as `type`; throws the API's error (an `ApiError`) when the answer is not it. */
  async download(url: string, type: FileType): Promise<void> {
    let response: Response;
    try {
      // eslint-disable-next-line no-restricted-globals -- the SDK's api.call reads JSON only and a file needs its bytes; follow-up: a download helper in @erplora/ui/sdk
      response = await fetch(url, { headers: { Accept: type }, credentials: 'same-origin' });
    } catch (error) {
      const reason = error instanceof Error ? error.message : String(error);
      throw new ApiError(0, 'network_error', `Network error (${reason})`);
    }
    const contentType = (response.headers.get('Content-Type') ?? '').split(';')[0].trim().toLowerCase();
    if (!response.ok || contentType !== type) {
      throw parseErrorEnvelope(response.status, await response.text().catch(() => undefined));
    }
    save(await response.blob(), attachmentName(response.headers.get('Content-Disposition')) || FALLBACK_NAMES[type]);
  },
};

/** The address of a query `op` with `input` as its query string (`null`, `undefined` and `''` left out). */
export function operationUrl<Op extends OpName>(op: Op, input: InputOf<Op>): string {
  const route = OPERATION_ROUTES[op];
  if (!route || route.method !== 'get') throw new Error(`billing: ${op} is not a query, it cannot be downloaded`);
  const query = new URLSearchParams();
  for (const [name, value] of Object.entries((input ?? {}) as Record<string, unknown>)) {
    if (value === null || value === undefined || value === '') continue;
    query.append(name, String(value));
  }
  const text = query.toString();
  return text ? `${route.path}?${text}` : route.path;
}
