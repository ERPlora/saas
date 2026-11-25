// What the Members of a business say of its plan and its end: ERPlora's own business, which has no plan and nobody
// deletes, says neither. One place for the pages and dialogs of Members (`memberTexts`).
import { describe, expect, it } from 'vitest';

import en from './locale/en.json';
import es from './locale/es.json';
import { memberTexts } from './member-texts';

const CUSTOMER = memberTexts({ is_platform: false });
const PLATFORM = memberTexts({ is_platform: true });

/** The sentence of a key (`hubs.members.rolesOwner`) in a catalogue. */
const sentence = (catalogue: unknown, key: string) =>
  key.split('.').reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], catalogue);
const everySentence = (texts: typeof CUSTOMER, catalogue: unknown) =>
  [...texts.roles, texts.freeRole, texts.transferBilling].filter((key) => key !== null).map((key) => sentence(catalogue, key!));

describe('memberTexts', () => {
  it('a customer’s business keeps its sentences', () => {
    expect(CUSTOMER).toEqual({
      roles: [
        'hubs.members.rolesOwner',
        'hubs.members.rolesAdmin',
        'hubs.members.rolesStaff',
        'hubs.members.rolesAccountant',
      ],
      freeRole: 'hubs.members.inviteModal.freeRole',
      transferBilling: 'hubs.members.transfer.consequenceBilling',
    });
  });

  it('ERPlora’s own business says the same of each role, without the plan', () => {
    expect(PLATFORM.roles).toHaveLength(CUSTOMER.roles.length);
    expect([PLATFORM.freeRole, PLATFORM.transferBilling]).toEqual([null, null]);
  });

  it.each([
    ['en', en, /plan|pay|paid|charge|card|delet/i],
    ['es', es, /plan|pag|cobra|tarjeta|elimin|borra/i],
  ] as const)('no sentence of ERPlora’s own business speaks of a plan, a payment or deleting it (%s)', (_, catalogue, forbidden) => {
    const sentences = everySentence(PLATFORM, catalogue);
    expect(sentences).toHaveLength(4);
    for (const text of sentences) {
      expect(text).toBeTypeOf('string');
      expect(text).not.toMatch(forbidden);
    }
    // The control: those of a customer's business do speak of them.
    expect(everySentence(CUSTOMER, catalogue).some((text) => forbidden.test(text as string))).toBe(true);
  });

  it('before the business answers, it is a customer’s', () => {
    expect(memberTexts(undefined)).toBe(CUSTOMER);
  });
});
