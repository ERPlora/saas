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

/** The fields of a pydantic schema of hubs/schemas.py (or `source`), with what its base class adds. */
function pythonFields(name: string, source = PYTHON): string[] {
  const match = new RegExp(`^class ${name}\\(([^)]*)\\):\\n((?:(?:    .*)?\\n)*)`, 'm').exec(source);
  if (!match) throw new Error(`the schemas have no class ${name}`);
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
function pythonTypes(name: string, source = PYTHON): Record<string, string> {
  const match = new RegExp(`^class ${name}\\(([^)]*)\\):\\n((?:(?:    .*)?\\n)*)`, 'm').exec(source);
  if (!match) throw new Error(`the schemas have no class ${name}`);
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
  // billing/schemas.py and apps/schemas.py (the Store, L2-D).
  Interval: 'BillingInterval',
  ModuleSlug: 'string',
  Category: 'string',
  // hubs/schemas.py `BillingProfileIn.billing_postal_code`: a stripped string.
  'Annotated[str, StringConstraints(strip_whitespace=True)]': 'string',
  // billing/schemas.py, the Billing section (L3-C): a day travels as `YYYY-MM-DD`; the literal aliases keep
  // their name in TypeScript.
  date: 'string',
  InvoicePaymentStatus: 'InvoicePaymentStatus',
  InvoiceFiscalStatus: 'InvoiceFiscalStatus',
  InvoiceRectificationType: 'InvoiceRectificationType',
  VatStatus: 'VatStatus',
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
  // `Country | Literal[""]`, `Email | Literal[""]`: the empty string is a string.
  'BillingProfileIn.billing_country': 'string',
  'BillingProfileIn.billing_email': 'string',
  // `CountryCode | Literal[""]` (billing/schemas.py `VatCheckIn.country`): a string.
  'VatCheckIn.country': 'string',
  // `list[Literal[…]]` of the row's actions: named in TypeScript (checked below against the literal).
  'InvoiceRowOut.actions': 'InvoiceAction[]',
  'SubscriptionRowOut.actions': 'SubscriptionAction[]',
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

/** The Store's schemas (L2-D), by their file: the same guard as hubs'. */
const STORE_SCHEMAS: Array<[file: string, names: string[]]> = [
  ['hubs/schemas.py', ['BillingProfileGetIn', 'BillingProfileIn', 'BillingProfileOut']],
  [
    'billing/schemas.py',
    [
      'PromoCheckIn',
      'PromoCheckOut',
      'CheckoutStartIn',
      'ChargePreviewOut',
      'CheckoutStartOut',
      'CheckoutConfirmIn',
      'PlanChangeIn',
      'HubIn',
      'ModuleIn',
      'SubscriptionModuleOut',
      'SubscriptionOut',
      'StoreCatalogIn',
      'StoreModuleOut',
      'StoreSubscriptionOut',
      'StoreCatalogOut',
    ],
  ],
  ['apps/schemas.py', ['AppListIn', 'AppSummaryOut', 'AppListOut', 'AppByIdIn', 'RequiredAppOut', 'AppOut']],
];
const STORE_CASES = STORE_SCHEMAS.flatMap(([file, names]) => names.map((name) => [file, name] as const));

describe('sdk-types.d.ts follows billing/schemas.py, apps/schemas.py and the payer of hubs (the Store)', () => {
  const sources = new Map(STORE_SCHEMAS.map(([file]) => [file, readFileSync(join(HERE, '..', file), 'utf8')]));

  it.each(STORE_CASES)('%s %s has the same fields on both sides', (file, name) => {
    expect(typeFields(name)).toEqual(pythonFields(name, sources.get(file)));
  });

  it.each(STORE_CASES)('%s %s types each field as its JSON is', (file, name) => {
    const python = pythonTypes(name, sources.get(file));
    const types = typeTypes(name);
    for (const [field, annotation] of Object.entries(python)) {
      const optional = `${field}?` in types;
      const ts = types[optional ? `${field}?` : field];
      let expected = NARROWED[`${name}.${field}`] ?? toTypeScript(annotation);
      if (optional && !ts.includes('null')) expected = expected.replace(/ \| null|null \| /g, '');
      expect(union(ts), `${file} ${name}.${field}: ${annotation}`).toBe(union(expected));
    }
  });

  it('types the billing of a subscription as the server names it', () => {
    expect(/^Interval = Literal\[([^\]]+)\]/m.exec(sources.get('billing/schemas.py') ?? '')?.[1]).toBe('"month", "year"');
    expect(/^export type BillingInterval = (.+);$/m.exec(TYPES)?.[1]).toBe("'month' | 'year'");
  });
});

/** The Billing section's schemas (L3-C front: invoices, subscriptions, payment details), by their file. */
const BILLING_SCHEMAS: Array<[file: string, names: string[]]> = [
  [
    'billing/schemas.py',
    [
      'InvoiceFilterIn',
      'InvoiceListIn',
      'InvoiceBusinessOut',
      'InvoiceCanOut',
      'InvoiceRectificationOut',
      'InvoiceRowOut',
      'InvoiceListOut',
      'InvoiceByIdIn',
      'InvoiceLineOut',
      'InvoiceRecipientOut',
      'InvoiceRefOut',
      'InvoiceDetailOut',
      'InvoicePayIn',
      'InvoicePayOut',
      'SubscriptionListIn',
      'SubscriptionPlanOut',
      'SubscriptionModuleRowOut',
      'NextInvoiceOut',
      'SubscriptionCanOut',
      'SubscriptionRowOut',
      'SubscriptionListOut',
      'PaymentMethodIn',
      'CardOut',
      'LastFailureOut',
      'PaymentMethodRowOut',
      'PaymentMethodOut',
      'PortalOpenIn',
      'PortalOpenOut',
      'VatCheckIn',
      'VatCheckOut',
      'ScheduledChangeOut',
    ],
  ],
];
const BILLING_CASES = BILLING_SCHEMAS.flatMap(([file, names]) => names.map((name) => [file, name] as const));

describe('sdk-types.d.ts follows billing/schemas.py (the Billing section)', () => {
  const sources = new Map(BILLING_SCHEMAS.map(([file]) => [file, readFileSync(join(HERE, '..', file), 'utf8')]));

  it.each(BILLING_CASES)('%s %s has the same fields on both sides', (file, name) => {
    expect(typeFields(name)).toEqual(pythonFields(name, sources.get(file)));
  });

  it.each(BILLING_CASES)('%s %s types each field as its JSON is', (file, name) => {
    const python = pythonTypes(name, sources.get(file));
    const types = typeTypes(name);
    for (const [field, annotation] of Object.entries(python)) {
      const optional = `${field}?` in types;
      const ts = types[optional ? `${field}?` : field];
      let expected = NARROWED[`${name}.${field}`] ?? toTypeScript(annotation);
      if (optional && !ts.includes('null')) expected = expected.replace(/ \| null|null \| /g, '');
      expect(union(ts), `${file} ${name}.${field}: ${annotation}`).toBe(union(expected));
    }
  });

  it.each([
    ['InvoicePaymentStatus', '"open", "paid", "void"', "'open' | 'paid' | 'void'"],
    [
      'InvoiceFiscalStatus',
      '"", "issuing", "issued", "accepted", "accepted_with_errors", "rejected"',
      "'' | 'issuing' | 'issued' | 'accepted' | 'accepted_with_errors' | 'rejected'",
    ],
    ['VatStatus', '"verified", "invalid", "unavailable", "national", "outside_vies"', "'verified' | 'invalid' | 'unavailable' | 'national' | 'outside_vies'"],
    ['InvoiceRectificationType', '"R1", "R2", "R3", "R4"', "'R1' | 'R2' | 'R3' | 'R4'"],
  ])('types %s as the server names its values', (alias, python, typescript) => {
    const source = sources.get('billing/schemas.py') ?? '';
    expect(new RegExp(`^${alias} = Literal\\[([^\\]]+)\\]`, 'm').exec(source)?.[1]).toBe(python);
    expect(new RegExp(`^export type ${alias} = (.+);$`, 'm').exec(TYPES)?.[1]).toBe(typescript);
  });

  it.each([
    ['InvoiceRowOut', 'InvoiceAction', '"pay", "pdf"', "'pay' | 'pdf'"],
    [
      'SubscriptionRowOut',
      'SubscriptionAction',
      '"take_over", "change_plan", "keep_plan", "view_invoice", "cancel_plan", "view_invoices"',
      "'take_over' | 'change_plan' | 'keep_plan' | 'view_invoice' | 'cancel_plan' | 'view_invoices'",
    ],
  ])('types the actions of a %s row (%s) as the server names them, in its order', (schema, alias, python, typescript) => {
    const annotation = pythonTypes(schema, sources.get('billing/schemas.py')).actions;
    expect(annotation).toBe(`list[Literal[${python}]]`);
    expect(new RegExp(`^export type ${alias} = (.+);$`, 'm').exec(TYPES)?.[1]).toBe(typescript);
  });
});

/** The usage of a business (lot L4-A): `hubs.usage.get`, `hubs.usage.series` and `usage` of the business's page. */
const USAGE_SCHEMAS = ['StorageUsageOut', 'ActiveUsersOut', 'UsageOut', 'UsageGetIn', 'UsageSeriesIn', 'UsagePointOut', 'UsageSeriesOut'];

describe('sdk-types.d.ts follows the usage schemas of hubs/schemas.py', () => {
  it.each(USAGE_SCHEMAS)('%s has the same fields on both sides', (name) => {
    expect(typeFields(name)).toEqual(pythonFields(name));
  });

  it.each(USAGE_SCHEMAS)('%s types each field as its JSON is', (name) => {
    const python = pythonTypes(name);
    const types = typeTypes(name);
    for (const [field, annotation] of Object.entries(python)) {
      const optional = `${field}?` in types;
      const ts = types[optional ? `${field}?` : field];
      let expected = NARROWED[`${name}.${field}`] ?? toTypeScript(annotation);
      if (optional && !ts.includes('null')) expected = expected.replace(/ \| null|null \| /g, '');
      expect(union(ts), `${name}.${field}: ${annotation}`).toBe(union(expected));
    }
  });

  it('the page of a business carries the last day measured, or null', () => {
    expect(typeTypes('BusinessDetailOut').usage).toBe('UsageOut | null');
  });
});

/** The signed authorisation of a business (plan 2026-10-15): `fiscal.representation.status`, its card on the business's page. */
const FISCAL_SCHEMAS = ['RepresentationStatusIn', 'RepresentationDocumentsOut', 'RepresentationHistoryOut', 'RepresentationStatusOut'];

describe('sdk-types.d.ts follows the schemas of fiscal/schemas.py', () => {
  const source = readFileSync(join(HERE, '..', 'fiscal', 'schemas.py'), 'utf8');

  it.each(FISCAL_SCHEMAS)('%s has the same fields on both sides', (name) => {
    expect(typeFields(name)).toEqual(pythonFields(name, source));
  });

  it.each(FISCAL_SCHEMAS)('%s types each field as its JSON is', (name) => {
    const python = pythonTypes(name, source);
    const types = typeTypes(name);
    for (const [field, annotation] of Object.entries(python)) {
      expect(union(types[field]), `${name}.${field}: ${annotation}`).toBe(union(toTypeScript(annotation)));
    }
  });

  it('names the states of an authorisation as the server does, «none» included', () => {
    const python = /^RepresentationState = (Literal\[[^\]]+\])/m.exec(source)?.[1] ?? '';
    expect(python).toBe('Literal["none", "submitted", "approved", "returned", "revoked"]');
    expect(/^export type RepresentationState = (.+);$/m.exec(TYPES)?.[1]).toBe(toTypeScript(python));
  });

  it('types the operation of the card with its input and output', () => {
    expect(TYPES).toContain(
      "'fiscal.representation.status': { input: RepresentationStatusIn; output: RepresentationStatusOut };",
    );
  });
});

describe("sdk-types.d.ts follows the panel's assistant schemas of base/schemas.py", () => {
  const source = readFileSync(join(HERE, '..', 'base', 'schemas.py'), 'utf8');
  const ASSISTANT_SCHEMAS = ['AssistantUsageOut', 'AssistantReportIn', 'AssistantReportOut'];

  it.each(ASSISTANT_SCHEMAS)('%s has the same fields on both sides', (name) => {
    expect(typeFields(name)).toEqual(pythonFields(name, source));
  });

  it.each(ASSISTANT_SCHEMAS)('%s types each field as its JSON is', (name) => {
    const python = pythonTypes(name, source);
    const types = typeTypes(name);
    for (const [field, annotation] of Object.entries(python)) {
      const optional = `${field}?` in types;
      expect(union(types[optional ? `${field}?` : field]), `${name}.${field}: ${annotation}`).toBe(
        union(toTypeScript(annotation)),
      );
    }
  });

  it('types the allowance and the report with their input and output', () => {
    expect(TYPES).toContain("'base.assistant.usage': { input: AssistantUsageIn; output: AssistantUsageOut };");
    expect(TYPES).toContain("'base.assistant.report': { input: AssistantReportIn; output: AssistantReportOut };");
  });
});
