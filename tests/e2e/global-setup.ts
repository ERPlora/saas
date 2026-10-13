// Seeds the app the store's specs open (store_docs_seed.py) and returns the teardown that removes it,
// so the local database is left as it was even when a spec fails.
import { execFileSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const SAAS_DIR = resolve(HERE, '..', '..');

function seed(action: 'seed' | 'clear'): void {
  execFileSync('uv', ['run', 'python', 'tests/e2e/store_docs_seed.py', action], {
    cwd: SAAS_DIR,
    stdio: 'inherit',
  });
}

export default function globalSetup(): () => void {
  seed('seed');
  return () => seed('clear');
}
