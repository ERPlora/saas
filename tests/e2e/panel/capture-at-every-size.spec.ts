// flow: ninguno — tooling of the e2e harness, nothing anyone sees changes (saas#336)
// The walk of `captureAtEverySize` (fixtures.ts), which the panel's specs take to check a screen at phone, tablet and
// desktop: if it skipped a size, no spec failed, only that size's captures were missing (saas#336). Here it walks a
// page of its own (`page.setContent`, no server) whose `ready` writes down the size it is called at: the three sizes,
// in their order, a capture of each at its size, and back at the desktop at the end. Its captures are removed, before
// and after, so the evidence of `.artifacts/panel/` only holds the screens'.
import { existsSync, readFileSync, rmSync } from 'node:fs';
import { basename } from 'node:path';

import { captureAtEverySize, expect, shot, test } from './fixtures';

const PREFIX = 'saas-e2e-walk';
const KEY = 'probe';

/** Phone, tablet and desktop, in this order (working rules §2.4), and the size the walk leaves the page at. */
const SIZES = [
  { width: 390, height: 844 },
  { width: 834, height: 1112 },
  { width: 1440, height: 900 },
];
const DESKTOP = { width: 1440, height: 900 };

const capturesOf = () => SIZES.map(({ width }) => shot(`${PREFIX}-${KEY}-${width}`));
const removeCaptures = () => capturesOf().forEach((path) => rmSync(path, { force: true }));

/** Width and height of the PNG at `path`, from its IHDR chunk. */
function pngSize(path: string): { width: number; height: number } {
  const png = readFileSync(path);
  return { width: png.readUInt32BE(16), height: png.readUInt32BE(20) };
}

test('saas-e2e-walk: captureAtEverySize walks 390, 834 and 1440 in order, captures each and ends at the desktop', async ({ page }) => {
  removeCaptures();
  try {
    await page.setContent('<!doctype html><main>A page that fits every size</main>');
    const ratio = await page.evaluate(() => devicePixelRatio);
    const seen: Array<{ width: number; height: number } | null> = [];
    await captureAtEverySize(PREFIX)(page, KEY, async () => {
      seen.push(page.viewportSize());
    });
    expect(seen, 'the sizes `ready` was called at').toEqual(SIZES);
    expect(page.viewportSize(), 'the size the walk ends at').toEqual(DESKTOP);
    const captured = capturesOf().map((path) => (existsSync(path) ? pngSize(path) : `${basename(path)} missing`));
    const atEachSize = SIZES.map(({ width, height }) => ({ width: width * ratio, height: height * ratio }));
    expect(captured, 'one capture per size, taken at that size').toEqual(atEachSize);
  } finally {
    removeCaptures();
  }
});
