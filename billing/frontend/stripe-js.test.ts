// Stripe.js for the Embedded Checkout (PLAN-SAAS §3.6 point 17; plan §7 point 5): the one script that
// comes from another origin (PCI: never served by us), loaded only when a payment opens and only on the
// web. It is inserted by our own code, with the page's CSP nonce. Its address is a plain string: the
// page's `default` Trusted Types policy admits the script URLs of `https://js.stripe.com` and no other
// (`createShell({ trustedScriptOrigins })` in frontend/main.ts), the same door Stripe.js's own chunks use.
import { applySurface } from '@erplora/ui/shell';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { loadStripeJs, resetStripeJs, STRIPE_JS_URL } from './stripe-js';

afterEach(() => {
  resetStripeJs();
  applySurface('web');
});

/** A page as the loader sees it: its nonced scripts, its head and, maybe, Trusted Types. */
function page(options: { nonce?: string; trustedTypes?: boolean } = {}) {
  const appended: HTMLScriptElement[] = [];
  const policies: Array<{ name: string; createScriptURL: (url: string) => string }> = [];
  const nonced = document.createElement('script');
  if (options.nonce) nonced.nonce = options.nonce;
  const doc = {
    createElement: (tag: string) => document.createElement(tag),
    querySelector: (selector: string) => (selector === 'script[nonce]' && options.nonce ? nonced : null),
    head: { append: (el: HTMLScriptElement) => void appended.push(el) },
  } as unknown as Document;
  const win: { Stripe?: unknown; trustedTypes?: unknown } = {};
  if (options.trustedTypes) {
    win.trustedTypes = {
      createPolicy: (name: string, rules: { createScriptURL: (url: string) => string }) => {
        policies.push({ name, ...rules });
        return { createScriptURL: (url: string) => ({ trusted: rules.createScriptURL(url) }) };
      },
    };
  }
  return { doc, win: win as unknown as Window, appended, policies, raw: win };
}

describe('loadStripeJs', () => {
  it('inserts Stripe.js once, from js.stripe.com, async and with the page’s nonce, and gives back Stripe', async () => {
    const p = page({ nonce: 'n0nce' });
    const factory = vi.fn();
    const loading = loadStripeJs({ doc: p.doc, win: p.win });
    expect(loadStripeJs({ doc: p.doc, win: p.win })).toBe(loading);
    expect(p.appended).toHaveLength(1);
    const [script] = p.appended;
    expect(script.src).toBe(STRIPE_JS_URL);
    expect(STRIPE_JS_URL).toBe('https://js.stripe.com/v3/');
    expect(script.async).toBe(true);
    expect(script.nonce).toBe('n0nce');
    p.raw.Stripe = factory;
    script.onload?.(new Event('load'));
    await expect(loading).resolves.toBe(factory);
  });

  it('reuses Stripe.js when the page already has it', async () => {
    const p = page();
    const factory = vi.fn();
    p.raw.Stripe = factory;
    await expect(loadStripeJs({ doc: p.doc, win: p.win })).resolves.toBe(factory);
    expect(p.appended).toEqual([]);
  });

  it('creates no Trusted Types policy of its own: the page’s `default` one admits Stripe.js', async () => {
    const p = page({ trustedTypes: true });
    void loadStripeJs({ doc: p.doc, win: p.win }).catch(() => {});
    expect(p.policies).toEqual([]);
    expect(p.appended[0].src).toBe(STRIPE_JS_URL);
  });

  it('a script that fails to load rejects, and the next payment tries again', async () => {
    const p = page();
    const first = loadStripeJs({ doc: p.doc, win: p.win });
    p.appended[0].onerror?.(new Event('error'));
    await expect(first).rejects.toThrow('Stripe.js could not be loaded');
    const second = loadStripeJs({ doc: p.doc, win: p.win });
    expect(second).not.toBe(first);
    expect(p.appended).toHaveLength(2);
    second.catch(() => {});
  });

  it('a script that loads without Stripe rejects', async () => {
    const p = page();
    const loading = loadStripeJs({ doc: p.doc, win: p.win });
    p.appended[0].onload?.(new Event('load'));
    await expect(loading).rejects.toThrow('Stripe.js loaded without Stripe');
  });

  it('never loads inside the apps nor on the account surface: they sell nothing', async () => {
    for (const surface of ['desktop', 'mobile', 'account'] as const) {
      applySurface(surface);
      const p = page();
      await expect(loadStripeJs({ doc: p.doc, win: p.win })).rejects.toThrow('Stripe.js is web only');
      expect(p.appended).toEqual([]);
    }
  });
});
