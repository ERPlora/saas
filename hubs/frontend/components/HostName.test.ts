// A business's web address that breaks only after a dot (audit 2 R-25; W-14 of the mockups): at 390 px the launcher
// split «e2e-billing- / plaza.localhost:8000» at the hyphen, as if it were two addresses, and the tables cut it with
// «…». Each part between dots stays whole; a line may end only after a dot.
import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';

import HostName from './HostName.vue';

describe('HostName', () => {
  it('reads as the address, whole', () => {
    const wrapper = mount(HostName, { props: { host: 'e2e-billing-plaza.localhost:8000' } });
    expect(wrapper.text()).toBe('e2e-billing-plaza.localhost:8000');
  });

  it('may break only after a dot: each part stays on one line', () => {
    const wrapper = mount(HostName, { props: { host: 'panaderia-lopez.erplora.com' } });
    const parts = wrapper.findAll('.host-name__part');
    expect(parts.map((part) => part.text())).toEqual(['panaderia-lopez.', 'erplora.', 'com']);
    expect(wrapper.findAll('wbr')).toHaveLength(2);
    expect(wrapper.html()).not.toMatch(/-<wbr>/);
  });
});
