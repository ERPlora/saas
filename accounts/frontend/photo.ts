// The profile photo, made small in the browser before it travels (accounts/README.md, «Foto en la BD»): the server
// keeps at most 150 KB (`photos.MAX_PHOTO_BYTES`) and has no image library to shrink one. The picked file is drawn
// on a canvas at most 512 px on its longer side over white (a transparent PNG would turn black as a JPEG); a canvas
// draws one frame, so an animation arrives still, and nothing of the file's metadata survives the re-drawing. The
// JPEG's quality drops until it fits.

/** The longer side of the photo the panel sends (the avatar paints it at 40 px; 512 covers any screen). */
export const MAX_PHOTO_SIDE = 512;
/** What the server keeps at most (`accounts/photos.py`, `MAX_PHOTO_BYTES`). */
export const MAX_PHOTO_BYTES = 150_000;
/** The kinds of image the server takes (and the file picker offers). */
export const PHOTO_TYPES = ['image/jpeg', 'image/png', 'image/webp'] as const;
/** The JPEG qualities tried, best first. */
const QUALITIES = [0.9, 0.8, 0.7, 0.6, 0.5, 0.4];

export type PhotoErrorReason = 'unsupported' | 'unreadable' | 'too_large';

/** Why a picked file cannot be the photo (the panel says it in the reader's language). */
export class PhotoError extends Error {
  constructor(readonly reason: PhotoErrorReason) {
    super(`photo: ${reason}`);
    this.name = 'PhotoError';
  }
}

/** The size that fits within `max` on its longer side, keeping the shape; never larger than it was. */
export function fitWithin(width: number, height: number, max = MAX_PHOTO_SIDE): { width: number; height: number } {
  const scale = Math.min(1, max / Math.max(width, height));
  return { width: Math.max(1, Math.round(width * scale)), height: Math.max(1, Math.round(height * scale)) };
}

/** The bytes a base64 data URL carries once decoded. */
export function dataUrlBytes(url: string): number {
  const payload = url.slice(url.indexOf(',') + 1);
  const padding = payload.endsWith('==') ? 2 : payload.endsWith('=') ? 1 : 0;
  return (payload.length / 4) * 3 - padding;
}

/** The first encoding, best quality first, that fits `maxBytes`; `null` when none does. */
export function encodeWithin(encode: (quality: number) => string, maxBytes = MAX_PHOTO_BYTES): string | null {
  for (const quality of QUALITIES) {
    const url = encode(quality);
    if (dataUrlBytes(url) <= maxBytes) return url;
  }
  return null;
}

/** A decoded image, as the canvas draws it. */
export interface LoadedImage {
  width: number;
  height: number;
  image: unknown;
}

/** A canvas of a given size: draw the image over white, encode it. */
export interface PhotoCanvas {
  draw(image: unknown): void;
  encode(type: string, quality: number): string;
}

export interface PhotoDeps {
  load(file: File): Promise<LoadedImage>;
  canvas(width: number, height: number): PhotoCanvas;
}

/** The browser's image decoder and canvas. */
const BROWSER: PhotoDeps = {
  async load(file) {
    const bitmap = await createImageBitmap(file);
    return { width: bitmap.width, height: bitmap.height, image: bitmap };
  },
  canvas(width, height) {
    const element = document.createElement('canvas');
    element.width = width;
    element.height = height;
    const context = element.getContext('2d');
    if (!context) throw new PhotoError('unreadable');
    return {
      draw(image) {
        context.fillStyle = '#fff';
        context.fillRect(0, 0, width, height);
        context.drawImage(image as CanvasImageSource, 0, 0, width, height);
      },
      encode: (type, quality) => element.toDataURL(type, quality),
    };
  },
};

/** The photo to send for `file`: a still JPEG data URL of at most 512 px and 150 KB. */
export async function preparePhoto(file: File, deps: PhotoDeps = BROWSER): Promise<string> {
  if (!(PHOTO_TYPES as readonly string[]).includes(file.type)) throw new PhotoError('unsupported');
  let loaded: LoadedImage;
  try {
    loaded = await deps.load(file);
  } catch {
    throw new PhotoError('unreadable');
  }
  const size = fitWithin(loaded.width, loaded.height);
  const canvas = deps.canvas(size.width, size.height);
  canvas.draw(loaded.image);
  const url = encodeWithin((quality) => canvas.encode('image/jpeg', quality));
  if (!url || !url.startsWith('data:image/jpeg;base64,')) throw new PhotoError(url ? 'unreadable' : 'too_large');
  return url;
}
