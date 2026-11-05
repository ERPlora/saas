// A read-only address with «Copy» (mockups `business.html`: «En tus dispositivos» and Settings): the
// text in monospace and a copy button that says what happened in a toast.
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@erplora/ui/shell', async (original) => (await import('../__tests__/module-mocks')).shellWithToastSpies(original));

import { toastError, toastSuccess } from '@erplora/ui/shell';

import { accessibleName, flush, mountHubs, stubClipboard as clipboard } from '../__tests__/mount-hubs';
import CopyField from './CopyField.vue';

afterEach(() => {
  vi.restoreAllMocks();
  vi.mocked(toastSuccess).mockClear();
  vi.mocked(toastError).mockClear();
  document.body.innerHTML = '';
});

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

  it('copies what is not an address (a DNS record) with the words it is given', async () => {
    const writeText = vi.fn(() => Promise.resolve());
    clipboard(writeText);
    const texts = { copyLabel: 'Copy the value', copiedText: 'Value copied', failedText: 'Copy it by hand.' };
    const { wrapper } = await mountHubs(CopyField, { props: { value: 'hub-h1.erplora.com', label: 'Value', ...texts } });
    const button = wrapper.get('[data-testid="copy-button"]');
    expect(accessibleName(button)).toBe('Copy the value');
    expect(button.attributes('title')).toBe('Copy the value');
    await button.trigger('click');
    await flush();
    expect(writeText).toHaveBeenCalledWith('hub-h1.erplora.com');
    expect(toastSuccess).toHaveBeenCalledWith('Value copied');
    clipboard(() => Promise.reject(new Error('denied')));
    await button.trigger('click');
    await flush();
    expect(toastError).toHaveBeenCalledWith('Copy it by hand.');
  });
});
