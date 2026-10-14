// «Change photo» on Account → Profile: a JPEG, PNG or WebP picked from the device, made small in the browser
// (`../photo.ts`) and sent as a data URL (`accounts.photo.upload`); «Remove photo» goes back to the initials
// (`accounts.photo.remove`). What cannot be the photo is said in a toast, in the person's language.
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastSuccess: vi.fn(() => Promise.resolve()),
  toastError: vi.fn(() => Promise.resolve()),
}));
vi.mock('../photo', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../photo')>()),
  preparePhoto: vi.fn(),
}));

import { toastError, toastSuccess } from '@erplora/ui/shell';

import { apiError, flush, mountPanel, profile } from '../__tests__/mount-panel';
import type { ProfileOut } from '../../../frontend/sdk-types';
import { PhotoError, preparePhoto } from '../photo';
import PhotoPicker from './PhotoPicker.vue';

const SMALL = 'data:image/jpeg;base64,QUJD';

afterEach(() => {
  vi.mocked(toastSuccess).mockClear();
  vi.mocked(toastError).mockClear();
  vi.mocked(preparePhoto).mockReset();
  document.body.innerHTML = '';
});

async function setup(me: ProfileOut = profile(), api: () => Response | Promise<Response> = () => Response.json(profile({ photo: SMALL }))) {
  const s = await mountPanel(PhotoPicker, { props: { profile: me }, api });
  await flush();
  return s;
}

/** Picks `file` in the hidden file input, as the system dialog does. */
async function pick(input: HTMLElement | null, file: File) {
  if (!input) throw new Error('no file input');
  Object.defineProperty(input, 'files', { value: [file], configurable: true });
  input.dispatchEvent(new Event('change'));
  await flush();
}

describe('PhotoPicker', () => {
  it('opens the device’s picker for the images the server takes', async () => {
    const s = await setup();
    const input = s.q('photo-input') as unknown as HTMLInputElement;
    expect(input.type).toBe('file');
    expect(input.accept).toBe('image/jpeg,image/png,image/webp');
    const click = vi.spyOn(input, 'click');
    s.q('photo-change')?.click();
    expect(click).toHaveBeenCalledTimes(1);
  });

  it('sends the photo made small, and says so', async () => {
    vi.mocked(preparePhoto).mockResolvedValue(SMALL);
    const s = await setup();
    const file = new File(['x'], 'me.png', { type: 'image/png' });
    await pick(s.q('photo-input'), file);
    expect(preparePhoto).toHaveBeenCalledWith(file);
    expect(s.calls().map((c) => [c.path, c.body])).toEqual([['/api/accounts/photo', { image: SMALL }]]);
    expect(toastSuccess).toHaveBeenCalledWith('Photo updated');
  });

  it('says why a file cannot be the photo, and sends nothing', async () => {
    vi.mocked(preparePhoto).mockRejectedValue(new PhotoError('unsupported'));
    const s = await setup();
    await pick(s.q('photo-input'), new File(['x'], 'a.gif', { type: 'image/gif' }));
    expect(toastError).toHaveBeenCalledWith('Choose a JPEG, PNG or WebP image.');
    expect(s.calls()).toEqual([]);
  });

  it('says the server’s refusal of the image', async () => {
    vi.mocked(preparePhoto).mockResolvedValue(SMALL);
    const s = await setup(profile(), () => apiError(422, 'invalid_payload', 'Invalid payload', { fields: { image: 'Upload a still image, not an animation.' } }));
    await pick(s.q('photo-input'), new File(['x'], 'a.webp', { type: 'image/webp' }));
    expect(toastError).toHaveBeenCalledWith('Upload a still image, not an animation.');
  });

  it('offers to remove a photo only when there is one, and goes back to the initials', async () => {
    expect((await setup()).q('photo-remove')).toBeNull();
    document.body.innerHTML = '';
    const s = await setup(profile({ photo: SMALL }), () => Response.json(profile()));
    s.q('photo-remove')?.click();
    await flush();
    expect(s.calls().map((c) => c.path)).toEqual(['/api/accounts/photo/remove']);
    expect(toastSuccess).toHaveBeenCalledWith('Photo removed');
  });
});
