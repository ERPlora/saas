// The panel's assistant's words (`saas.assistant.*` of the entry's catalogue, frontend/locale: the app `assistant`'s
// own catalogue would sit under `assistant`, the shared chat's namespace): the same keys in en and es, each said, and
// each translated. That every write the assistant may run has its verb is the server's guard
// (base/tests/test_assistant_panel_words.py: it reads the catalogue of a real account).
import { describe, expect, it } from 'vitest';

import en from '../../frontend/locale/en.json';
import es from '../../frontend/locale/es.json';

type Catalogue = { [key: string]: string | Catalogue };

function leaves(catalogue: Catalogue, prefix = ''): Array<[string, string]> {
  return Object.entries(catalogue).flatMap(([key, value]) =>
    typeof value === 'string' ? [[`${prefix}${key}`, value] as [string, string]] : leaves(value, `${prefix}${key}.`),
  );
}

const EN = Object.fromEntries(leaves(en.saas.assistant as unknown as Catalogue));
const ES = Object.fromEntries(leaves(es.saas.assistant as unknown as Catalogue));

describe("the panel's assistant's words", () => {
  it('have the same keys in en and es', () => {
    expect(Object.keys(ES).sort()).toEqual(Object.keys(EN).sort());
    expect(Object.keys(EN)).toEqual(
      expect.arrayContaining([
        'empty',
        'shortcuts.businesses',
        'shortcuts.billing',
        'shortcuts.create',
        'screens.businesses',
        'screens.store',
        'screens.billing',
        'screens.account',
        'errors.quotaSpentAccount',
        'card.operations.hubs.business.create',
      ]),
    );
  });

  it('say each one, translated', () => {
    for (const [key, text] of Object.entries(EN)) {
      expect(text.trim(), key).not.toBe('');
      expect(ES[key].trim(), key).not.toBe('');
      expect(ES[key], key).not.toBe(text);
    }
  });

  it('have no placeholder the components would leave unsaid', () => {
    expect(Object.entries({ ...EN, ...ES }).filter(([, text]) => /[{}]/.test(text))).toEqual([]);
  });
});
