// What every test of the SaaS runs under (`vitest.setup.ts`): nothing a test mounted outlives it. Vue apps left
// mounted keep their listeners on `window`, so each later test paid for all the earlier ones: InvoicesTab.test.ts,
// which resizes the window around each test, went from 83 ms in its third test to 666 ms in its 47th (saas#251).
// And an icon paints by name with nothing to prepare: an unregistered one warns with its whole element, which Vitest
// dumps by the thousand lines (saas#253, saas#255).
import { HubIcon } from '@erplora/ui/shell';
import { mount } from '@vue/test-utils';
import { describe, expect, it, vi } from 'vitest';
import { defineComponent, h, onUnmounted } from 'vue';

describe('a test that paints an icon and prepares nothing', () => {
  it('has it painted by name, with no warning', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const icon = mount(HubIcon, { props: { name: 'ion:refresh-outline' }, attachTo: document.body }).element;
    await vi.waitFor(() => expect(icon.shadowRoot?.querySelector('svg')).not.toBeNull());
    expect(warn).not.toHaveBeenCalled();
    warn.mockRestore();
  });
});

describe('a test that mounts a component and leaves', () => {
  const unmounted = vi.fn();
  const Page = defineComponent({
    setup() {
      onUnmounted(unmounted);
      return () => h('div');
    },
  });

  it('keeps it mounted while the test lasts', () => {
    mount(Page, { attachTo: document.body });
    expect(unmounted).not.toHaveBeenCalled();
  });

  it('has it unmounted before the next test starts', () => {
    expect(unmounted).toHaveBeenCalledOnce();
  });
});
