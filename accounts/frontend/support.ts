// The support address of the SPA's «Contact Support» (PUBLIC-F18): base/spa.py embeds `SUPPORT_EMAIL` as the JSON
// block `support-email`, beside `spa-config`; the public web's footer and contact page write the same one.

export const SUPPORT_EMAIL_ID = 'support-email';

/** `mailto:` the support address, or `undefined` when the page carries none (never an address typed here). */
export function supportMailto(doc: Document = document): string | undefined {
  const text = doc.getElementById(SUPPORT_EMAIL_ID)?.textContent;
  if (!text) return undefined;
  try {
    const email: unknown = JSON.parse(text);
    return typeof email === 'string' && email.includes('@') ? `mailto:${email}` : undefined;
  } catch {
    return undefined;
  }
}
