// The environment of every Django process the e2e starts: the servers (playwright.config.ts,
// panel/project.ts), globalSetup's `manage.py` and the seeds and helpers of the specs. Django reads DEBUG
// as a boolean (config/settings.py, `cast=bool`), and Playwright the same variable as the namespaces of
// its logs (`DEBUG=pw:webserver`, README.md): inherited, `manage.py migrate --check` stopped the run before
// the first spec (`Invalid truth value: pw:webserver`). So each one says the DEBUG it runs with, here.
// And the database: a stack beside the shared one opens its own e2e database (stack.ts) in every one of them,
// the public server included, whose `env` Playwright lays over its own environment.

import { STACK, type Stack } from './stack.ts';

/**
 * `env` (this process's by default) with Django's DEBUG on or off and the `DB_NAME` of `stack`'s own database
 * (the shared stack's is left to `.env`); the unset variables left out.
 */
export function djangoEnv(
  debug: boolean,
  env: NodeJS.ProcessEnv = process.env,
  stack: Pick<Stack, 'database'> = STACK,
): Record<string, string> {
  const result: Record<string, string> = {};
  for (const [name, value] of Object.entries(env)) {
    if (value !== undefined) result[name] = value;
  }
  result.DEBUG = debug ? 'True' : 'False';
  if (stack.database !== undefined) result.DB_NAME = stack.database;
  return result;
}
