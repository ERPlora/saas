import { describe, expect, it } from 'vitest';

import { flush, ionProps, mountBilling } from '../__tests__/mount-billing';
import CollapsibleChecklist from './CollapsibleChecklist.vue';

const ITEMS = Array.from({ length: 7 }, (_, index) => ({ text: `Detail ${index + 1}`, testid: `detail-${index + 1}` }));

async function checklist(extra: Record<string, unknown> = {}) {
  const mounted = await mountBilling(CollapsibleChecklist, {
    props: {
      items: ITEMS,
      showAllLabel: 'All details',
      showFewerLabel: 'Less detail',
      toggleTestid: 'details-toggle',
      expanded: false,
      ...extra,
    },
  });
  await flush();
  return mounted;
}

describe('CollapsibleChecklist', () => {
  it('shows five items by default and expands with an Ionic disclosure button', async () => {
    const { wrapper } = await checklist();
    const list = wrapper.get('ion-list');
    const toggle = wrapper.get('[data-testid="details-toggle"]');
    expect(wrapper.findAll('ion-item')).toHaveLength(5);
    expect((wrapper.get('[data-testid="detail-1"]').element as HTMLElement).innerText.trim()).toBe('Detail 1');
    expect(toggle.element.tagName).toBe('ION-BUTTON');
    expect(ionProps(toggle, 'fill', 'size')).toEqual({ fill: 'clear', size: 'small' });
    expect(toggle.text()).toBe('All details');
    expect(toggle.attributes('aria-expanded')).toBe('false');
    expect(toggle.attributes('aria-controls')).toBe(list.attributes('id'));
    expect(toggle.get('ion-icon').attributes('slot')).toBe('start');

    await toggle.trigger('click');
    expect(wrapper.findAll('ion-item')).toHaveLength(7);
    expect(toggle.attributes('aria-expanded')).toBe('true');
    expect(toggle.text()).toBe('Less detail');

    await toggle.trigger('click');
    expect(wrapper.findAll('ion-item')).toHaveLength(5);
    expect(wrapper.text()).not.toContain('Detail 6');
  });

  it('accepts a different collapsed count and caller-provided labels', async () => {
    const { wrapper } = await checklist({
      items: ITEMS.slice(0, 3).map(({ text }) => ({ text })),
      collapsedCount: 2,
      showAllLabel: 'Mostrar todo',
      showFewerLabel: 'Mostrar menos',
    });
    expect(wrapper.findAll('ion-item')).toHaveLength(2);
    expect(wrapper.get('ion-item').attributes('data-testid')).toBeUndefined();
    const toggle = wrapper.get('[data-testid="details-toggle"]');
    expect(toggle.text()).toBe('Mostrar todo');
    await toggle.trigger('click');
    expect(wrapper.findAll('ion-item')).toHaveLength(3);
    expect(toggle.text()).toBe('Mostrar menos');
  });

  it('omits the disclosure when every item fits', async () => {
    const { wrapper } = await checklist({ items: ITEMS.slice(0, 5) });
    expect(wrapper.findAll('ion-item')).toHaveLength(5);
    expect(wrapper.find('[data-testid="details-toggle"]').exists()).toBe(false);
  });
});
