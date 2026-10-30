// The size of a copy of a business's data, as «Download the data» says it (DataCopyCard): in the person's language,
// in kB, MB or GB (1024 each), one decimal at most.
import { describe, expect, it } from 'vitest';

import { formatBytes } from './data-copy';

describe('formatBytes', () => {
  it.each([
    [0, 'en', '0 kB'],
    [1_536, 'es', '1,5 kB'],
    [48_213_504, 'en', '46 MB'],
    [48_213_504, 'es', '46 MB'],
    [5 * 1024 ** 3, 'en', '5 GB'],
    [1_610_612_736, 'es', '1,5 GB'],
  ])('%d bytes in %s are %s', (bytes, locale, text) => {
    expect(formatBytes(bytes, locale)).toBe(text);
  });
});
