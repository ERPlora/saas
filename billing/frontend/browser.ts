// What the Billing section asks of the browser itself, in one place (the tests watch it instead of leaving
// the page):
//   - `assign`: a top-level navigation to Stripe (its page to pay an invoice, its Customer Portal);
//   - `download`: a file the API answers as an attachment (an invoice's PDF, the CSV of the list), asked for
//     by the SDK (`fetchFile`: the session cookie, its `Accept`) and saved only when the answer IS that file
//     (audit 2026-10-14, R-05: a link with `download` saved the 503 of the invoice service as `pdf.json`, and
//     the page said nothing). Any other answer is thrown as the API's error, and no answer at all as the SDK's
//     `network_error` in the person's language (hub#2281), for the page to say it.
import { fetchFile, type InputOf, type OpName } from '@erplora/ui/sdk';

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
    const file = await fetchFile(url, type);
    save(file.blob, file.name || FALLBACK_NAMES[type]);
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
