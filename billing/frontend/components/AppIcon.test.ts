// The icon of a module, from the app catalog (`apps.app.list` → `icon_svg`: the SVG the Hub bakes,
// cleaned with nh3 by the SaaS, `apps/icons.py`). It is painted the way every icon of the shell is:
// `ion-icon` with the SVG as its `;utf8,` data URL, which ion-icon sanitises again and writes into its
// shadow root — the one HTML sink the page's Trusted Types policy admits (`<svg` only). Never `v-html`.
// Without a usable SVG, the catalog's fallback, `ion:apps-outline`.
import { describe, expect, it } from 'vitest';

import { mountBilling } from '../__tests__/mount-billing';
import AppIcon from './AppIcon.vue';

const SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" class="ionicon"><path d="M1 1h10" class="ionicon-fill-none ionicon-stroke-width"/></svg>';

describe('AppIcon', () => {
  it('paints the catalog’s SVG through ion-icon, decorative, without writing HTML itself', async () => {
    const { wrapper } = await mountBilling(AppIcon, { props: { svg: SVG } });
    const icon = wrapper.find('ion-icon');
    expect((icon.element as unknown as { icon?: string }).icon).toBe(`data:image/svg+xml;utf8,${SVG}`);
    expect(icon.attributes('aria-hidden')).toBe('true');
    // The SVG is the icon's data, not markup of the page.
    expect(wrapper.element.querySelector('svg')).toBeNull();
  });

  it('without an icon, or with something that is not an SVG, paints the catalog’s fallback', async () => {
    for (const svg of ['', '   ', '<img src=x onerror=alert(1)>']) {
      const { wrapper } = await mountBilling(AppIcon, { props: { svg } });
      const icon = wrapper.find('ion-icon');
      expect((icon.element as unknown as { name?: string }).name, svg).toBe('apps-outline');
      expect((icon.element as unknown as { icon?: string }).icon, svg).toBeUndefined();
    }
  });
});
