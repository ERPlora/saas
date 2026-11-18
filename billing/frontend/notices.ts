// The unpaid invoices as notices of the action center, the one place the panel says them: one per business with a
// payment pending or suspended (`unpaid.ts`). Only its payer gets the buttons, and only on the web: inside the apps
// nothing is paid. After a declined card the server refuses «Pay» until the card changes, so «Change card» is the
// only way out.
import { type ActionNotice, type ActionNoticeSource, type NoticeAction, type Surface, useSurface } from '@erplora/ui/shell';
import { useLiveClient } from '@erplora/ui/sdk';
import { computed, onScopeDispose, type Ref, shallowRef } from 'vue';
import { useI18n } from 'vue-i18n';

import type { InvoiceRowOut } from '../../frontend/sdk-types';
import { formatDate } from './format';
import { formatAmount, graceEnd } from './invoices';
import { usePayInvoice } from './pay';
import { useCardPortal } from './portal';
import { type UnpaidItem, useUnpaidInvoices } from './unpaid';

const DAY_MS = 24 * 60 * 60 * 1000;
/** The days left change once a day: a minute is close enough. */
const CLOCK_TICK_MS = 60_000;

interface Context {
  readonly t: ReturnType<typeof useI18n>['t'];
  readonly locale: string;
  readonly now: number;
  readonly surface: Surface;
  readonly pay: (invoice: InvoiceRowOut) => Promise<boolean>;
  readonly changeCard: (hubId: string) => Promise<boolean>;
}

interface Case extends UnpaidItem {
  /** The account pays the business: its invoice says so, or without it the business. */
  readonly payer: boolean;
  readonly declined: boolean;
  /** When the grace ends; `''` without the day it went unpaid. */
  readonly deadline: string;
}

function caseOf(item: UnpaidItem): Case {
  const { business, invoice } = item;
  const payer = invoice ? invoice.pay_blocked_reason !== 'payer_required' : business.is_payer || business.pay_url !== null;
  const declined = business.unpaid_reason === 'card_declined' || invoice?.pay_blocked_reason === 'card_change_required';
  return { ...item, payer, declined: payer && declined, deadline: graceEnd(business.unpaid_since) };
}

function chip(c: Case, ctx: Context): string | undefined {
  if (c.business.status === 'suspended') return ctx.t('billing.notice.suspended');
  if (!c.deadline) return undefined;
  const days = Math.ceil((Date.parse(c.deadline) - ctx.now) / DAY_MS);
  return days > 1 ? ctx.t('billing.notice.daysLeft', { count: days }) : ctx.t('billing.notice.lastDay');
}

function lead(c: Case, ctx: Context): string | undefined {
  if (!c.payer) return undefined;
  if (c.declined) return ctx.t('billing.notice.declined');
  return c.business.unpaid_reason === 'card_changed' ? ctx.t('billing.notice.cardChanged') : undefined;
}

function consequence(c: Case, ctx: Context): string {
  if (c.business.status === 'suspended') return ctx.t('billing.notice.suspendedBody');
  if (!c.deadline) return ctx.t('billing.notice.pastDueBodyNoDate');
  return ctx.t('billing.notice.pastDueBody', { until: formatDate(c.deadline, ctx.locale) });
}

/** Why there is no button, when there is none. */
function tail(c: Case, ctx: Context): string | undefined {
  if (!c.payer) return ctx.t('billing.notice.payerRequired');
  if (ctx.surface === 'web') return undefined;
  if (ctx.surface === 'account') return ctx.t('billing.notice.account');
  return ctx.t(c.declined ? 'billing.notice.appDeclined' : 'billing.notice.app');
}

const amountOf = (invoice: InvoiceRowOut, locale: string) => formatAmount(invoice.total_cents, invoice.currency, locale);

/** The primary first. */
function actions(c: Case, ctx: Context): NoticeAction[] {
  if (!c.payer || ctx.surface !== 'web') return [];
  const changeCard = { label: ctx.t('billing.notice.changeCard'), run: () => ctx.changeCard(c.business.id) };
  const invoice = c.invoice;
  if (c.declined || c.business.pay_url === null || !invoice?.can.pay) return [changeCard];
  const pay = { label: ctx.t('billing.notice.pay', { amount: amountOf(invoice, ctx.locale) }), run: () => ctx.pay(invoice) };
  return [pay, changeCard];
}

function unpaidNotice(c: Case, ctx: Context): ActionNotice {
  const title = ctx.t('billing.notice.title', { name: c.business.name });
  const [action, secondary] = actions(c, ctx);
  return {
    id: `billing.unpaid:${c.business.id}`,
    severity: 'danger',
    icon: 'ion:card-outline',
    label: title,
    title,
    body: [lead(c, ctx), consequence(c, ctx), tail(c, ctx)].filter(Boolean).join(' '),
    figure: c.invoice ? amountOf(c.invoice, ctx.locale) : undefined,
    chip: chip(c, ctx),
    due: c.deadline ? { from: c.business.unpaid_since ?? undefined, at: c.deadline } : undefined,
    action,
    secondary,
  };
}

/** The time of day, read again every minute on the live client's timers. */
function useClock(): Readonly<Ref<number>> {
  const client = useLiveClient();
  const now = shallowRef(Date.now());
  const tick = (): void => {
    now.value = Date.now();
    cancel = client.schedule(tick, CLOCK_TICK_MS);
  };
  let cancel = client.schedule(tick, CLOCK_TICK_MS);
  onScopeDispose(() => cancel());
  return now;
}

export function useUnpaidNotices(): ActionNoticeSource {
  const { t, locale } = useI18n();
  const { surface } = useSurface();
  const { items, state } = useUnpaidInvoices();
  const { pay } = usePayInvoice();
  const portal = useCardPortal();
  const now = useClock();
  const notices = computed(() => {
    const ctx: Context = { t, locale: locale.value, now: now.value, surface: surface.value, pay, changeCard: portal.open };
    return items.value?.map((item) => unpaidNotice(caseOf(item), ctx));
  });
  return { notices, failed: state.failed, retry: state.retry };
}
