// «Export your data» of Account → Profile (ACCOUNTS-F26; GDPR art. 20; GitHub's «Export account data» sits above its
// «Delete account» the same way): «Download my data» reads `accounts.data.export` and saves it as a JSON file
// built here, named with the day. While it runs the button is off; a failure is said and the button comes back.
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastError: vi.fn(() => Promise.resolve()),
}));

import { toastError } from '@erplora/ui/shell';

import { apiError, flush, ionProps, mountPanel } from '../__tests__/mount-panel';
import accountsEn from '../locale/en.json';
import accountsEs from '../locale/es.json';
import DataExportCard from './DataExportCard.vue';

const EXPORTED = { format: 'erplora.account-export', version: 1, account: { email: 'laura@example.com' } };

afterEach(() => {
  vi.mocked(toastError).mockClear();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.useRealTimers();
  document.body.innerHTML = '';
});

/** Catches the file the card saves: the link it clicks and the blob behind it. */
function catchDownloads() {
  const blobs: Blob[] = [];
  const createObjectURL = vi.fn((blob: Blob) => {
    blobs.push(blob);
    return 'blob:account-export';
  });
  vi.stubGlobal('URL', Object.assign(class extends URL {}, { createObjectURL, revokeObjectURL: vi.fn() }));
  const clicked: HTMLAnchorElement[] = [];
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    clicked.push(this);
  });
  return { blobs, clicked };
}

describe('DataExportCard', () => {
  it('says what the file holds, with «Download my data»', async () => {
    const s = await mountPanel(DataExportCard);
    expect(s.q('profile-export-card')?.textContent).toContain('Export your data');
    expect(s.q('profile-export-card')?.textContent).toContain(
      'A copy of your account, your businesses and your ERPlora invoices, in a file other apps can read.',
    );
    expect(s.q('profile-export')?.textContent?.trim()).toBe('Download my data');
  });

  it('never repeats the heading of «Your details» above it, in any language', () => {
    for (const { accounts } of [accountsEn, accountsEs]) {
      expect(accounts.account.export.title).not.toBe(accounts.account.profile.heading);
    }
  });

  it('says it in Spanish', async () => {
    const s = await mountPanel(DataExportCard, { locale: 'es' });
    expect(s.q('profile-export-card')?.textContent).toContain('Exportar tus datos');
    expect(s.q('profile-export-card')?.textContent).toContain(
      'Una copia de tu cuenta, tus negocios y tus facturas de ERPlora, en un fichero que otras aplicaciones pueden leer.',
    );
    expect(s.q('profile-export')?.textContent?.trim()).toBe('Descargar mis datos');
  });

  it('downloads the account as erplora-data-<day>.json, read from accounts.data.export', async () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-10-21T10:00:00Z'));
    const s = await mountPanel(DataExportCard, { api: () => Response.json(EXPORTED) });
    const { blobs, clicked } = catchDownloads();

    s.q('profile-export')?.click();
    await flush();

    expect(s.calls()).toEqual([{ method: 'GET', path: '/api/accounts/export', body: undefined }]);
    expect(clicked).toHaveLength(1);
    expect([clicked[0].download, clicked[0].getAttribute('href')]).toEqual(['erplora-data-2026-10-21.json', 'blob:account-export']);
    expect(blobs[0].type).toBe('application/json');
    expect(JSON.parse(await blobs[0].text())).toEqual(EXPORTED);
    expect(toastError).not.toHaveBeenCalled();
  });

  it('keeps the button off while the file is read', async () => {
    let answer: (response: Response) => void = () => undefined;
    const s = await mountPanel(DataExportCard, { api: () => new Promise<Response>((resolve) => (answer = resolve)) });
    catchDownloads();

    s.q('profile-export')?.click();
    await flush();
    expect(ionProps(s.q('profile-export'), 'disabled')).toEqual({ disabled: true });

    answer(Response.json(EXPORTED));
    await flush();
    expect(ionProps(s.q('profile-export'), 'disabled')).toEqual({ disabled: false });
  });

  it('says a failure and lets the person try again, saving nothing', async () => {
    const s = await mountPanel(DataExportCard, { api: () => apiError(429, 'rate_limited', 'Too many requests.') });
    const { clicked } = catchDownloads();

    s.q('profile-export')?.click();
    await flush();

    expect(toastError).toHaveBeenCalledWith('Too many requests.');
    expect(clicked).toEqual([]);
    expect(ionProps(s.q('profile-export'), 'disabled')).toEqual({ disabled: false });
  });

  it('says a lost connection in its own words', async () => {
    const s = await mountPanel(DataExportCard, {
      api: () => {
        throw new TypeError('Failed to fetch');
      },
    });
    catchDownloads();

    s.q('profile-export')?.click();
    await flush();

    expect(toastError).toHaveBeenCalledWith('We could not reach ERPlora. Check your connection and try again.');
  });
});
