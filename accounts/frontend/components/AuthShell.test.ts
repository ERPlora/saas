// The frame of every account screen, ported from ERPlora/saas's partials `account/_auth_header.html`
// + `_auth_shell_top.html` + `_auth_shell_bottom.html`: a back arrow (Lucide's, as the template) to
// home, the logo with «ERPlora Cloud» and a subtitle, a glass card with the screen's content, and
// an optional foot under the card. Full bleed, outside the shell's chrome.
import { ionIconSrc } from '@erplora/ui/shell';
import { IonButton, IonIcon } from '@ionic/vue';
import { describe, expect, it } from 'vitest';

import { mountAccountPage } from '../__tests__/mount-account-page';
import AuthShell from './AuthShell.vue';

const mountShell = (locale: 'en' | 'es' = 'en') =>
  mountAccountPage(AuthShell, {
    locale,
    props: { subtitle: 'Choose a business' },
    slots: { default: '<p class="probe">content</p>', foot: '<p class="probe-foot">foot</p>' },
  });

describe('AuthShell', () => {
  it('paints the logo, «ERPlora Cloud» and the subtitle it is given', async () => {
    const { wrapper } = await mountShell();
    const logo = wrapper.get('.erp-logo.lg');
    expect(logo.attributes('aria-label')).toBe('ERPlora Cloud');
    expect(logo.findAll('i')).toHaveLength(9);
    expect(wrapper.get('h1.biz-name').text()).toBe('ERPlora Cloud');
    expect(wrapper.get('.biz-sub').text()).toBe('Choose a business');
  });

  it('puts the screen in the glass card and the foot under it', async () => {
    const { wrapper } = await mountShell();
    expect(wrapper.get('ion-card.glass ion-card-content .probe').text()).toBe('content');
    expect(wrapper.find('ion-card .probe-foot').exists()).toBe(false);
    expect(wrapper.get('.auth-card > .probe-foot').text()).toBe('foot');
  });

  it("goes back home with the template's Lucide arrow, baked so it paints offline", async () => {
    const { wrapper } = await mountShell();
    const back = wrapper.findAllComponents(IonButton).find((b) => b.classes().includes('auth-back'))!;
    expect([back.props('href'), back.props('fill'), back.attributes('aria-label')]).toEqual(['/', 'clear', 'Back to home']);
    const icon = back.findComponent(IonIcon);
    expect(icon.attributes('slot')).toBe('icon-only');
    expect(icon.props('icon')).toBe(ionIconSrc('lucide:arrow-left'));
    expect(icon.props('icon')).toMatch(/^data:image\/svg\+xml;utf8,<svg /);
  });

  it('speaks Spanish', async () => {
    const { wrapper } = await mountShell('es');
    const back = wrapper.findAllComponents(IonButton).find((b) => b.classes().includes('auth-back'))!;
    expect(back.attributes('aria-label')).toBe('Volver al inicio');
  });
});
