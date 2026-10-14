// The profile photo is made small in the browser before it travels (accounts/README.md, «Foto en la BD»: the server
// keeps at most 150 KB and has no image library): at most 512 px on its longer side, re-drawn on a canvas (only its
// first frame, so an animation arrives still and without its metadata), as a JPEG whose quality drops until it fits.
import { describe, expect, it, vi } from 'vitest';

import { dataUrlBytes, encodeWithin, fitWithin, MAX_PHOTO_BYTES, MAX_PHOTO_SIDE, PhotoError, preparePhoto, type PhotoCanvas } from './photo';

/** A data URL of `bytes` bytes once decoded (base64: 4 characters per 3 bytes). */
const urlOf = (bytes: number) => `data:image/jpeg;base64,${'A'.repeat(Math.ceil(bytes / 3) * 4)}`;

describe('fitWithin', () => {
  it('shrinks the longer side to 512 px keeping the shape, never enlarges', () => {
    expect(MAX_PHOTO_SIDE).toBe(512);
    expect(fitWithin(4032, 3024)).toEqual({ width: 512, height: 384 });
    expect(fitWithin(1000, 2000)).toEqual({ width: 256, height: 512 });
    expect(fitWithin(300, 200)).toEqual({ width: 300, height: 200 });
    expect(fitWithin(5000, 3)).toEqual({ width: 512, height: 1 });
  });
});

describe('dataUrlBytes', () => {
  it('counts the bytes of the payload, not the characters', () => {
    expect(dataUrlBytes(urlOf(300))).toBe(300);
    expect(dataUrlBytes('data:image/jpeg;base64,QUI=')).toBe(2);
    expect(dataUrlBytes('data:image/jpeg;base64,QUJD')).toBe(3);
  });
});

describe('encodeWithin', () => {
  it('keeps the first quality that fits the 150 KB the server takes', () => {
    expect(MAX_PHOTO_BYTES).toBe(150_000);
    const encode = vi.fn((quality: number) => urlOf(quality > 0.7 ? 200_000 : 120_000));
    expect(encodeWithin(encode)).toBe(urlOf(120_000));
    expect(encode.mock.calls.map(([q]) => q)).toEqual([0.9, 0.8, 0.7]);
  });

  it('gives up when not even the lowest quality fits', () => {
    expect(encodeWithin(() => urlOf(400_000))).toBeNull();
  });
});

describe('preparePhoto', () => {
  function fakeCanvas(bytes = 50_000) {
    const drawn: Array<{ width: number; height: number }> = [];
    const canvas = vi.fn(
      (width: number, height: number): PhotoCanvas => ({
        draw: () => drawn.push({ width, height }),
        encode: (type, quality) => (type === 'image/jpeg' && quality <= 0.9 ? urlOf(bytes) : 'data:,'),
      }),
    );
    return { canvas, drawn };
  }

  it('re-draws a JPEG, PNG or WebP at 512 px and hands back a JPEG data URL', async () => {
    const { canvas, drawn } = fakeCanvas();
    const file = new File(['x'], 'me.png', { type: 'image/png' });
    const url = await preparePhoto(file, { load: async () => ({ width: 2048, height: 1536, image: {} }), canvas });
    expect(url).toBe(urlOf(50_000));
    expect(drawn).toEqual([{ width: 512, height: 384 }]);
  });

  it('refuses another kind of file before reading it (a GIF moves; a PDF is no photo)', async () => {
    const load = vi.fn();
    for (const type of ['image/gif', 'application/pdf', '']) {
      const error = await preparePhoto(new File(['x'], 'x', { type }), { load, canvas: fakeCanvas().canvas }).catch((e: unknown) => e);
      expect(error).toBeInstanceOf(PhotoError);
      expect((error as PhotoError).reason).toBe('unsupported');
    }
    expect(load).not.toHaveBeenCalled();
  });

  it('says an image the browser cannot read, and one that does not fit even small', async () => {
    const file = new File(['x'], 'me.jpg', { type: 'image/jpeg' });
    const unreadable = await preparePhoto(file, { load: () => Promise.reject(new Error('decode')), canvas: fakeCanvas().canvas }).catch((e) => e);
    expect((unreadable as PhotoError).reason).toBe('unreadable');
    const tooBig = await preparePhoto(file, { load: async () => ({ width: 512, height: 512, image: {} }), canvas: fakeCanvas(900_000).canvas }).catch((e) => e);
    expect((tooBig as PhotoError).reason).toBe('too_large');
  });
});
