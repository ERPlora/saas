import type { Page } from '@playwright/test';

/** Collects the page's uncaught errors from now on (the list fills as they happen). */
export function watchPageErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(String(error)));
  return errors;
}

/**
 * The `/api/live` streams a page opens (the operations of each, from `s=`) and the ones that failed. A page declares
 * its live data when it mounts, so its stream opens once; a subscription arriving after the first open makes the SDK
 * reopen it, and the first request ends `ERR_ABORTED`.
 */
export function watchLiveStreams(page: Page): { opened: string[][]; failed: string[] } {
  const opened: string[][] = [];
  const failed: string[] = [];
  const isStream = (url: string) => new URL(url).pathname === '/api/live';
  page.on('request', (request) => {
    if (!isStream(request.url())) return;
    const s = new URL(request.url()).searchParams.get('s') ?? '';
    const list = JSON.parse(Buffer.from(s, 'base64url').toString('utf8')) as { op: string; params: unknown }[];
    opened.push(list.map((sub) => `${sub.op} ${JSON.stringify(sub.params)}`));
  });
  page.on('requestfailed', (request) => {
    if (isStream(request.url())) failed.push(request.failure()?.errorText ?? 'failed');
  });
  return { opened, failed };
}

/** Longer than the SDK's resubscribe debounce (150 ms) and a round trip: a late subscription would reopen by then. */
export const QUIET_MS = 1500;
