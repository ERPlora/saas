import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const FOLDER = join(dirname(fileURLToPath(import.meta.url)), '..', 'sdk-types');

/** Every hand-written type of `frontend/sdk-types/`, its files one after the other. */
export function readSdkTypes(): string {
  return readdirSync(FOLDER)
    .filter((file) => file.endsWith('.d.ts'))
    .sort()
    .map((file) => readFileSync(join(FOLDER, file), 'utf8'))
    .join('\n');
}
