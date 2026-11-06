// The report of an answer of the panel's assistant (ASSISTANT-F23, F25; saas#287, ui#103), in a browser against the
// panel's own Django, with the e2e's own model and its web search on (assistant-provider.ts; panel/project.ts gives the
// search a made-up key): «Report a problem» under an answer says whether its turn brought pages of the web — also when
// the turn went on with a tool of the panel after the search, whose round brought none —, and support gets the answer
// only when it did not (Brave's terms do not let a mailbox keep its results). After a reload of the tab each answer
// still says it. The dialog at 390, 834 and 1440 (screenshots under `.artifacts/panel/`).
// flow: ASSISTANT-F23 — the report of an answer reaches support, without its text when it may quote the web.
import { readMails } from '@erplora/ui/testing/mail';
import type { Locator, Page } from '@playwright/test';

import { STACK } from '../stack';

import { ask, DESKTOP_FIRST, localAssistant, openPanel } from './assistant-chat';
import { djangoPrintWarm, expect, settled, shot, sidewaysScroll, test, toast, waitForMail, watchPageErrors } from './fixtures';
import { PANEL_MAIL_DIR } from './project';

/** What support gets instead of an answer that may quote the web (assistant/services.py, `REPORT_WEB_ANSWER`). */
const LEFT_OUT = 'Left out: it may quote web search results';
const SEARCHED = '¿Qué dice la nueva ley de mis negocios?';
const SEARCHED_ANSWER = 'Tienes 1 negocio';
const GREETING = 'Hola';
const GREETING_ANSWER = 'Hola, soy el asistente de prueba.';
/** The thank-you of a report that was sent. */
const THANKS = 'Gracias, hemos recibido tu denuncia.';

const { seed } = localAssistant(STACK.aiProviderPort);

/** Support's address (`SUPPORT_EMAIL`), read once, by the warm Django `localAssistant` started: on no test's clock. */
let support = '';

test.beforeAll(async () => {
  support = await djangoPrintWarm('from django.conf import settings\nprint(settings.SUPPORT_EMAIL)');
});

/** Reports `answer` («It is wrong») and gives back what the chat sent. */
async function report(page: Page, answer: Locator): Promise<{ message_id: string; answer: string; web?: unknown }> {
  await answer.getByTestId('assistant-report').click();
  await expect(page.getByTestId('assistant-report-dialog-submit')).toBeVisible();
  // No thank-you of a report before still on screen (2.6 s, shell/toast.ts): the one that shows next is this report's.
  await expect(toast(page, THANKS)).toHaveCount(0);
  const request = page.waitForRequest(
    (sent) => sent.method() === 'POST' && new URL(sent.url()).pathname.endsWith('/assistant/report'),
  );
  await page.getByTestId('assistant-report-dialog-submit').click();
  const body = (await request).postDataJSON() as { message_id: string; answer: string; web?: unknown };
  await expect(toast(page, THANKS)).toBeVisible();
  await expect(page.getByTestId('assistant-report-dialog-submit')).toBeHidden();
  return body;
}

/** The mail support got of the report of `id`. */
async function mailOf(support: string, since: number, id: string): Promise<string> {
  await waitForMail(support, since, new RegExp(`^Message: (${id})$`, 'm'));
  return readMails(PANEL_MAIL_DIR).find((mail) => mail.body.includes(`Message: ${id}`))?.body ?? '';
}

test('a reported answer reaches support with its text only when its turn brought no pages of the web, also after a reload', async ({
  page,
}) => {
  await seed('panel', 'es');
  const errors = watchPageErrors(page);
  const panel = await openPanel(page);
  // Each answer's row: its bubble and, under it, «Report a problem».
  const answers = panel.getByTestId('assistant-answer');

  // Searched the web, then read the businesses: the round after the search brought no pages, the answer still may.
  await ask(page, SEARCHED);
  await expect(answers.last()).toContainText(SEARCHED_ANSWER);
  await ask(page, GREETING);
  await expect(answers.last()).toContainText(GREETING_ANSWER);
  // Over: a reload in the middle of a turn would leave it cut.
  await expect(page.getByTestId('assistant-stop')).toHaveCount(0);

  // The conversation lives in the tab: after a reload the panel comes back with both answers.
  await page.reload();
  await expect(panel).toHaveAttribute('data-open', 'true');
  await expect(answers).toHaveCount(2);
  await expect(panel.getByTestId('assistant-failure')).toHaveCount(0);

  const since = Date.now();
  const searched = await report(page, answers.first());
  expect(searched.answer).toContain(SEARCHED_ANSWER);
  expect(searched.web).toBe(true);
  const greeted = await report(page, answers.last());
  expect(greeted.answer).toBe(GREETING_ANSWER);
  expect(greeted.web).toBe(false);

  const fromTheWeb = await mailOf(support, since, searched.message_id);
  expect(fromTheWeb).toContain(LEFT_OUT);
  expect(fromTheWeb).not.toContain(SEARCHED_ANSWER);
  const notFromTheWeb = await mailOf(support, since, greeted.message_id);
  expect(notFromTheWeb).toContain(GREETING_ANSWER);
  expect(notFromTheWeb).not.toContain(LEFT_OUT);

  // The dialog, at every size, once the thank-you of the last report is gone: nothing scrolls sideways.
  await expect(toast(page, THANKS)).toHaveCount(0);
  await answers.last().getByTestId('assistant-report').click();
  const dialog = page.getByTestId('assistant-report-dialog');
  for (const size of DESKTOP_FIRST) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await expect(page.getByTestId('assistant-report-dialog-submit')).toBeVisible();
    await expect.poll(() => sidewaysScroll(page), `${size.width}: nothing scrolls sideways`).toEqual([]);
    await settled(page);
    await page.screenshot({ path: shot(`assistant-report-${size.width}`) });
  }
  await expect(dialog).toContainText('Denunciar esta respuesta');
  expect(errors).toEqual([]);
});
