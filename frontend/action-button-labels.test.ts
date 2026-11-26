// An action button with an icon is the icon: its label is its accessible name and its title, never text beside it.
// Only an action whose icon does not say it alone paints its label, and a datum (a count, an amount, a price) stays
// beside its icon. These read the panel's sources: a DataTable row action that paints its text (`showLabel`) or an
// `ion-button` that paints text beside its icon fails here unless it is listed below with why, and so does an
// exception that is no longer used: the lists only shrink. Every icon-only button carries its name and its title,
// and the common square of `icon-action` unless a toolbar (`ion-buttons`) sizes it.
import { describe, expect, it } from 'vitest';

/** `<file>#<action id>` → why its icon cannot stand alone. */
const LABELLED_ROW_ACTIONS: Record<string, string> = {
  'billing/frontend/components/InvoicesTab.vue#pay': 'a card is also the icon of «Payment method» on the same page',
};

const RETRY = '«Retry» is the rule’s own example of a label no icon replaces';
const SUBMIT = 'the submit of a form or a dialog says its consequence';
const DECISION = 'accepting or declining is the decision the screen asks for, said in words';
const NAVIGATION = 'a link to another screen, not an action';
const DATUM = 'what it shows beside the icon is a datum, not a label';
const OPEN = 'the main action of its screen: the enter arrow does not say which business it opens';

/** `<file>#<data-testid, or the first i18n key>` → why that `ion-button` paints text beside its icon. */
const LABELLED_BUTTONS: Record<string, string> = {
  'accounts/frontend/components/NewKeyModal.vue#new-key-done': SUBMIT,
  'accounts/frontend/components/ProfileForm.vue#profile-save': SUBMIT,
  'accounts/frontend/components/SessionsTable.vue#sessions-close-others': 'its sign-out icon is each row’s «Sign out»',
  'accounts/frontend/components/SignInForm.vue#accounts.login.continueWithGoogle': `${SUBMIT}; the logo names Google, not signing in`,
  'accounts/frontend/components/TwoFactorRow.vue#two-factor-manage': 'the shield names two-step sign-in, not «Set up» or «Manage»',
  'billing/frontend/components/AnnualSwitchDialog.vue#annual-retry': RETRY,
  'billing/frontend/components/BillingProfileCard.vue#profile-retry': RETRY,
  'billing/frontend/components/CheckoutModal.vue#checkout-retry': RETRY,
  'billing/frontend/components/InvoiceFilters.vue#invoices-filters': DATUM,
  'billing/frontend/components/InvoiceFilters.vue#invoices-filters-clear': 'an ✕ inside a popover reads as closing it',
  'billing/frontend/components/InvoicesTab.vue#invoices-csv': 'a second download beside the PDFs, and no icon says Excel',
  'billing/frontend/components/InvoicesTab.vue#invoices-empty-plans': NAVIGATION,
  'billing/frontend/components/InvoicesTab.vue#invoices-pdf-selected': DATUM,
  'billing/frontend/components/InvoicesTab.vue#invoices-show-all': 'an ✕ does not say «Show all»',
  'billing/frontend/components/ModuleCard.vue#module-add': DATUM,
  'billing/frontend/components/ModuleCard.vue#module-cancel': 'an ✕ reads as closing, not as cancelling the module',
  'billing/frontend/components/ModuleCard.vue#module-keep': 'no icon says «Keep · no charge today»',
  'billing/frontend/components/ModuleCard.vue#module-owned': 'a state, not an action',
  'billing/frontend/components/PayInvoiceButton.vue#pay-invoice': DATUM,
  'billing/frontend/components/PaymentTab.vue#payment-retry': RETRY,
  'billing/frontend/components/PlanCard.vue#`plan-${action.kind}`': 'a change of plan says its consequence',
  'billing/frontend/components/PromoCodeField.vue#store-promo-apply': SUBMIT,
  'billing/frontend/components/PromoCodeField.vue#store-promo-toggle': 'a question that opens the field: no icon asks it',
  'billing/frontend/components/ProrationDialog.vue#proration-retry': RETRY,
  'billing/frontend/components/StoreShop.vue#store-retry': RETRY,
  'billing/frontend/components/StoreUnpaidNotice.vue#store-unpaid-billing': NAVIGATION,
  'billing/frontend/components/StoreUnpaidNotice.vue#store-unpaid-pay': 'the card is the notice’s own icon: alone it does not say «Pay»',
  'billing/frontend/components/SubscriptionsTab.vue#subscriptions-empty-plans': NAVIGATION,
  'fiscal/frontend/components/RepresentationCard.vue#representation-manage': 'no icon says «Manage in your business»',
  'frontend/LoadFailed.vue#retryTestid': RETRY,
  'hubs/frontend/components/BusinessCreateForm.vue#create-submit': SUBMIT,
  'hubs/frontend/components/BusinessCreateModal.vue#create-free-limit-store': 'no icon says «Change the plan of …»',
  'hubs/frontend/components/BusinessCreateModal.vue#create-modal-close-list': NAVIGATION,
  'hubs/frontend/components/BusinessCreateModal.vue#create-modal-open': OPEN,
  'hubs/frontend/components/BusinessSettings.vue#settings-save': SUBMIT,
  'hubs/frontend/components/CustomDomainCard.vue#domain-connect': SUBMIT,
  'hubs/frontend/components/DeviceAccessCard.vue#device-android': 'the platform’s name tells the two downloads apart',
  'hubs/frontend/components/DeviceAccessCard.vue#device-windows': 'the platform’s name tells the two downloads apart',
  'hubs/frontend/components/InvitationsAndOffers.vue#invitation-accept': DECISION,
  'hubs/frontend/components/InvitationsAndOffers.vue#invitation-decline': DECISION,
  'hubs/frontend/components/InvitationsAndOffers.vue#offer-accept': DECISION,
  'hubs/frontend/components/InvitationsAndOffers.vue#offer-decline': DECISION,
  'hubs/frontend/components/LaunchBusinesses.vue#launch-open': OPEN,
  'hubs/frontend/components/LaunchInvitation.vue#launch-accept': DECISION,
  'hubs/frontend/components/LaunchInvitation.vue#launch-create-own': `${NAVIGATION}; a «+» alone does not say what it creates`,
  'hubs/frontend/components/LaunchInvitation.vue#launch-decline': DECISION,
  'hubs/frontend/components/MembersTab.vue#members-transfer-cancel': 'an ✕ reads as dismissing the notice, not as withdrawing the offer',
  'hubs/frontend/components/RecoverButton.vue#recover-business': 'as wide as its card it is the card’s main action, said in words; small in a list it is its icon',
  'hubs/frontend/components/UnpaidActions.vue#unpaid-change-card': 'two card icons side by side: «Change card» and «Pay the invoice»',
  'hubs/frontend/components/UnpaidActions.vue#unpaid-pay': 'two card icons side by side: «Change card» and «Pay the invoice»',
  'hubs/frontend/pages/BusinessListPage.vue#businesses-show-all': 'an ✕ does not say «Show all»',
  'hubs/frontend/pages/BusinessPage.vue#business-open': OPEN,
  'hubs/frontend/pages/InvitationPage.vue#invitation-accept': DECISION,
  'hubs/frontend/pages/InvitationPage.vue#invitation-create-own': `${NAVIGATION}; a «+» alone does not say what it creates`,
  'hubs/frontend/pages/InvitationPage.vue#invitation-decline': DECISION,
  'hubs/frontend/pages/InvitationPage.vue#invitation-panel': NAVIGATION,
  'hubs/frontend/pages/LaunchPage.vue#launch-create-another': NAVIGATION,
  'hubs/frontend/pages/LaunchPage.vue#launch-panel': NAVIGATION,
};

const sources = import.meta.glob<string>(['../*/frontend/**/*.{ts,vue}', './**/*.{ts,vue}', '!**/*.test.ts', '!**/__tests__/**'], {
  query: '?raw',
  import: 'default',
  eager: true,
});

const panelFiles = () =>
  Object.entries(sources).map(([path, source]) => ({ file: path.replace(/^\.\.\//, '').replace(/^\.\//, 'frontend/'), source }));

/** Each `showLabel:` of the panel's sources, as `<file>#<id>` with the nearest `id: '…'` before it. */
function labelledRowActions(): string[] {
  return panelFiles().flatMap(({ file, source }) =>
    [...source.matchAll(/\bshowLabel\s*:/g)].map((match) => {
      const id = [...source.slice(0, match.index).matchAll(/\bid:\s*'([^']+)'/g)].at(-1)?.[1] ?? '?';
      return `${file}#${id}`;
    }),
  );
}

interface IconButton {
  file: string;
  /** The opening tag's attributes. */
  attributes: string;
  /** What it paints besides its tags: empty for an icon-only button. */
  text: string;
  /** Its `data-testid` (bound or not), or the first i18n key it paints. */
  id: string;
  /** Inside an `ion-buttons` toolbar slot, which sizes its buttons. */
  inToolbar: boolean;
}

/** Every `ion-button` of the panel's components that holds an icon. */
function iconButtons(): IconButton[] {
  return panelFiles()
    .filter(({ file }) => file.endsWith('.vue'))
    .flatMap(({ file, source }) =>
      [...source.matchAll(/<ion-button\b([^>]*)>([\s\S]*?)<\/ion-button>/g)]
        .filter((match) => /<(?:HubIcon|ion-icon)\b/.test(match[2]))
        .map((match) => {
          const before = source.slice(0, match.index);
          return {
            file,
            attributes: match[1],
            text: match[2].replace(/<[^>]*>/g, '').trim(),
            id: /\bdata-testid="([^"]+)"/.exec(match[1])?.[1] ?? /\$t\('([^']+)'/.exec(match[2])?.[1] ?? '?',
            inToolbar: before.lastIndexOf('<ion-buttons') > before.lastIndexOf('</ion-buttons>'),
          };
        }),
    );
}

describe('action buttons of the panel', () => {
  it('row actions paint their text (`showLabel`) only where the icon does not say it alone', () => {
    expect(Object.keys(sources).length).toBeGreaterThan(50);
    expect(labelledRowActions().sort()).toEqual(Object.keys(LABELLED_ROW_ACTIONS).sort());
  });

  it('paint text beside their icon only where the icon does not say it alone, or the text is a datum', () => {
    const labelled = iconButtons().filter((button) => button.text !== '');
    expect(labelled.length).toBeGreaterThan(20);
    expect([...new Set(labelled.map(({ file, id }) => `${file}#${id}`))].sort()).toEqual(Object.keys(LABELLED_BUTTONS).sort());
  });

  it('that are only their icon carry its name and its title, and the common square outside a toolbar', () => {
    const iconOnly = iconButtons().filter((button) => button.text === '');
    expect(iconOnly.length).toBeGreaterThan(5);
    const unnamed = iconOnly.filter(({ attributes }) => !/[\s:]aria-label=/.test(attributes) || !/[\s:]title=/.test(attributes));
    const unsized = iconOnly.filter(({ attributes, inToolbar }) => !inToolbar && !/\bicon-action\b/.test(attributes));
    expect(unnamed.map(({ file, id }) => `${file}#${id}`)).toEqual([]);
    expect(unsized.map(({ file, id }) => `${file}#${id}`)).toEqual([]);
  });
});
