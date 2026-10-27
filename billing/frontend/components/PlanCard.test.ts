// A plan of the Store (mockups `store.html` «Planes»; round 17 §2.11; UX-AUDIT-4 X-03/X-08/X-09/X-14): its
// name, description, price (net, monthly or annual as the switch says) and features, and the ONE thing
// the chosen business can do with it now:
//   - on Free: «Upgrade to …» (the Embedded Checkout), the trial it is trying said on its card;
//   - paying: «Change to …» (confirmed with its proration), «Switch to annual/monthly» on its own plan,
//     «Downgrade to Free» (a cancellation at the end of the period);
//   - cancelled: «Keep the plan», and Free says from when;
//   - with an unpaid invoice nothing that charges, and the reason under the button (X-34).
import { describe, expect, it } from 'vitest';

import { FREE, FREE_SUBSCRIPTION, STARTER, plan, subscription } from '../__tests__/fixtures';
import { mountBilling } from '../__tests__/mount-billing';
import type { Block } from '../store';
import PlanCard from './PlanCard.vue';

const PRO = plan('pro', 'Pro', '59.99', '599.90');
const nb = (text: string) => text.replace(/ €/g, ' €');

async function card(props: { plan?: typeof STARTER; period?: 'month' | 'year'; subscription?: unknown; block?: Block | null; locale?: 'en' | 'es' }) {
  const { locale, ...rest } = props;
  const m = await mountBilling(PlanCard, {
    locale,
    props: { plan: STARTER, period: 'month', subscription: subscription(), block: null, ...rest },
  });
  const text = (id: string) => m.wrapper.find(`[data-testid="${id}"]`);
  return { ...m, text };
}

describe('PlanCard', () => {
  it('paints its name, description, net price and features', async () => {
    const s = await card({ subscription: FREE_SUBSCRIPTION });
    expect(s.text('plan-name').text()).toBe('Starter');
    expect(s.wrapper.text()).toContain('Starter description');
    expect(s.text('plan-price').text()).toBe('€29.99 /month + VAT');
    const features = s.wrapper.findAll('[data-testid="plan-feature"]');
    // Its text is read as rendered (`innerText`): Stencil patches the `textContent` of Ionic's items and labels.
    expect(features.map((item) => [item.element.tagName, (item.element as HTMLElement).innerText.trim()])).toEqual([['ION-ITEM', 'Starter feature']]);
    expect(s.wrapper.find('ion-list').exists()).toBe(true);
  });

  it('annual: the year’s price and what it is a month', async () => {
    const s = await card({ period: 'year', subscription: FREE_SUBSCRIPTION, locale: 'es' });
    expect(s.text('plan-price').text()).toBe(nb('299,90 € /año + IVA · 24,99 €/mes'));
  });

  it('Free says it costs nothing, forever', async () => {
    const s = await card({ plan: FREE, subscription: FREE_SUBSCRIPTION });
    expect(s.text('plan-price').text()).toBe('€0.00 forever');
  });

  describe('a business on Free', () => {
    it('Free is its current plan, with nothing to do', async () => {
      const s = await card({ plan: FREE, subscription: FREE_SUBSCRIPTION });
      expect(s.text('plan-current').text()).toBe('Your current plan');
      expect(s.wrapper.findAll('ion-button')).toHaveLength(0);
    });

    it('a paid plan is bought in the checkout, at the billing the switch says', async () => {
      const s = await card({ period: 'year', subscription: FREE_SUBSCRIPTION });
      const button = s.text('plan-upgrade');
      expect(button.text()).toBe('Upgrade to Starter');
      await button.trigger('click');
      expect(s.wrapper.emitted('upgrade')).toEqual([['year']]);
    });

    it('the plan it is trying says until when, and that buying it keeps the days left', async () => {
      const s = await card({ subscription: FREE_SUBSCRIPTION });
      expect(s.text('plan-trial').text()).toBe('Trying it until Oct 20, 2099');
      expect(s.text('plan-note').text()).toBe('Buying it now keeps the days left of the trial.');
    });

    it('without a subscription at all, Free is still its plan', async () => {
      const s = await card({ plan: FREE, subscription: null });
      expect(s.text('plan-current').exists()).toBe(true);
    });
  });

  describe('a business that pays', () => {
    it('its own plan is current; at the same billing there is nothing to do', async () => {
      const s = await card({});
      expect(s.text('plan-current').text()).toBe('Your current plan');
      expect(s.wrapper.findAll('ion-button')).toHaveLength(0);
    });

    it('its own plan at the other billing switches it, saying the new price', async () => {
      const s = await card({ period: 'year' });
      const button = s.text('plan-switch');
      expect(button.text()).toBe('Switch to annual · €299.90/year');
      await button.trigger('click');
      expect(s.wrapper.emitted('switch')).toEqual([['year']]);
      const back = await card({ period: 'month', subscription: subscription({ billing_interval: 'year' }) });
      expect(back.text('plan-switch').text()).toBe('Switch to monthly · €29.99/month');
    });

    it('another paid plan is a change, confirmed with its proration', async () => {
      const s = await card({ plan: PRO });
      const button = s.text('plan-change');
      expect(button.text()).toBe('Change to Pro');
      await button.trigger('click');
      expect(s.wrapper.emitted('change')).toEqual([['month']]);
    });

    it('Free is reached by cancelling the plan', async () => {
      const s = await card({ plan: FREE });
      const button = s.text('plan-downgrade');
      expect(button.text()).toBe('Downgrade to Free');
      await button.trigger('click');
      expect(s.wrapper.emitted('downgrade')).toHaveLength(1);
    });

    it('with an unpaid invoice nothing charges, and the reason is under the button', async () => {
      const s = await card({ period: 'year', block: 'card_declined' });
      const button = s.text('plan-switch');
      expect((button.element as unknown as { disabled: boolean }).disabled).toBe(true);
      const hint = s.text('plan-hint');
      expect(hint.text()).toBe('Pay the pending invoice first.');
      expect(hint.element.tagName).toBe('ION-NOTE');
      expect(button.element.tagName).toBe('ION-BUTTON');
      expect(button.find('ion-icon').exists()).toBe(true);
      expect(button.attributes('aria-describedby')).toBe(hint.attributes('id'));
      const change = await card({ plan: PRO, block: 'unpaid' });
      expect((change.text('plan-change').element as unknown as { disabled: boolean }).disabled).toBe(true);
    });

    it('cancelling still works with an unpaid invoice: it stops the next charges', async () => {
      const s = await card({ plan: FREE, block: 'unpaid' });
      expect((s.text('plan-downgrade').element as unknown as { disabled: boolean }).disabled).toBe(false);
    });
  });

  describe('a cancelled plan', () => {
    const cancelled = subscription({ cancel_at_period_end: true });

    it('says until when it lasts and offers to keep it', async () => {
      const s = await card({ subscription: cancelled });
      expect(s.text('plan-note').text()).toBe('Cancelled: Starter until Oct 31, 2026, then Free.');
      await s.text('plan-keep').trigger('click');
      expect(s.wrapper.emitted('keep')).toHaveLength(1);
    });

    it('Free says from when, with nothing to do', async () => {
      const s = await card({ plan: FREE, subscription: cancelled });
      expect(s.text('plan-note').text()).toBe('The business goes to Free on Oct 31, 2026.');
      expect(s.wrapper.findAll('ion-button')).toHaveLength(0);
    });

    it('another plan waits for the plan to be kept', async () => {
      const s = await card({ plan: PRO, subscription: cancelled });
      expect((s.text('plan-change').element as unknown as { disabled: boolean }).disabled).toBe(true);
      expect(s.text('plan-hint').text()).toBe('Keep the plan first to change it.');
    });

    it('keeping it with an unpaid invoice waits for the payment', async () => {
      const s = await card({ subscription: cancelled, block: 'unpaid' });
      expect((s.text('plan-keep').element as unknown as { disabled: boolean }).disabled).toBe(true);
      expect(s.text('plan-hint').text()).toBe('Pay the pending invoice first.');
    });
  });

  it('each action carries its icon: sparkles to upgrade, an arrow down to Free', async () => {
    const icon = (s: Awaited<ReturnType<typeof card>>, id: string) =>
      (s.text(id).find('ion-icon').element as unknown as { name?: string }).name;
    expect(icon(await card({ subscription: FREE_SUBSCRIPTION }), 'plan-upgrade')).toBe('sparkles-outline');
    expect(icon(await card({ plan: FREE }), 'plan-downgrade')).toBe('arrow-down-outline');
  });

  describe('the messages a month it includes (PLAN-SAAS §3.6)', () => {
    const quotas = (s: Awaited<ReturnType<typeof card>>) =>
      s.wrapper.findAll('[data-testid="plan-quota"]').map((item) => (item.element as HTMLElement).innerText.trim());
    const withMessages = (assistant: number, whatsapp: number) =>
      plan('standard', 'Standard', '54.99', '549.90', { assistant_messages_per_month: assistant, whatsapp_messages_per_month: whatsapp });

    it('says the assistant and WhatsApp messages, after the features', async () => {
      const s = await card({ plan: withMessages(600, 300), subscription: FREE_SUBSCRIPTION });
      expect(quotas(s)).toEqual(['AI assistant: 600 messages a month', 'WhatsApp: 300 messages a month']);
      const items = s.wrapper.findAll('ion-item').map((item) => item.attributes('data-testid'));
      expect(items).toEqual(['plan-feature', 'plan-apps', 'plan-quota', 'plan-quota']);
    });

    it('0 is none: no line rather than «0 messages»', async () => {
      expect(quotas(await card({ plan: withMessages(0, 0) }))).toEqual([]);
      expect(quotas(await card({ plan: withMessages(0, 40) }))).toEqual(['WhatsApp: 40 messages a month']);
    });

    it('one message reads in the singular', async () => {
      expect(quotas(await card({ plan: withMessages(1, 0) }))).toEqual(['AI assistant: 1 message a month']);
    });

    it('in Spanish', async () => {
      const s = await card({ plan: withMessages(300, 150), locale: 'es' });
      expect(quotas(s)).toEqual(['Asistente de IA: 300 mensajes al mes', 'WhatsApp: 150 mensajes al mes']);
    });
  });

  describe('the apps it turns on at once (`max_apps`, the cap the Hub applies since hub#256)', () => {
    /** Every line of the card, in order, with what it is. */
    const lines = (s: Awaited<ReturnType<typeof card>>) =>
      s.wrapper.findAll('ion-item').map((item) => [item.attributes('data-testid'), (item.element as HTMLElement).innerText.trim()]);
    const withApps = (maxApps: number, features: string[], extra: Partial<typeof STARTER> = {}) =>
      plan('standard', 'Standard', '54.99', '549.90', { max_apps: maxApps, features, ...extra });

    it('says up to how many, right after «All apps included», as /pricing/ does', async () => {
      const s = await card({ plan: withApps(40, ['All apps included', 'Up to 3 devices']) });
      expect(lines(s)).toEqual([
        ['plan-feature', 'All apps included'],
        ['plan-apps', 'Up to 40 apps turned on at once'],
        ['plan-feature', 'Up to 3 devices'],
      ]);
    });

    it('right after «Everything in …» on the plans above', async () => {
      const s = await card({ plan: withApps(80, ['Everything in Starter', 'Priority support']) });
      expect(lines(s)).toEqual([
        ['plan-feature', 'Everything in Starter'],
        ['plan-apps', 'Up to 80 apps turned on at once'],
        ['plan-feature', 'Priority support'],
      ]);
    });

    it('0 is no limit: every app turned on at once', async () => {
      const s = await card({ plan: withApps(0, ['Everything in Standard']) });
      expect(lines(s)).toEqual([
        ['plan-feature', 'Everything in Standard'],
        ['plan-apps', 'All the apps turned on at once'],
      ]);
    });

    it('one app reads in the singular', async () => {
      const s = await card({ plan: withApps(1, ['All apps included']) });
      expect(lines(s)).toEqual([
        ['plan-feature', 'All apps included'],
        ['plan-apps', 'Up to 1 app turned on at once'],
      ]);
    });

    it('without such a line it ends the plan’s own features: then the messages, then its trial, as /pricing/', async () => {
      const s = await card({
        plan: withApps(20, ['Sell and invoice', '15-day free trial'], { trial_period_days: 15, has_trial: true, whatsapp_messages_per_month: 40 }),
      });
      expect(lines(s)).toEqual([
        ['plan-feature', 'Sell and invoice'],
        ['plan-apps', 'Up to 20 apps turned on at once'],
        ['plan-quota', 'WhatsApp: 40 messages a month'],
        ['plan-feature', '15-day free trial'],
      ]);
    });

    it('an upgrade-only plan has no trial line: its last feature stays a feature', async () => {
      const s = await card({ plan: withApps(0, ['Sell and invoice', 'Priority support'], { trial_period_days: 15, upgrade_only: true }) });
      expect(lines(s)).toEqual([
        ['plan-feature', 'Sell and invoice'],
        ['plan-feature', 'Priority support'],
        ['plan-apps', 'All the apps turned on at once'],
      ]);
    });

    it('in Spanish, after «Todas las apps incluidas» or «Todo lo del plan …»', async () => {
      const starter = await card({ plan: withApps(40, ['Todas las apps incluidas', 'Hasta 3 dispositivos']), locale: 'es' });
      expect(lines(starter)).toEqual([
        ['plan-feature', 'Todas las apps incluidas'],
        ['plan-apps', 'Hasta 40 apps activadas a la vez'],
        ['plan-feature', 'Hasta 3 dispositivos'],
      ]);
      const max = await card({ plan: withApps(0, ['Todo lo del plan Standard', 'Soporte prioritario']), locale: 'es' });
      expect(lines(max)).toEqual([
        ['plan-feature', 'Todo lo del plan Standard'],
        ['plan-apps', 'Todas las apps activadas a la vez'],
        ['plan-feature', 'Soporte prioritario'],
      ]);
      const one = await card({ plan: withApps(1, ['Todas las apps incluidas']), locale: 'es' });
      expect(lines(one)).toContainEqual(['plan-apps', 'Hasta 1 app activada a la vez']);
    });

    it('the line carries the same check as the features', async () => {
      const s = await card({ plan: withApps(40, ['All apps included']) });
      expect((s.text('plan-apps').find('ion-icon').element as unknown as { name?: string }).name).toBe('checkmark-outline');
    });
  });

  it('speaks Spanish', async () => {
    const s = await card({ plan: FREE, locale: 'es' });
    expect(s.text('plan-downgrade').text()).toBe('Bajar a Gratis');
  });
});
