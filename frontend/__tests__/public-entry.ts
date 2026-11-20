// What the tests of the public web's entry share (public.test.ts, public.navbar.test.ts): the source of
// `frontend/public.ts`, where the public templates are, and a page to run the code on.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const FRONTEND = join(dirname(fileURLToPath(import.meta.url)), '..');
export const SAAS_DIR = join(FRONTEND, '..');
export const SOURCE = readFileSync(join(FRONTEND, 'public.ts'), 'utf8');
export const PUBLIC_TEMPLATES = join(SAAS_DIR, 'public', 'templates');

export function page(html: string): Document {
  document.documentElement.className = '';
  document.body.innerHTML = html;
  return document;
}
