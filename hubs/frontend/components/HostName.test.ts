// A business's web address that breaks only after a dot: at 390 px the launcher once split
// «e2e-billing- / plaza.localhost:8000» at the hyphen, as if it were two addresses, and the tables cut it with
// «…». Each part between dots stays whole while it fits; a line may end only after a dot. A part wider than
// its box (qa-restaurante-20261125-2101) breaks inside it instead of painting over the next column.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';

import HostName from './HostName.vue';

const STYLE = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'HostName.vue'), 'utf8').split('<style')[1] ?? '';

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

  it('breaks a part wider than its box inside the box, and only that part', () => {
    // A box as wide as its text and never wider than the line: a part that fits is never split.
    expect(STYLE).toMatch(/\.host-name__part \{[^}]*display: inline-block;/);
    expect(STYLE).toMatch(/\.host-name__part \{[^}]*max-width: 100%;/);
    expect(STYLE).toMatch(/\.host-name__part \{[^}]*overflow-wrap: anywhere;/);
    expect(STYLE).not.toMatch(/white-space: nowrap/);
  });
});
