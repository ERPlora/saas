// A read-only address with «Copy» (mockups `business.html`: «En tus dispositivos» and Settings): the
// text in monospace and a copy button that says what happened in a toast.
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastSuccess: vi.fn(() => Promise.resolve()),
  toastError: vi.fn(() => Promise.resolve()),
}));

import { toastError, toastSuccess } from '@erplora/ui/shell';

import { accessibleName, flush, mountHubs } from '../__tests__/mount-hubs';
import CopyField from './CopyField.vue';

afterEach(() => {
  vi.restoreAllMocks();
  vi.mocked(toastSuccess).mockClear();
  vi.mocked(toastError).mockClear();
  document.body.innerHTML = '';
});

function clipboard(writeText: (text: string) => Promise<void>) {
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
}

describe('CopyField', () => {
  it('shows the text and copies it, saying so', async () => {
    const writeText = vi.fn(() => Promise.resolve());
    clipboard(writeText);
    const { wrapper } = await mountHubs(CopyField, { props: { value: 'bakery.erplora.com', label: 'Web address of the business' } });
    expect(wrapper.get('[data-testid="copy-value"]').text()).toBe('bakery.erplora.com');
    const button = wrapper.get('[data-testid="copy-button"]');
    expect(accessibleName(button)).toBe('Copy address');
    await button.trigger('click');
    await flush();
    expect(writeText).toHaveBeenCalledWith('bakery.erplora.com');
    expect(toastSuccess).toHaveBeenCalledWith('Address copied');
  });

  it('says how to copy it by hand when the browser refuses', async () => {
    clipboard(() => Promise.reject(new Error('denied')));
    const { wrapper } = await mountHubs(CopyField, { props: { value: 'bakery.erplora.com', label: 'x' } });
    await wrapper.get('[data-testid="copy-button"]').trigger('click');
    await flush();
    expect(toastError).toHaveBeenCalledWith('The address could not be copied. Select it and copy it by hand.');
  });
});
