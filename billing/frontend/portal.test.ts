// «Change card» (mockups `billing.html`; README §6.18): Stripe's Customer Portal for the payer of a business
// (`billing.portal.open`, cards and Stripe's receipts), a top-level navigation; it comes back to Billing.
// One opening at a time; a refusal (no payment yet, the Portal not configured) is said in a toast.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { defineComponent } from 'vue';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastError: vi.fn(() => Promise.resolve()),
}));

import { toastError } from '@erplora/ui/shell';

import { apiError, flush, mountBilling } from './__tests__/mount-billing';
import { browser } from './browser';
import { useCardPortal } from './portal';

afterEach(() => {
  vi.restoreAllMocks();
  vi.mocked(toastError).mockClear();
  document.body.innerHTML = '';
});

async function setup(api: () => Response | Promise<Response>) {
  let portal!: ReturnType<typeof useCardPortal>;
  const Host = defineComponent({
    setup() {
      portal = useCardPortal();
      return () => null;
    },
  });
  const s = await mountBilling(Host, { api });
  return { ...s, portal: () => portal };
}

describe('useCardPortal', () => {
  it('opens the Customer Portal of the business’s payer and goes there', async () => {
    const assign = vi.spyOn(browser, 'assign').mockImplementation(() => {});
    const s = await setup(() => Response.json({ url: 'https://billing.stripe.com/p/session/x' }));
    const opened = s.portal().open('plaza');
    expect(s.portal().opening.value).toBe('plaza');
    expect(await opened).toBe(true);
    expect(s.calls()).toEqual([{ method: 'POST', path: '/api/billing/portal', body: { hub_id: 'plaza' }, query: {} }]);
    expect(assign).toHaveBeenCalledExactlyOnceWith('https://billing.stripe.com/p/session/x');
  });

  it('opens it once at a time', async () => {
    vi.spyOn(browser, 'assign').mockImplementation(() => {});
    const s = await setup(() => Response.json({ url: 'https://billing.stripe.com/p/session/x' }));
    void s.portal().open('plaza');
    expect(await s.portal().open('plaza')).toBe(false);
    await flush();
    expect(s.calls()).toHaveLength(1);
  });

  it('says a refusal in a toast and lets it be tried again', async () => {
    const assign = vi.spyOn(browser, 'assign').mockImplementation(() => {});
    const s = await setup(() => apiError(409, 'billing.no_customer', 'The payment details appear here after the first payment.'));
    expect(await s.portal().open('cafe')).toBe(false);
    expect(toastError).toHaveBeenCalledWith('The payment details appear here after the first payment.');
    expect(assign).not.toHaveBeenCalled();
    expect(s.portal().opening.value).toBeNull();
  });

  it('back through the browser’s cache, nothing is opening any more', async () => {
    vi.spyOn(browser, 'assign').mockImplementation(() => {});
    const s = await setup(() => Response.json({ url: 'https://billing.stripe.com/p/session/x' }));
    await s.portal().open('plaza');
    expect(s.portal().opening.value).toBe('plaza');
    window.dispatchEvent(Object.assign(new Event('pageshow'), { persisted: true }));
    expect(s.portal().opening.value).toBeNull();
  });
});
