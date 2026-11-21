// The page of the codes shown again: Ionic keeps the page, and each arrival reads the session once and
// starts from the address and code it is handed, with nothing of the last visit.
import { IonInput } from '@ionic/vue';
import { flushPromises } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';

import { anonymous, fakeAllauth, ok, pendingEmailVerification, pendingLoginCode, rejected, signedIn } from '../__tests__/allauth-server';
import { enterView } from '../__tests__/mount-account-page';
import { assign, mountPage, setUpVerifyEmailPage } from '../__tests__/verify-email-page';

setUpVerifyEmailPage();

describe('VerifyEmailPage: coming back to it (Ionic keeps the page and shows it again)', () => {
  type Mounted = Awaited<ReturnType<typeof mountPage>>;

  /** The visitor goes to the sign-in and comes back to `to` (a location of the router, with its history state). */
  async function comeBack({ wrapper, router }: Mounted, to: Parameters<Mounted['router']['push']>[0]): Promise<void> {
    if (router.currentRoute.value.path !== '/launch') await router.push('/launch');
    await router.push(to);
    enterView(wrapper);
    await flushPromises();
  }

  it("after «Use a different email», the real account finds its own address and code, never the typo's", async () => {
    const server = fakeAllauth({
      'GET /auth/session': pendingEmailVerification,
      'DELETE /auth/session': anonymous,
      'POST /auth/code/confirm': signedIn,
    });
    const mounted = await mountPage({ email: 'typo@exmaple.com', flow: 'verify_email' });
    const { wrapper, router, click, verify, button } = mounted;
    await wrapper.getComponent(IonInput).setValue('111111');
    await click('verify-email-other');
    expect(router.currentRoute.value.fullPath).toBe('/launch');

    // The sign-in of the real account: a code to the account, handed over as the launcher's form does.
    server.serve({ 'GET /auth/session': pendingLoginCode });
    await comeBack(mounted, { path: '/verify-email', state: { email: 'owner@example.com', flow: 'login_by_code' } });

    expect(wrapper.get('p.auth-lead').text()).toBe('We emailed a code to owner@example.com');
    expect(wrapper.getComponent(IonInput).props('modelValue')).toBe('');
    expect(button('verify-email-resend')).toBeUndefined();
    expect(wrapper.find('[data-testid="verify-email-help"]').exists()).toBe(true);
    await verify('482913');
    expect(server.callsTo('POST /auth/code/confirm').map((c) => c.body)).toEqual([{ code: '482913' }]);
    expect(server.callsTo('POST /auth/email/verify')).toEqual([]);
    expect(assign).toHaveBeenCalledExactlyOnceWith('/launch');
  });

  it('reads the session again and leaves nothing of the last visit: no digits, no error, no notice', async () => {
    const server = fakeAllauth({
      'GET /auth/session': pendingEmailVerification,
      'POST /auth/email/verify': rejected('Incorrect code.', 'key'),
      'POST /auth/email/verify/resend': ok(),
    });
    const mounted = await mountPage({ email: 'new@example.com' });
    const { wrapper, verify, click, failure, notice } = mounted;
    await click('verify-email-resend');
    expect(notice().exists()).toBe(true);
    await verify('000000');
    expect(wrapper.getComponent(IonInput).classes()).toContain('ion-invalid');

    await comeBack(mounted, { path: '/verify-email', state: { email: 'other@example.com', flow: 'verify_email' } });

    expect(server.callsTo('GET /auth/session')).toHaveLength(2);
    expect(wrapper.get('p.auth-lead').text()).toBe('We emailed a code to other@example.com');
    const input = wrapper.getComponent(IonInput);
    expect([input.props('modelValue'), input.classes().includes('ion-invalid')]).toEqual(['', false]);
    expect([failure().exists(), notice().exists()]).toEqual([false, false]);
  });

  it('says where the code went without an address when it comes back with none (a reload, another tab)', async () => {
    fakeAllauth({ 'GET /auth/session': pendingEmailVerification });
    const mounted = await mountPage({ email: 'new@example.com' });

    await comeBack(mounted, '/verify-email');

    expect(mounted.wrapper.get('p.auth-lead').text()).toBe('We emailed a code to your email address.');
  });

  it('follows the session it reads again: signed in meanwhile, it leaves for next', async () => {
    fakeAllauth({ 'GET /auth/session': [pendingEmailVerification, signedIn] });
    const mounted = await mountPage({ path: '/verify-email?next=%2Faccount' });

    await comeBack(mounted, '/verify-email?next=%2Faccount');

    expect(assign).toHaveBeenCalledExactlyOnceWith('/account');
  });

  it('reads the session once per arrival: Ionic announces the first one too, around the mount', async () => {
    const server = fakeAllauth({ 'GET /auth/session': pendingEmailVerification });
    const { wrapper } = await mountPage({ email: 'new@example.com' });

    enterView(wrapper);
    await flushPromises();

    expect(server.callsTo('GET /auth/session')).toHaveLength(1);
  });
});
