// reCAPTCHA Enterprise in the browser, score-based and invisible (Ioan, 2026-10-22: «no se vea en la pantalla»): no
// checkbox, no puzzle. Google's `enterprise.js` watches the page; on submit a form asks it for a token of its own
// action (`grecaptcha.enterprise.execute(siteKey, {action})`) and sends it as `recaptcha_token`; the server asks
// Google about it (live.recaptcha) and refuses a bot, a token of another form or none at all.
//   - Our code inserts the script (CSP `'strict-dynamic'` trusts what a nonced script inserts) with the page's nonce
//     too, for the public web, whose policy names Google's `/recaptcha/` paths instead (public/csp.py). On the SPA,
//     Trusted Types: a script's address is a sink, and the page's `default` policy admits Google's two origins
//     (`createShell({ trustedScriptOrigins })`, frontend/main.ts); Google's script then makes its own `goog#html`
//     policy (CSP `trusted-types`, live.recaptcha.with_recaptcha).
//   - The badge Google paints is hidden, which Google allows only with its notice near the form (the public web's
//     public/partials/recaptcha_notice.html, the SPA's accounts/frontend/components/RecaptchaNotice.vue). The rule
//     that hides it goes in with Google's script (`hideBadge`): reCAPTCHA off (the default since 2026-10-23) emits
//     no CSS of it. Both CSPs admit inline styles (`style-src 'unsafe-inline'`, live.csp and public/csp.py).
//   - A token that cannot be had (Google blocked by an extension, down, slower than `TOKEN_TIMEOUT_MS`) is no token:
//     the form still goes, the server refuses it and says why («We could not check that you are a person»).
// Used by the public web (`protectForms`, frontend/public.ts) and by the SPA's sign-in pages
// (accounts/frontend/recaptcha.ts).

/** Google's loader of reCAPTCHA Enterprise (`?render=<site key>`: score-based, invisible). */
export const RECAPTCHA_SCRIPT = 'https://www.google.com/recaptcha/enterprise.js';
/** How long a form waits for its token before it goes without one. */
export const TOKEN_TIMEOUT_MS = 10_000;
/** The form field the token travels in (the server's `recaptcha_token`). */
export const TOKEN_FIELD = 'recaptcha_token';

/** What the forms use of `grecaptcha.enterprise`. */
export interface RecaptchaEnterprise {
  ready(callback: () => void): void;
  execute(siteKey: string, options: { action: string }): Promise<string>;
}
type RecaptchaWindow = Window & { grecaptcha?: { enterprise?: RecaptchaEnterprise } };

export interface RecaptchaEnv {
  doc?: Document;
  win?: Window;
  timeoutMs?: number;
}

let loading: { siteKey: string; promise: Promise<RecaptchaEnterprise> } | null = null;

/** The rule that hides Google's badge; its notice is under each protected form. */
export const BADGE_STYLE = '.grecaptcha-badge { visibility: hidden; }';

/** Hides Google's badge on `doc`, once: the style goes in with Google's script, never without it. */
function hideBadge(doc: Document): void {
  if (doc.querySelector('style[data-recaptcha-badge]')) return;
  const style = doc.createElement('style');
  style.dataset.recaptchaBadge = '';
  style.textContent = BADGE_STYLE;
  doc.head.append(style);
}

/** `grecaptcha.enterprise` once ready, loading Google's script the first time. A failure rejects (and the next call
 *  tries again). */
export function loadRecaptcha(siteKey: string, { doc = document, win = window }: RecaptchaEnv = {}): Promise<RecaptchaEnterprise> {
  if (loading?.siteKey === siteKey) return loading.promise;
  hideBadge(doc);
  const present = (win as RecaptchaWindow).grecaptcha?.enterprise;
  const attempt = new Promise<RecaptchaEnterprise>((resolve, reject) => {
    if (present) {
      present.ready(() => resolve(present));
      return;
    }
    const script = doc.createElement('script');
    script.async = true;
    const nonce = doc.querySelector<HTMLScriptElement>('script[nonce]')?.nonce;
    if (nonce) script.nonce = nonce;
    script.onload = () => {
      const enterprise = (win as RecaptchaWindow).grecaptcha?.enterprise;
      if (enterprise) enterprise.ready(() => resolve(enterprise));
      else reject(new Error('reCAPTCHA loaded without grecaptcha.enterprise'));
    };
    script.onerror = () => reject(new Error('reCAPTCHA could not be loaded'));
    script.src = `${RECAPTCHA_SCRIPT}?render=${encodeURIComponent(siteKey)}`;
    doc.head.append(script);
  });
  loading = { siteKey, promise: attempt };
  attempt.catch(() => {
    if (loading?.promise === attempt) loading = null;
  });
  return attempt;
}

/** Forgets a load in flight (tests). */
export function resetRecaptcha(): void {
  loading = null;
}

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`reCAPTCHA did not answer in ${ms} ms`)), ms);
    promise.then(
      (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      (error: unknown) => {
        clearTimeout(timer);
        reject(error instanceof Error ? error : new Error(String(error)));
      },
    );
  });
}

/** Google's token of `action`; `undefined` without a site key (reCAPTCHA off) or when it cannot be had in time. */
export async function recaptchaToken(siteKey: string, action: string, env: RecaptchaEnv = {}): Promise<string | undefined> {
  if (!siteKey) return undefined;
  try {
    return await withTimeout(
      loadRecaptcha(siteKey, env).then((enterprise) => enterprise.execute(siteKey, { action })),
      env.timeoutMs ?? TOKEN_TIMEOUT_MS,
    );
  } catch (error) {
    console.error('reCAPTCHA: no token for', action, error);
    return undefined;
  }
}

/** The form's token field, added (hidden) when the template has none. */
function tokenField(form: HTMLFormElement): HTMLInputElement {
  const present = form.querySelector<HTMLInputElement>(`input[name="${TOKEN_FIELD}"]`);
  if (present) return present;
  const field = form.ownerDocument.createElement('input');
  field.type = 'hidden';
  field.name = TOKEN_FIELD;
  form.append(field);
  return field;
}

/**
 * The public web's forms with `data-recaptcha-action` and `data-recaptcha-site-key` (the contact form, the demo):
 * Google's script loads with the page (it scores what it sees), and every submit is held until the form's token is
 * in, then submitted again (`requestSubmit`) for the form's own checks and the post. Each submit asks a fresh token:
 * one lives two minutes and serves once. Listens on the document in the capture phase, before the form's own
 * listeners (the contact form's checks), which see only the second submit. Gives back what stops it (tests).
 */
export function protectForms(doc: Document, env: RecaptchaEnv = {}): () => void {
  const protectedForm = (target: EventTarget | null): HTMLFormElement | null =>
    target instanceof HTMLFormElement && target.dataset.recaptchaAction && target.dataset.recaptchaSiteKey ? target : null;
  const first = doc.querySelector<HTMLFormElement>('form[data-recaptcha-action][data-recaptcha-site-key]');
  if (!first) return () => undefined;
  loadRecaptcha(first.dataset.recaptchaSiteKey ?? '', env).catch((error: unknown) => {
    console.error('reCAPTCHA: the script did not load', error);
  });
  const onSubmit = (event: Event): void => {
      const form = protectedForm(event.target);
      if (!form) return;
      if (form.dataset.recaptchaReady === '1') {
        delete form.dataset.recaptchaReady;
        return;
      }
      event.preventDefault();
      event.stopImmediatePropagation();
      if (form.dataset.recaptchaPending === '1') return;
      form.dataset.recaptchaPending = '1';
      void recaptchaToken(form.dataset.recaptchaSiteKey ?? '', form.dataset.recaptchaAction ?? '', env).then((token) => {
        tokenField(form).value = token ?? '';
        delete form.dataset.recaptchaPending;
        form.dataset.recaptchaReady = '1';
        form.requestSubmit();
      });
  };
  doc.addEventListener('submit', onSubmit, { capture: true });
  return () => doc.removeEventListener('submit', onSubmit, { capture: true });
}
