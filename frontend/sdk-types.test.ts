// `sdk-types.d.ts` is written by hand from the schemas of the API (until it is generated from
// `/api/openapi.json`): this guard reads both and fails when a field of a hubs schema the panel uses is
// missing from its TypeScript twin, the twin carries one the server no longer sends, or a field's type
// differs (pydantic's annotation translated to what its JSON is in TypeScript).
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const HERE = dirname(fileURLToPath(import.meta.url));
const PYTHON = readFileSync(join(HERE, '..', 'hubs', 'schemas.py'), 'utf8');
const TYPES = readFileSync(join(HERE, 'sdk-types.d.ts'), 'utf8');

const PAGE = ['rows', 'total', 'limit', 'offset'];
const PAGE_IN = ['limit', 'offset'];

/** The fields of a pydantic schema of hubs/schemas.py, with what its base class adds. */
function pythonFields(name: string): string[] {
  const match = new RegExp(`^class ${name}\\(([^)]*)\\):\\n((?:(?:    .*)?\\n)*)`, 'm').exec(PYTHON);
  if (!match) throw new Error(`hubs/schemas.py has no class ${name}`);
  const [, base, body] = match;
  const own = [...body.matchAll(/^ {4}(\w+): /gm)].map((m) => m[1]);
  const inherited = base.startsWith('Page[') ? PAGE : base === 'PageIn' ? PAGE_IN : [];
  return [...inherited, ...own].sort();
}

/** The fields of an interface of sdk-types.d.ts, with what `extends Page<…>`/`PageIn` adds. */
function typeFields(name: string): string[] {
  const match = new RegExp(`^export interface ${name}(?: extends ([\\w<>]+))? \\{\\n([\\s\\S]*?)^\\}`, 'm').exec(TYPES);
  if (!match) throw new Error(`sdk-types.d.ts has no interface ${name}`);
  const [, base = '', body] = match;
  const own = [...body.matchAll(/^ {2}(\w+)\??: /gm)].map((m) => m[1]);
  const inherited = base.startsWith('Page<') ? PAGE : base === 'PageIn' ? PAGE_IN : [];
  return [...inherited, ...own].sort();
}

/** `name: annotation` of a pydantic schema (a multi-line `Field(...)` default is cut at `=`). */
function pythonTypes(name: string): Record<string, string> {
  const match = new RegExp(`^class ${name}\\(([^)]*)\\):\\n((?:(?:    .*)?\\n)*)`, 'm').exec(PYTHON);
  if (!match) throw new Error(`hubs/schemas.py has no class ${name}`);
  const own = [...match[2].matchAll(/^ {4}(\w+): (.+?)(?: = .*)?$/gm)].map((m) => [m[1], m[2].trim()] as const);
  return Object.fromEntries(own);
}

/** `name: type` of an interface, with `?` kept on the name's side (`name?`). */
function typeTypes(name: string): Record<string, string> {
  const match = new RegExp(`^export interface ${name}(?: extends [\\w<>]+)? \\{\\n([\\s\\S]*?)^\\}`, 'm').exec(TYPES);
  if (!match) throw new Error(`sdk-types.d.ts has no interface ${name}`);
  return Object.fromEntries([...match[1].matchAll(/^ {2}(\w+\??): (.+);$/gm)].map((m) => [m[1], m[2].trim()]));
}

/** What a pydantic annotation is once JSON reaches TypeScript. */
const SCALARS: Record<string, string> = {
  UUID: 'string',
  str: 'string',
  datetime: 'string',
  Decimal: 'string',
  int: 'number',
  bool: 'boolean',
  // The constrained strings of hubs/schemas.py.
  Name: 'string',
  Country: 'string',
  Email: 'string',
  LocalPath: 'string',
  TimeZone: 'string',
  // Same values, the TypeScript name.
  Role: 'HubRole',
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

const union = (type: string) => type.split('|').map((part) => part.trim()).sort().join(' | ');

/**
 * Fields TypeScript types narrower than the server on purpose: the server sends a plain `str` that
 * only ever holds these values (`Hub.Status`, `open_blocked_reason`).
 */
const NARROWED: Record<string, string> = {
  'BusinessRowOut.status': 'BusinessStatusCode',
  'BusinessRowOut.open_blocked_reason': 'OpenBlockedReason | null',
  'BusinessDetailOut.status': 'BusinessStatusCode',
};

/** Every schema of hubs the panel reads or sends, by its name on both sides. */
const SCHEMAS = [
  'HubRefOut',
  'PlanRefOut',
  'BusinessTypeOut',
  'PlanOut',
  'BusinessListIn',
  'BusinessRowOut',
  'InvitationOut',
  'OwnershipOfferOut',
  'BusinessListOut',
  'SeatsOut',
  'TransferRefOut',
  'BusinessRowCanOut',
  'BusinessCanOut',
  'BusinessDetailOut',
  'AddressProposeOut',
  'BusinessCreateIn',
  'BusinessUpdateIn',
  'BusinessDeleteIn',
  'BusinessOpenIn',
  'BusinessOpenOut',
  'MemberListIn',
  'MemberRowOut',
  'MemberListOut',
  'MemberInviteIn',
  'MemberRoleIn',
  'OwnershipTransferIn',
  'OwnershipTransferOut',
];

describe('sdk-types.d.ts follows hubs/schemas.py', () => {
  it.each(SCHEMAS)('%s has the same fields on both sides', (name) => {
    expect(typeFields(name)).toEqual(pythonFields(name));
  });

  it.each(SCHEMAS)('%s types each field as its JSON is', (name) => {
    const python = pythonTypes(name);
    const types = typeTypes(name);
    for (const [field, annotation] of Object.entries(python)) {
      const optional = `${field}?` in types;
      const ts = types[optional ? `${field}?` : field];
      let expected = NARROWED[`${name}.${field}`] ?? toTypeScript(annotation);
      // An input the SPA leaves out (`field?`) is never sent as null: the twin may drop `null`.
      if (optional && !ts.includes('null')) expected = expected.replace(/ \| null|null \| /g, '');
      expect(union(ts), `${name}.${field}: ${annotation}`).toBe(union(expected));
    }
  });

  it('types the actions of a member row as the server names them, in its order', () => {
    expect(/^MemberAction = Literal\[([^\]]+)\]/m.exec(PYTHON)?.[1]).toBe('"change_role", "remove", "resend", "cancel", "transfer"');
    expect(/^export type MemberAction = (.+);$/m.exec(TYPES)?.[1]).toBe("'change_role' | 'remove' | 'resend' | 'cancel' | 'transfer'");
  });
});
