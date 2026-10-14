// What the Billing section asks of the browser itself, in one place (the tests watch it instead of leaving
// the page):
//   - `assign`: a top-level navigation to Stripe (its page to pay an invoice, its Customer Portal);
//   - `download`: a file the API answers as an attachment (an invoice's PDF, the CSV of the list), fetched
//     by the browser with the session cookie through a same-origin link. Not a `fetch` of ours: the SPA
//     reaches the server only through the SDK (eslint `no-restricted-globals`), and the SDK's `api.call`
//     reads JSON. What a PDF not issued yet would answer (404) is known before: the row's `can.pdf`.
import type { InputOf, OpName } from '@erplora/ui/sdk';

import { OPERATION_ROUTES } from '../../frontend/generated/operation-routes';

export const browser = {
  assign(url: string): void {
    window.location.assign(url);
  },
  download(url: string): void {
    const link = document.createElement('a');
    link.href = url;
    link.download = '';
    link.rel = 'noopener';
    link.hidden = true;
    document.body.append(link);
    link.click();
    link.remove();
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
