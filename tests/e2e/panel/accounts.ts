import { execFileSync } from 'node:child_process';

import { djangoEnv } from '../django-env';
import { djangoPrint, djangoPrintAsync, djangoPrintWarm, SAAS_DIR } from './django';

/** A SaaS account: what its sign-in asks for. */
export interface Credentials {
  email: string;
  password: string;
}

/**
 * `demo_seed`'s customer: owner of the local hubs `a` and `b`, no admin and no name of its own. The QA users of
 * the root `.env` (`QA_OWNER_*`) name it, with these as their defaults (playwright.config.ts loads them).
 */
export const OWNER: Credentials = {
  email: process.env.QA_OWNER_EMAIL ?? 'owner@example.com',
  password: process.env.QA_OWNER_PASSWORD ?? 'owner',
};

/**
 * `manage.py demo_seed`, against the database of `.env`: it creates the local accounts that are
 * missing and leaves the rest as they are. It refuses to run without DEBUG, hence `DEBUG=True`.
 */
export function seedAccounts(): void {
  execFileSync('uv', ['run', 'python', 'manage.py', 'demo_seed'], {
    cwd: SAAS_DIR,
    env: djangoEnv(true),
    stdio: 'pipe',
  });
}

/**
 * The accounts of `panel_seed.py` (`e2e-<name>@example.com`), all with the same password: `QA_PANEL_PASSWORD`
 * of the root `.env` (playwright.config.ts loads it), the seed's own default otherwise.
 */
export const panelAccount = (name: string): Credentials => ({
  email: `e2e-${name}@example.com`,
  password: process.env.QA_PANEL_PASSWORD ?? 'e2e-panel',
});

/**
 * A QA user of the root `.env` (`QA_<ROLE>_EMAIL`, `QA_<ROLE>_PASSWORD`, README «Usuarios QA») when exported,
 * else `fallback`: the same values its seed falls back to (`billing_seed.py`, `store_seed.py`).
 */
export const qaAccount = (role: string, fallback: Credentials): Credentials => ({
  email: process.env[`QA_${role}_EMAIL`] ?? fallback.email,
  password: process.env[`QA_${role}_PASSWORD`] ?? fallback.password,
});

/** A fresh account of a spec, its address proven, speaking `language` (the account's language wins on the panel). */
export function provenAccount(email: string, password: string, language: 'en' | 'es' = 'en'): void {
  djangoPrint(
    [
      'from allauth.account.models import EmailAddress',
      'from django.contrib.auth import get_user_model',
      `user = get_user_model().objects.create_user(email=${JSON.stringify(email)}, password=${JSON.stringify(password)}, language="${language}")`,
      'EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)',
    ].join('\n'),
  );
}

/**
 * The snippet that removes what a spec leaves behind: the businesses and the accounts whose email starts with `prefix`,
 * and the billing profiles they would leave ownerless (as panel_seed.py's `clear`): the accounts' own (`owner` is
 * SET_NULL) and the ownerless ones of the businesses, after the businesses (their PROTECT). Another account's profile
 * stays, even one that paid a business a spec's account worked in. A profile of theirs still there fails the snippet.
 * Its own tests: config/tests/test_e2e_removing_accounts.py.
 */
const removingAccountsOf = (prefix: string) =>
  [
    'from django.contrib.auth import get_user_model',
    'from hubs.models import BillingProfile, Hub',
    `users = get_user_model().objects.filter(email__startswith=${JSON.stringify(prefix)})`,
    `hubs = Hub.objects.filter(members__user__email__startswith=${JSON.stringify(prefix)})`,
    'profiles = {*hubs.filter(billing_profile__owner=None).values_list("billing_profile_id", flat=True), *BillingProfile.objects.filter(owner__in=users).values_list("pk", flat=True)} - {None}',
    'hubs.delete()',
    'BillingProfile.objects.filter(pk__in=profiles).delete()',
    'users.delete()',
    'left = BillingProfile.objects.filter(pk__in=profiles).count()',
    'if left:',
    '    raise RuntimeError(f"{left} billing profiles of the removed businesses and accounts left behind")',
  ].join('\n');

/** What a spec leaves behind: the businesses and the accounts whose email starts with its `prefix` (`e2e-<spec>-`). */
export function removeAccountsOf(prefix: string): void {
  djangoPrint(removingAccountsOf(prefix));
}

/**
 * `seedAccounts` without blocking this process (the same `demo_seed`, run by `djangoPrintAsync`): while it runs, what
 * lives in this process (the Hub or Stripe a spec plays, the timers) keeps answering, and a timeout can fire. A failing
 * seed rejects, its traceback in the error.
 */
export async function seedAccountsAsync(): Promise<void> {
  await djangoPrintAsync('from django.core.management import call_command\ncall_command("demo_seed")');
}

/**
 * Who a spec's account is: a customer (`create_user`), Django's superuser (`create_superuser`), or a team account of
 * ERPlora (`accounts.services.platform_staff.create_platform_user`, with its group: the platform's admin or its
 * support).
 */
export type AccountRole = 'customer' | 'superuser' | 'platform-admin' | 'platform-support';

export interface AccountOptions {
  role?: AccountRole;
  /** Its address proven (the default), as an account that signed in before; `false`, never proven. */
  verified?: boolean;
  firstName?: string;
  lastName?: string;
  /** The account's language (the panel speaks it once signed in); the model's own when left out. */
  language?: 'en' | 'es';
}

/** A fresh account of a spec, `email` with `password` and `options`, written by the warm Django: its credentials. */
export async function createAccountWarm(email: string, password: string, options: AccountOptions = {}): Promise<Credentials> {
  const { role = 'customer', verified = true, firstName, lastName, language } = options;
  const fields = Object.entries({ first_name: firstName, last_name: lastName, language }).filter(
    (field): field is [string, string] => field[1] !== undefined,
  );
  const said = (value: string) => JSON.stringify(value);
  const kwargs = [`email=${said(email)}`, `password=${said(password)}`, ...fields.map(([name, value]) => `${name}=${said(value)}`)];
  const group = role === 'platform-admin' ? 'platform_staff.PLATFORM_ADMIN' : 'platform_staff.PLATFORM_SUPPORT';
  const made =
    role === 'customer' || role === 'superuser'
      ? [`user = get_user_model().objects.${role === 'customer' ? 'create_user' : 'create_superuser'}(${kwargs.join(', ')})`]
      : [
          `user = platform_staff.create_platform_user(${said(email)}, ${group}, ${said(password)})[0]`,
          ...fields.map(([name, value]) => `user.${name} = ${said(value)}`),
          `user.save(update_fields=[${fields.map(([name]) => said(name)).join(', ')}])`,
        ];
  await djangoPrintWarm(
    [
      'from allauth.account.models import EmailAddress',
      'from django.contrib.auth import get_user_model',
      'from accounts.services import platform_staff',
      ...made,
      `EmailAddress.objects.update_or_create(user=user, email=user.email, defaults={"verified": ${verified ? 'True' : 'False'}, "primary": True})`,
    ].join('\n'),
  );
  return { email, password };
}

/** `removeAccountsOf` through the warm Django: the businesses and the accounts whose email starts with `prefix`. */
export async function removeAccountsWarm(prefix: string): Promise<void> {
  await djangoPrintWarm(removingAccountsOf(prefix));
}
