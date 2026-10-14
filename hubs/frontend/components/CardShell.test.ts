// The centred-card frame of the launcher and the invitation (mockups `launch.html`, `invitation.html`;
// old SaaS `_shell_styles.html`): no menu, the ERPlora lockup INSIDE the card above the title, the
// state's icon and title (the page's heading), a lead under it, the content, and under the card
// «Signed in as … · Sign out» (Django's logout form, as the old launcher posted it).
import { afterEach, describe, expect, it } from 'vitest';
import { h } from 'vue';

import { ANONYMOUS, mountHubs } from '../__tests__/mount-hubs';
import CardShell from './CardShell.vue';

afterEach(() => {
  document.body.innerHTML = '';
  document.cookie = 'csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT';
});

async function mountShell(options: Parameters<typeof mountHubs>[1] = {}) {
  const Host = {
    render: () =>
      h(CardShell, { icon: 'ion:storefront-outline', title: 'Create your business', lead: 'Free and no card.' }, () =>
        h('p', { 'data-testid': 'content' }, 'The form'),
      ),
  };
  return mountHubs(Host, options);
}

describe('CardShell', () => {
  it('paints the lockup inside the card, then the icon, the title as the heading and the lead', async () => {
    const { wrapper } = await mountShell();
    const card = wrapper.get('ion-card.shell-card');
    expect(card.get('[role="img"]').attributes('aria-label')).toBe('ERPlora');
    expect(card.get('.erp-wordmark').text()).toBe('ERPlora');
    const title = card.get('ion-card-title');
    expect(title.attributes('role')).toBe('heading');
    expect(title.attributes('aria-level')).toBe('1');
    expect(title.text()).toBe('Create your business');
    expect(card.get('.shell-lead').text()).toBe('Free and no card.');
    expect(card.get('[data-testid="content"]').text()).toBe('The form');
    // The lockup comes first, above the title (README §5).
    const html = card.html();
    expect(html.indexOf('erp-lockup')).toBeLessThan(html.indexOf('ion-card-title'));
  });

  it('is the main landmark of a page outside the menu', async () => {
    const { wrapper } = await mountShell();
    expect(wrapper.find('.ion-page main.shell-page').exists()).toBe(true);
  });

  it('says who is signed in and signs out with Django’s logout form, back to the sign-in', async () => {
    document.cookie = 'csrftoken=tok123';
    const { wrapper } = await mountShell();
    const account = wrapper.get('[data-testid="shell-account"]');
    expect(account.text()).toContain('Signed in as laura@example.com');
    const form = account.get('form');
    expect(form.attributes('method')).toBe('post');
    expect(form.attributes('action')).toBe('/accounts/logout/');
    const fields = Object.fromEntries(form.findAll('input[type="hidden"]').map((i) => [i.attributes('name'), (i.element as HTMLInputElement).value]));
    expect(fields).toEqual({ csrfmiddlewaretoken: 'tok123', next: '/login' });
    expect(form.get('ion-button').text()).toBe('Sign out');
    expect((form.get('ion-button').element as HTMLElement & { type?: string }).type).toBe('submit');
  });

  it('has no account line without a session', async () => {
    const { wrapper } = await mountShell({ session: ANONYMOUS });
    expect(wrapper.find('[data-testid="shell-account"]').exists()).toBe(false);
  });

  it('speaks Spanish', async () => {
    const { wrapper } = await mountShell({ locale: 'es' });
    expect(wrapper.get('[data-testid="shell-account"]').text()).toContain('Conectado como laura@example.com');
    expect(wrapper.get('[data-testid="shell-account"] ion-button').text()).toBe('Cerrar sesión');
  });
});
