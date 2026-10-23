// reCAPTCHA Enterprise in the browser, score-based and invisible (Ioan, 2026-10-22: no checkbox, no puzzle): Google's
// enterprise.js, inserted by our code with the page's nonce, and a token per form's action; the server asks Google
// about it (live.recaptcha). The public web's forms say which action they are (`data-recaptcha-action`) and get the
// token in `recaptcha_token` before their own checks run. A token that cannot be had (Google blocked, slow) leaves
// the field empty: the server refuses it and says why.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { loadRecaptcha, protectForms, RECAPTCHA_SCRIPT, recaptchaToken, resetRecaptcha } from './recaptcha';

type Enterprise = { ready: (callback: () => void) => void; execute: ReturnType<typeof vi.fn> };

/** A page as the loader sees it: its nonced script, its head (the scripts and the styles put in it), and Google's
 *  `grecaptcha` once its script loads. */
function page(options: { nonce?: string; loads?: boolean; execute?: Enterprise['execute'] } = {}) {
  const appended: HTMLScriptElement[] = [];
  const styles: HTMLStyleElement[] = [];
  const nonced = document.createElement('script');
  if (options.nonce) nonced.nonce = options.nonce;
  const win: { grecaptcha?: { enterprise?: Enterprise } } = {};
  const execute = options.execute ?? vi.fn(async (_key: string, { action }: { action: string }) => `token-for-${action}`);
  const doc = {
    createElement: (tag: string) => document.createElement(tag),
    querySelector: (selector: string) => {
      if (selector === 'script[nonce]') return options.nonce ? nonced : null;
      if (selector === 'style[data-recaptcha-badge]') return styles[0] ?? null;
      return null;
    },
    head: {
      append: (el: HTMLScriptElement | HTMLStyleElement) => {
        if (el instanceof HTMLStyleElement) {
          styles.push(el);
          return;
        }
        appended.push(el);
        if (options.loads === false) return;
        queueMicrotask(() => {
          win.grecaptcha = { enterprise: { ready: (callback) => callback(), execute } };
          el.onload?.(new Event('load'));
        });
      },
    },
  } as unknown as Document;
  return { doc, win: win as unknown as Window, appended, styles, execute, raw: win };
}

beforeEach(() => {
  vi.spyOn(console, 'error').mockImplementation(() => undefined);
});

let stop: (() => void) | undefined;

afterEach(() => {
  stop?.();
  stop = undefined;
  resetRecaptcha();
  vi.restoreAllMocks();
  vi.useRealTimers();
  document.body.innerHTML = '';
});

describe('loadRecaptcha', () => {
  it('inserts enterprise.js once, from Google, with the site key, async and with the page’s nonce', async () => {
    const p = page({ nonce: 'n0nce' });

    const first = loadRecaptcha('site-key', { doc: p.doc, win: p.win });
    const second = loadRecaptcha('site-key', { doc: p.doc, win: p.win });

    const enterprise = await first;
    expect(enterprise).toBe(p.raw.grecaptcha?.enterprise);
    expect(second).toBe(first);
    expect(p.appended).toHaveLength(1);
    const [script] = p.appended;
    expect(script.src).toBe(`${RECAPTCHA_SCRIPT}?render=site-key`);
    expect(RECAPTCHA_SCRIPT).toBe('https://www.google.com/recaptcha/enterprise.js');
    expect(script.async).toBe(true);
    expect(script.nonce).toBe('n0nce');
  });

  it('uses a grecaptcha already on the page without inserting a second script', async () => {
    const p = page();
    const ready = vi.fn((callback: () => void) => callback());
    p.raw.grecaptcha = { enterprise: { ready, execute: vi.fn() } };

    await expect(loadRecaptcha('site-key', { doc: p.doc, win: p.win })).resolves.toBe(p.raw.grecaptcha.enterprise);
    expect(p.appended).toEqual([]);
    expect(ready).toHaveBeenCalledOnce();
  });

  it('hides Google’s badge as its script goes in, with one style and never a second one', async () => {
    // Google's terms allow the badge hidden only with its notice near the form (RecaptchaNotice.vue,
    // public/partials/recaptcha_notice.html). No style without the script: reCAPTCHA off emits no CSS of it.
    const p = page({ loads: false });

    void loadRecaptcha('site-key', { doc: p.doc, win: p.win }).catch(() => undefined);
    resetRecaptcha();
    void loadRecaptcha('site-key', { doc: p.doc, win: p.win }).catch(() => undefined);

    expect(p.appended).toHaveLength(2);
    expect(p.styles.map((style) => [style.dataset.recaptchaBadge, style.textContent])).toEqual([
      ['', '.grecaptcha-badge { visibility: hidden; }'],
    ]);
  });

  it('rejects when the script fails, and tries again next time', async () => {
    const p = page({ loads: false });

    const first = loadRecaptcha('site-key', { doc: p.doc, win: p.win });
    p.appended[0].onerror?.(new Event('error'));

    await expect(first).rejects.toThrow('reCAPTCHA could not be loaded');
    loadRecaptcha('site-key', { doc: p.doc, win: p.win }).catch(() => undefined);
    expect(p.appended).toHaveLength(2);
  });
});

describe('recaptchaToken', () => {
  it('asks Google for a token of the action', async () => {
    const p = page();

    await expect(recaptchaToken('site-key', 'login', { doc: p.doc, win: p.win })).resolves.toBe('token-for-login');
    expect(p.execute).toHaveBeenCalledWith('site-key', { action: 'login' });
  });

  it('without a site key (reCAPTCHA off) asks nothing and gives nothing', async () => {
    const p = page();

    await expect(recaptchaToken('', 'login', { doc: p.doc, win: p.win })).resolves.toBeUndefined();
    expect(p.appended).toEqual([]);
    expect(p.styles).toEqual([]);
  });

  it('gives nothing when Google fails, and says so in the console', async () => {
    const p = page({ execute: vi.fn(async () => Promise.reject(new Error('Invalid site key'))) });

    await expect(recaptchaToken('site-key', 'login', { doc: p.doc, win: p.win })).resolves.toBeUndefined();
    expect(console.error).toHaveBeenCalled();
  });

  it('gives nothing when Google does not answer in time', async () => {
    vi.useFakeTimers();
    const p = page({ loads: false });

    const token = recaptchaToken('site-key', 'login', { doc: p.doc, win: p.win, timeoutMs: 1000 });
    await vi.advanceTimersByTimeAsync(1000);

    await expect(token).resolves.toBeUndefined();
  });
});

describe('protectForms: the public web’s forms', () => {
  function form(action = 'contact') {
    document.body.innerHTML = `
      <form id="f" method="post" action="/contact/submit/" data-recaptcha-action="${action}" data-recaptcha-site-key="site-key">
        <input type="hidden" name="recaptcha_token" value="">
        <button type="submit">Send</button>
      </form>`;
    const el = document.getElementById('f') as HTMLFormElement;
    const requestSubmit = vi.spyOn(el, 'requestSubmit').mockImplementation(() => undefined);
    const token = () => (el.querySelector('input[name="recaptcha_token"]') as HTMLInputElement).value;
    return { el, requestSubmit, token };
  }

  function submit(el: HTMLFormElement): Event {
    const event = new Event('submit', { bubbles: true, cancelable: true });
    el.dispatchEvent(event);
    return event;
  }

  it('loads Google’s script as the page opens, for the score', () => {
    form();
    const p = page();

    stop = protectForms(document, { doc: p.doc, win: p.win });

    expect(p.appended).toHaveLength(1);
  });

  it('holds the first submit, fills the token of the form’s action, then submits again', async () => {
    const { el, requestSubmit, token } = form('demo_request');
    const p = page();
    const own = vi.fn();
    el.addEventListener('submit', own);
    stop = protectForms(document, { doc: p.doc, win: p.win });

    const first = submit(el);
    expect(first.defaultPrevented).toBe(true);
    expect(own).not.toHaveBeenCalled();
    await vi.waitFor(() => expect(requestSubmit).toHaveBeenCalledOnce());
    expect(token()).toBe('token-for-demo_request');

    const second = submit(el);
    expect(second.defaultPrevented).toBe(false);
    expect(own).toHaveBeenCalledOnce();
  });

  it('asks for a fresh token at the next submit (a token lives two minutes and is used once)', async () => {
    const { el, requestSubmit } = form();
    const p = page();
    stop = protectForms(document, { doc: p.doc, win: p.win });

    submit(el);
    await vi.waitFor(() => expect(requestSubmit).toHaveBeenCalledTimes(1));
    submit(el);
    submit(el);
    await vi.waitFor(() => expect(requestSubmit).toHaveBeenCalledTimes(2));

    expect(p.execute).toHaveBeenCalledTimes(2);
  });

  it('a second press while Google is asked does not ask twice', async () => {
    const { el, requestSubmit } = form();
    const p = page();
    stop = protectForms(document, { doc: p.doc, win: p.win });

    submit(el);
    const again = submit(el);
    await vi.waitFor(() => expect(requestSubmit).toHaveBeenCalledOnce());

    expect(again.defaultPrevented).toBe(true);
    expect(p.execute).toHaveBeenCalledOnce();
  });

  it('without a token the form still goes, empty, for the server to refuse and say why', async () => {
    const { el, requestSubmit, token } = form();
    const p = page({ execute: vi.fn(async () => Promise.reject(new Error('blocked'))) });
    stop = protectForms(document, { doc: p.doc, win: p.win });

    submit(el);

    await vi.waitFor(() => expect(requestSubmit).toHaveBeenCalledOnce());
    expect(token()).toBe('');
  });

  it('adds the token field when the form has none', async () => {
    const { el, requestSubmit } = form();
    el.querySelector('input[name="recaptcha_token"]')?.remove();
    const p = page();
    stop = protectForms(document, { doc: p.doc, win: p.win });

    submit(el);

    await vi.waitFor(() => expect(requestSubmit).toHaveBeenCalledOnce());
    const field = el.querySelector('input[name="recaptcha_token"]') as HTMLInputElement;
    expect([field.type, field.value]).toEqual(['hidden', 'token-for-contact']);
  });

  it('leaves alone a page without a protected form, and the forms that are not', () => {
    document.body.innerHTML = '<form id="g" method="get" action="/store/"><button type="submit">Go</button></form>';
    const p = page();
    stop = protectForms(document, { doc: p.doc, win: p.win });

    const event = submit(document.getElementById('g') as HTMLFormElement);

    expect(event.defaultPrevented).toBe(false);
    expect(p.appended).toEqual([]);
    expect(p.styles).toEqual([]);
  });
});
