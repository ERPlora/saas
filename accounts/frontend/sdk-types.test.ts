// The Account page's twins in `frontend/sdk-types.d.ts`, written by hand from accounts/schemas.py until they are
// generated from `/api/openapi.json`: this guard reads both and fails when a field the server sends or takes is
// missing from its TypeScript twin, the twin carries one the server no longer has, or a field's type differs
// (pydantic's annotation translated to what its JSON is in TypeScript).
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const HERE = dirname(fileURLToPath(import.meta.url));
const PYTHON = readFileSync(join(HERE, '..', 'schemas.py'), 'utf8');
const TYPES = readFileSync(join(HERE, '..', '..', 'frontend', 'sdk-types.d.ts'), 'utf8');

/** `name: annotation` of a pydantic schema of accounts/schemas.py (a default is cut at ` = `). */
function pythonTypes(name: string): Record<string, string> {
  const match = new RegExp(`^class ${name}\\(([^)]*)\\):\\n((?:(?:    .*)?\\n)*)`, 'm').exec(PYTHON);
  if (!match) throw new Error(`accounts/schemas.py has no class ${name}`);
  const own = [...match[2].matchAll(/^ {4}(\w+): (.+?)(?: = .*)?$/gm)].map((m) => [m[1], m[2].trim()] as const);
  return Object.fromEntries(own);
}

/** `name: type` of an interface of sdk-types.d.ts, `?` kept on the name's side (`name?`). */
function typeTypes(name: string): Record<string, string> {
  const match = new RegExp(`^export interface ${name} \\{\\n([\\s\\S]*?)^\\}`, 'm').exec(TYPES);
  if (!match) throw new Error(`sdk-types.d.ts has no interface ${name}`);
  return Object.fromEntries([...match[1].matchAll(/^ {2}(\w+\??): (.+);$/gm)].map((m) => [m[1], m[2].trim()]));
}

const SCALARS: Record<string, string> = {
  UUID: 'string',
  str: 'string',
  datetime: 'string',
  int: 'number',
  bool: 'boolean',
  // The two literals of accounts/schemas.py, by their TypeScript names.
  ThemeMode: 'AccountThemeMode',
  Language: 'AccountLanguage',
};

function toTypeScript(annotation: string): string {
  return annotation
    .split('|')
    .map((part) => part.trim())
    .map((part) => {
      if (part === 'None') return 'null';
      const literal = /^Literal\[(.+)\]$/.exec(part);
      if (literal) return literal[1].split(',').map((v) => v.trim().replace(/^"(.*)"$/, "'$1'")).join(' | ');
      const list = /^list\[(.+)\]$/.exec(part);
      if (list) return `${toTypeScript(list[1])}[]`;
      return SCALARS[part] ?? part;
    })
    .join(' | ');
}

const union = (type: string) =>
  type
    .split('|')
    .map((part) => part.trim())
    .sort()
    .join(' | ');

/** Every schema of the Account page the panel reads or sends, by its name on both sides. */
const SCHEMAS = [
  'PreferencesOut',
  'PreferencesUpdateIn',
  'ProfileOut',
  'ProfileUpdateIn',
  'ProfileDeletedOut',
  'EmailChangeIn',
  'EmailVerifyIn',
  'EmailVerifyOut',
  'PhotoUploadIn',
  'SessionRowOut',
  'SessionListOut',
  'SessionCloseIn',
  'SessionsClosedOut',
  'ApiKeyRowOut',
  'ApiKeyScopeOut',
  'ApiKeyListOut',
  'ApiKeyCreateIn',
  'ApiKeyCreatedOut',
  'ApiKeyRevokeIn',
];

describe('sdk-types.d.ts follows accounts/schemas.py (the Account page)', () => {
  it.each(SCHEMAS)('%s has the same fields, each typed as its JSON is', (name) => {
    const python = pythonTypes(name);
    const types = typeTypes(name);
    expect(Object.keys(types).map((field) => field.replace(/\?$/, '')).sort()).toEqual(Object.keys(python).sort());
    for (const [field, annotation] of Object.entries(python)) {
      const optional = `${field}?` in types;
      const ts = types[optional ? `${field}?` : field];
      let expected = toTypeScript(annotation);
      // An input the SPA leaves out (`field?`) is never sent as null: the twin may drop `null`.
      if (optional && !ts.includes('null')) expected = expected.replace(/ \| null|null \| /g, '');
      expect(union(ts), `${name}.${field}: ${annotation}`).toBe(union(expected));
    }
  });

  it('types the theme mode and the language as the server lists them', () => {
    expect(/^ThemeMode = Literal\[([^\]]+)\]/m.exec(PYTHON)?.[1]).toBe('"system", "light", "dark"');
    expect(/^export type AccountThemeMode = (.+);$/m.exec(TYPES)?.[1]).toBe("'system' | 'light' | 'dark'");
    // `settings.LANGUAGES`: English, the source, and Spanish.
    expect(/^export type AccountLanguage = (.+);$/m.exec(TYPES)?.[1]).toBe("'en' | 'es'");
  });

  it('declares every operation of the Account page for the SDK', () => {
    for (const op of [
      'accounts.profile.get',
      'accounts.profile.update',
      'accounts.profile.delete',
      'accounts.email.change',
      'accounts.email.verify',
      'accounts.photo.upload',
      'accounts.photo.remove',
      'accounts.preferences.get',
      'accounts.preferences.update',
      'accounts.session.list',
      'accounts.session.close',
      'accounts.session.close_others',
      'accounts.apikey.list',
      'accounts.apikey.create',
      'accounts.apikey.revoke',
    ]) {
      expect(TYPES, op).toContain(`'${op}': {`);
    }
  });
});
