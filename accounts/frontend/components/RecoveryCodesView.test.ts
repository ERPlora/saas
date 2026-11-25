// The recovery codes of the two-factor settings (`mfa/recovery_codes/index.html`) on their own: what they paint from
// the codes the page hands them, the file they download as (built here, no server route) and what «Generate new codes»
// and «Back» ask the page. The texts in both languages are the page's tests' (TwoFactorSettingsPage.recovery-codes.test.ts).
import type { RecoveryCodes } from '@erplora/ui/sdk';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { mountTwoFactorPiece } from '../__tests__/two-factor-settings-page';
import RecoveryCodesView from './RecoveryCodesView.vue';

const CODES = ['a1b2-c3d4', 'e5f6-g7h8'];
const codes = (unusedCodes: string[], unusedCodeCount: number): RecoveryCodes => ({ unusedCodes, unusedCodeCount, totalCodeCount: 10 });

const mountCodes = (recovery: RecoveryCodes | null, busy = false) => mountTwoFactorPiece(RecoveryCodesView, { recovery, busy });
const parts = ['codes-list', 'codes-count', 'codes-none', 'codes-download', 'codes-generate', 'codes-back'];

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe('RecoveryCodesView', () => {
  it('paints, for the codes it is given, the list and the download only when they can be read', async () => {
    const shown = await mountCodes(codes(CODES, 2));
    expect(parts.filter(shown.has)).toEqual(['codes-list', 'codes-count', 'codes-download', 'codes-generate', 'codes-back']);
    expect(shown.text('codes-list').split('\n')).toEqual(CODES);
    const hidden = await mountCodes(codes([], 9));
    expect(parts.filter(hidden.has)).toEqual(['codes-count', 'codes-generate', 'codes-back']);
    expect(hidden.text('codes-count')).toBe('9 of 10 unused');
  });

  it('warns that none is left when it is given none, or nothing', async () => {
    for (const recovery of [codes([], 0), null]) {
      const { has } = await mountCodes(recovery);
      expect(parts.filter(has)).toEqual(['codes-none', 'codes-generate', 'codes-back']);
    }
  });

  it('downloads them as erplora-recovery-codes.txt, one per line, and lets the address go 40 seconds later', async () => {
    vi.useFakeTimers();
    const blobs: Blob[] = [];
    const createObjectURL = vi.fn((blob: Blob) => {
      blobs.push(blob);
      return 'blob:recovery-codes';
    });
    const revokeObjectURL = vi.fn();
    vi.stubGlobal('URL', Object.assign(class extends URL {}, { createObjectURL, revokeObjectURL }));
    const clicked: HTMLAnchorElement[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      clicked.push(this);
    });
    const { button } = await mountCodes(codes(CODES, 2));
    await button('codes-download')!.trigger('click');
    expect(clicked.map((link) => [link.download, link.getAttribute('href'), link.isConnected])).toEqual([
      ['erplora-recovery-codes.txt', 'blob:recovery-codes', false],
    ]);
    expect([blobs[0].type, await blobs[0].text()]).toEqual(['text/plain', 'a1b2-c3d4\ne5f6-g7h8\n']);
    vi.advanceTimersByTime(39_999);
    expect(revokeObjectURL).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(revokeObjectURL).toHaveBeenCalledExactlyOnceWith('blob:recovery-codes');
  });

  it('«Generate new codes» and «Back» ask the page and wait while it is busy; «Download» does not wait', async () => {
    const { wrapper, button } = await mountCodes(codes(CODES, 2));
    await button('codes-generate')!.trigger('click');
    await button('codes-back')!.trigger('click');
    expect([wrapper.emitted('regenerate'), wrapper.emitted('back')]).toEqual([[[]], [[]]]);
    const busy = await mountCodes(codes(CODES, 2), true);
    expect(['codes-generate', 'codes-back'].map((testid) => busy.button(testid)!.props('disabled'))).toEqual([true, true]);
    expect(busy.button('codes-download')!.props('disabled')).not.toBe(true);
  });
});
