// `qrcode` as the SPA runs it: the browser build Vite bundles (the package's `browser` field), mapped
// by `paths` in tsconfig.app.json. `@types/qrcode` also types the Node build (files, streams, `Buffer`)
// and references Node's types, which would give every page Node's globals (`process`…): only the
// Vitest project, which runs in Node, keeps it. Just what the SPA calls; a page that needs more adds it
// from the package's browser API (`create`, `toCanvas`, `toString`).
declare namespace QRCode {
  type ErrorCorrectionLevel = 'low' | 'medium' | 'quartile' | 'high' | 'L' | 'M' | 'Q' | 'H';

  interface ToDataURLOptions {
    errorCorrectionLevel?: ErrorCorrectionLevel;
    /** Quiet zone around the code, in modules. */
    margin?: number;
    /** Pixels per module; `width` wins when both are given. */
    scale?: number;
    width?: number;
    color?: { dark?: string; light?: string };
    type?: 'image/png' | 'image/jpeg' | 'image/webp';
    rendererOpts?: { quality?: number };
  }

  /** The QR code of `text` as a `data:` URL of an image (PNG unless `type` says otherwise). */
  function toDataURL(text: string, options?: ToDataURLOptions): Promise<string>;
}

export = QRCode;
