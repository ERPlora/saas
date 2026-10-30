// Where the e2e's servers listen and which database they open (README.md, «Dos e2e del SaaS a la vez»).
// The shared stack is the one of every run that exports nothing: the public server on :8011, the panel's Django on :8012,
// its twin with the second factor on at :8013 (panel/project.ts), the Hub the specs play on :8019 and the `saas` of
// `.env`. A second run at once moves the four ports together with one variable, E2E_SAAS_PORT (8030: :8031, :8032, :8033, :8039), so that it can never leave one of
// them behind (two panels sending their Hub calls to one double), and runs on a database of its own,
// `saas_e2e_<port>`, which its first server creates and migrates (database.ts): two runs on the one `saas`
// write into each other's data. The rest of the e2e reads them here (playwright.config.ts, panel/project.ts,
// django-env.ts, database.ts).
//
// Refused before the first server starts: a stack beside the shared one on `saas`, and a database that is
// not the SaaS's, such as the Hub's `DB_NAME` a shell exports for its own stack (`hub_e2e_8030`; the SaaS
// opened it and its login failed with `relation "django_site" does not exist`).

type Env = Record<string, string | undefined>;

export interface Stack {
  /** E2E_SAAS_PORT, the block the stack's ports come from (8010 by default). */
  base: number;
  /** Whether it is the shared stack: today's ports. */
  shared: boolean;
  /** The public server's port (`base + 1`). */
  publicPort: number;
  /** The panel's Django's port (`base + 2`). */
  panelPort: number;
  /** The port of the panel's twin with the second factor on (`base + 3`; ACCOUNTS_MFA_ENABLED is off by default). */
  panelMfaPort: number;
  /** Where the public server calls the Hub (`HUB_INTERNAL_URL`): the demo a spec plays (`base + 4`; demo-wait.spec.ts). */
  publicHubDoublePort: number;
  /** The AI provider the assistant's specs start, assistant.tests.fake_provider (`base + 7`). */
  aiProviderPort: number;
  /** Where the public server asks reCAPTCHA's assessments (`RECAPTCHA_ENDPOINT`), the double of recaptcha-double.ts (`base + 8`). */
  recaptchaDoublePort: number;
  /** Where the panel's Django calls the Hub (`HUB_INTERNAL_URL`), which a spec plays (`base + 9`). */
  hubDoublePort: number;
  /** The run's own e2e database, which every Django process opens (`DB_NAME`); `undefined`: `.env`'s `saas`. */
  database: string | undefined;
}

/** The shared stack's block (:8011, :8012, :8013, :8019) and its database. */
export const SHARED_BASE = 8010;
const SHARED_DATABASE = 'saas';
/** The highest port of a block, from its base. */
const LAST_OFFSET = 9;

const RECIPE = 'tests/e2e/README.md, «Dos e2e del SaaS a la vez»';
const E2E_DATABASE = '`saas_…` with `e2e` as one of its words';

/** An e2e database: `saas_…` with `e2e` as one of its words (`saas_e2e_8030`, `saas_fix_e2e_a`). The only kind a
 *  stack beside the shared one runs on, and the only kind `database.ts` creates, migrates or drops. */
export function isE2eDatabase(name: string): boolean {
  return /^saas(?:_[a-z0-9]+)*_e2e(?:_[a-z0-9]+)*$/.test(name);
}

function baseOf(env: Env): number {
  const raw = env.E2E_SAAS_PORT;
  if (raw === undefined || raw === '') return SHARED_BASE;
  const value = Number(raw);
  if (!/^\d+$/.test(raw) || value <= 0 || value + LAST_OFFSET >= 65536) {
    throw new Error(
      `E2E_SAAS_PORT must be a TCP port with ${LAST_OFFSET} more above it (the stack's ports run up to +${LAST_OFFSET}), ` +
        `not ${JSON.stringify(raw)}.`,
    );
  }
  return value;
}

/** The exported DB_NAME, or `undefined`. It goes into a shell command (`psql -c …`) as is. */
function exportedDatabase(env: Env): string | undefined {
  const raw = env.DB_NAME;
  if (raw === undefined || raw === '') return undefined;
  if (!/^[a-z_][a-z0-9_]*$/.test(raw)) {
    throw new Error(`DB_NAME must be a plain database name, not ${JSON.stringify(raw)}.`);
  }
  return raw;
}

/** The run's own database, `undefined` for the shared `saas`, or the refusal that names the way out. */
function databaseOf(env: Env, base: number): string | undefined {
  const name = exportedDatabase(env);
  if (name !== undefined && isE2eDatabase(name)) return name;
  if (base === SHARED_BASE) {
    if (name === undefined || name === SHARED_DATABASE) return undefined;
    throw new Error(
      `DB_NAME=${name} is no database of the SaaS: the e2e runs on the shared \`${SHARED_DATABASE}\` (unset DB_NAME, ` +
        `\`env -u DB_NAME\`, and the one of \`.env\` is used) or on an e2e database (${E2E_DATABASE}).`,
    );
  }
  const own = `saas_e2e_${base}`;
  if (name === undefined) return own;
  throw new Error(
    `A stack beside the shared one (E2E_SAAS_PORT=${base}) runs on its own e2e database, not on DB_NAME=${name}: ` +
      `another run would write into it. Unset DB_NAME (\`env -u DB_NAME\`) for ${own}, or export an e2e database ` +
      `(${E2E_DATABASE}) (${RECIPE}).`,
  );
}

export function stackFrom(env: Env): Stack {
  const base = baseOf(env);
  return {
    base,
    shared: base === SHARED_BASE,
    publicPort: base + 1,
    panelPort: base + 2,
    panelMfaPort: base + 3,
    publicHubDoublePort: base + 4,
    aiProviderPort: base + 7,
    recaptchaDoublePort: base + 8,
    hubDoublePort: base + LAST_OFFSET,
    database: databaseOf(env, base),
  };
}

/** The stack of this run, from its environment. */
export const STACK = stackFrom(process.env);
