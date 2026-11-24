// flow: ACCOUNTS-F17 — whether this browser skips the authenticator app's code and until when, and «Stop trusting all
// browsers», as the two-factor settings read and change them.
// clock: data only — no code under test compares these dates with now.
import type { LiveClient } from '@erplora/ui/sdk';
import { describe, expect, it, vi } from 'vitest';

import { useBrowserTrust } from './browser-trust';

const UNTIL = '2026-11-04T10:00:00Z';

/** A client whose `api.call` answers each operation with the given function. */
function clientAnswering(answers: Record<string, () => Promise<unknown>>) {
  const call = vi.fn((op: string) => answers[op]?.() ?? new Promise(() => undefined));
  return { call, client: { api: { call } } as unknown as Pick<LiveClient, 'api'> };
}

describe('useBrowserTrust', () => {
  it('knows nothing before it reads', () => {
    const trust = useBrowserTrust(clientAnswering({}).client);
    expect([trust.trustedUntil.value, trust.trustUnknown.value, trust.trustRevoked.value]).toEqual([undefined, false, false]);
  });

  it('reads until when this browser is trusted', async () => {
    const { call, client } = clientAnswering({ 'accounts.browser_trust.get': () => Promise.resolve({ trusted_until: UNTIL }) });
    const trust = useBrowserTrust(client);
    await trust.loadTrust();
    expect(call).toHaveBeenCalledWith('accounts.browser_trust.get');
    expect([trust.trustedUntil.value, trust.trustUnknown.value]).toEqual([UNTIL, false]);
  });

  it('reads that this browser is not trusted', async () => {
    const trust = useBrowserTrust(clientAnswering({ 'accounts.browser_trust.get': () => Promise.resolve({ trusted_until: null }) }).client);
    await trust.loadTrust();
    expect([trust.trustedUntil.value, trust.trustUnknown.value]).toEqual([null, false]);
  });

  it('says it could not tell when the read fails, and forgets what it knew', async () => {
    const answers = [Promise.resolve({ trusted_until: UNTIL }), Promise.reject(new Error('offline'))];
    const trust = useBrowserTrust(clientAnswering({ 'accounts.browser_trust.get': () => answers.shift()! }).client);
    await trust.loadTrust();
    await trust.loadTrust();
    expect([trust.trustedUntil.value, trust.trustUnknown.value]).toEqual([undefined, true]);
  });

  it('a read that works again is no longer unknown', async () => {
    const answers = [Promise.reject(new Error('offline')), Promise.resolve({ trusted_until: null })];
    const trust = useBrowserTrust(clientAnswering({ 'accounts.browser_trust.get': () => answers.shift()! }).client);
    await trust.loadTrust();
    expect(trust.trustUnknown.value).toBe(true);
    await trust.loadTrust();
    expect([trust.trustedUntil.value, trust.trustUnknown.value]).toEqual([null, false]);
  });

  it('stopping the trust of every browser takes what the server answers and says it is done', async () => {
    const { call, client } = clientAnswering({
      'accounts.browser_trust.get': () => Promise.reject(new Error('offline')),
      'accounts.browser_trust.revoke': () => Promise.resolve({ trusted_until: null }),
    });
    const trust = useBrowserTrust(client);
    await trust.loadTrust();
    await trust.revokeTrust();
    expect(call).toHaveBeenCalledWith('accounts.browser_trust.revoke');
    expect([trust.trustedUntil.value, trust.trustUnknown.value, trust.trustRevoked.value]).toEqual([null, false, true]);
  });

  it('a revocation that fails is the caller’s to show, and changes nothing', async () => {
    const { client } = clientAnswering({
      'accounts.browser_trust.get': () => Promise.resolve({ trusted_until: UNTIL }),
      'accounts.browser_trust.revoke': () => Promise.reject(new Error('offline')),
    });
    const trust = useBrowserTrust(client);
    await trust.loadTrust();
    await expect(trust.revokeTrust()).rejects.toThrow('offline');
    expect([trust.trustedUntil.value, trust.trustUnknown.value, trust.trustRevoked.value]).toEqual([UNTIL, false, false]);
  });
});
