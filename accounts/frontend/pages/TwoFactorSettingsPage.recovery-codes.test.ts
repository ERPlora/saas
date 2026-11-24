// The recovery codes of the two-factor settings: reading and downloading them (`mfa/recovery_codes/index.html`)
// and generating a new set (`mfa/recovery_codes/generate.html`).
import { ionIconSrc } from '@erplora/ui/shell';
import { IonIcon } from '@ionic/vue';
import { flushPromises } from '@vue/test-utils';
import { describe, expect, it, vi } from 'vitest';

import { type Answer, fakeAllauth, held, offline, reauthenticationRequired, rejected } from '../__tests__/allauth-server';
import { CODES, codes, list, mountPage, recovery, setUpTwoFactorSettingsPage, TOTP } from '../__tests__/two-factor-settings-page';

setUpTwoFactorSettingsPage();

describe('TwoFactorSettingsPage: the recovery codes (mfa/recovery_codes/index.html)', () => {
  async function openCodes(answer: Answer, more: Record<string, Answer | Answer[]> = {}) {
    const server = fakeAllauth({
      'GET /account/authenticators': list(TOTP, recovery(9)),
      'GET /account/authenticators/recovery-codes': answer,
      ...more,
    });
    const page = await mountPage();
    await page.click('recovery-view');
    return { ...page, server };
  }

  it('lists the unused codes one per line, how many are left, «Download» and «Generate new codes»', async () => {
    const { wrapper, text, button } = await openCodes(codes(CODES, 3, 10));
    expect(wrapper.get('.auth-mark').findComponent(IonIcon).props('icon')).toBe(ionIconSrc('lucide:key-round'));
    expect(wrapper.get('h2.auth-title').text()).toBe('Recovery codes');
    expect(text('codes-lead')).toBe('Each code signs you in once if you lose your authenticator. Keep them somewhere safe.');
    const pre = wrapper.get('pre[data-testid="codes-list"]');
    expect([pre.text(), pre.classes()]).toEqual([CODES.join('\n'), ['recovery-codes']]);
    expect(text('codes-count')).toBe('3 of 10 unused');
    expect([button('codes-download')!.props('fill'), button('codes-download')!.text()]).toEqual(['outline', 'Download']);
    expect([button('codes-generate')!.props('fill'), button('codes-generate')!.text()]).toEqual(['outline', 'Generate new codes']);
    expect(button('codes-back')!.text()).toBe('Back');
    expect(document.title).toBe('Recovery codes - ERPlora Cloud');
  });

  it('counts the codes allauth hides, without listing nor downloading them', async () => {
    const { has, text } = await openCodes(codes([], 9, 10));
    expect(has('codes-list')).toBe(false);
    expect(text('codes-count')).toBe('9 of 10 unused');
    expect(has('codes-download')).toBe(false);
  });

  it('warns when none is left, with nothing to download', async () => {
    const { has, text } = await openCodes(codes([], 0, 10));
    expect(text('codes-none')).toBe('You have no codes left. Generate a new set now, before you need one.');
    expect(has('codes-count')).toBe(false);
    expect(has('codes-download')).toBe(false);
    expect(has('codes-generate')).toBe(true);
  });

  it('downloads them as erplora-recovery-codes.txt, one per line, built here (no server route)', async () => {
    const page = await openCodes(codes(CODES, 3, 10));
    const blobs: Blob[] = [];
    const createObjectURL = vi.fn((blob: Blob) => {
      blobs.push(blob);
      return 'blob:recovery-codes';
    });
    vi.stubGlobal('URL', Object.assign(class extends URL {}, { createObjectURL, revokeObjectURL: vi.fn() }));
    const clicked: HTMLAnchorElement[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      clicked.push(this);
    });
    await page.click('codes-download');
    expect(clicked).toHaveLength(1);
    expect([clicked[0].download, clicked[0].getAttribute('href')]).toEqual(['erplora-recovery-codes.txt', 'blob:recovery-codes']);
    expect(blobs[0].type).toBe('text/plain');
    expect(await blobs[0].text()).toBe(`${CODES.join('\n')}\n`);
    expect(page.server.calls.filter((c) => c.path.includes('download'))).toEqual([]);
  });

  it('goes to confirm it is you when reading them needs a recent login', async () => {
    const { router } = await openCodes(reauthenticationRequired());
    expect(router.currentRoute.value.path).toBe('/reauthenticate');
    expect(router.currentRoute.value.query).toMatchObject({ next: '/2fa', method: 'totp' });
  });

  it('«Back» shows the settings again, read anew', async () => {
    const page = await openCodes(codes(CODES, 3, 10));
    await page.click('codes-back');
    expect(page.server.callsTo('GET /account/authenticators')).toHaveLength(2);
    expect(page.has('recovery-section')).toBe(true);
  });

  it('holds «Generate new codes» while «Back» reads the settings again', async () => {
    const again = held(list(TOTP, recovery(9)));
    const page = await openCodes(codes(CODES, 3, 10), { 'GET /account/authenticators': [list(TOTP, recovery(9)), again.answer] });
    expect(page.button('codes-generate')!.props('disabled')).toBe(false);
    await page.click('codes-back');
    expect(page.button('codes-generate')!.props('disabled')).toBe(true);
    again.release();
    await flushPromises();
    expect(page.has('recovery-section')).toBe(true);
  });

  it('speaks Spanish', async () => {
    fakeAllauth({
      'GET /account/authenticators': list(TOTP, recovery(9)),
      'GET /account/authenticators/recovery-codes': codes(CODES, 3, 10),
    });
    const page = await mountPage('es');
    await page.click('recovery-view');
    expect(page.text('codes-count')).toBe('3 de 10 sin usar');
    expect(page.button('codes-download')!.text()).toBe('Descargar');
  });
});

describe('TwoFactorSettingsPage: new recovery codes (mfa/recovery_codes/generate.html)', () => {
  async function openRegenerate(unused: number, more: Record<string, Answer | Answer[]> = {}) {
    const server = fakeAllauth({ 'GET /account/authenticators': list(TOTP, recovery(unused)), ...more });
    const page = await mountPage();
    await page.click(unused ? 'recovery-generate-new' : 'recovery-generate');
    return { ...page, server };
  }

  it('says how many unused codes it throws away, in its plural', async () => {
    const several = await openRegenerate(9);
    expect(several.wrapper.get('.auth-mark').findComponent(IonIcon).props('icon')).toBe(ionIconSrc('lucide:refresh-cw'));
    expect(several.wrapper.get('h2.auth-title').text()).toBe('Generate new recovery codes?');
    expect(several.text('regenerate-lead')).toBe('This replaces your 9 unused codes.');
    const submit = several.button('regenerate-submit')!;
    expect([submit.props('color'), submit.props('size'), submit.text()]).toEqual(['primary', 'large', 'Generate']);
    expect([several.button('regenerate-cancel')!.props('fill'), several.button('regenerate-cancel')!.text()]).toEqual(['clear', 'Cancel']);
    expect((await openRegenerate(1)).text('regenerate-lead')).toBe('This replaces your 1 unused code.');
  });

  it('says nothing is thrown away when none is left', async () => {
    const { text } = await openRegenerate(0);
    expect(text('regenerate-lead')).toBe('You have no unused codes left, so nothing is thrown away.');
  });

  it('generates them and shows the new set', async () => {
    const fresh = ['n1n1-n1n1', 'n2n2-n2n2'];
    const page = await openRegenerate(9, { 'POST /account/authenticators/recovery-codes': codes(fresh, 2, 2) });
    await page.click('regenerate-submit');
    expect(page.server.callsTo('POST /account/authenticators/recovery-codes')).toHaveLength(1);
    expect(page.text('codes-list')).toBe(fresh.join('\n'));
    expect(page.text('codes-count')).toBe('2 of 2 unused');
  });

  it('goes to confirm it is you when generating needs a recent login', async () => {
    const page = await openRegenerate(9, { 'POST /account/authenticators/recovery-codes': reauthenticationRequired(['mfa_reauthenticate']) });
    await page.click('regenerate-submit');
    expect(page.router.currentRoute.value.path).toBe('/reauthenticate');
    expect(page.router.currentRoute.value.query).toEqual({ next: '/2fa', method: 'totp', flows: 'mfa_reauthenticate' });
  });

  it('says why allauth will not generate them, and stays', async () => {
    const page = await openRegenerate(9, {
      'POST /account/authenticators/recovery-codes': rejected('You cannot generate recovery codes.', undefined, 'cannot_generate_recovery_codes'),
    });
    await page.click('regenerate-submit');
    expect(page.text('failure')).toBe('You cannot generate recovery codes.');
    expect(page.has('regenerate-view')).toBe(true);
  });

  it('says something went wrong when the server is out of reach, in the language of the page', async () => {
    fakeAllauth({ 'GET /account/authenticators': list(TOTP, recovery(9)), 'POST /account/authenticators/recovery-codes': offline });
    const page = await mountPage('es');
    await page.click('recovery-generate-new');
    await page.click('regenerate-submit');
    expect(page.text('failure')).toBe('Algo ha ido mal. Inténtalo de nuevo.');
  });

  it('«Cancel» goes back to where it came from: the settings, or the codes', async () => {
    const fromIndex = await openRegenerate(9);
    await fromIndex.click('regenerate-cancel');
    expect(fromIndex.has('recovery-section')).toBe(true);

    fakeAllauth({
      'GET /account/authenticators': list(TOTP, recovery(3)),
      'GET /account/authenticators/recovery-codes': codes(CODES, 3, 10),
    });
    const fromCodes = await mountPage();
    await fromCodes.click('recovery-view');
    await fromCodes.click('codes-generate');
    expect(fromCodes.text('regenerate-lead')).toBe('This replaces your 3 unused codes.');
    await fromCodes.click('regenerate-cancel');
    expect(fromCodes.text('codes-list')).toBe(CODES.join('\n'));
  });
});
