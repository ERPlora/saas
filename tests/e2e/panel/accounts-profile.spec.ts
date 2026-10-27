// The flows of «the profile, the preferences, the user menu, downloading the data and deleting the account»
// (accounts/WORKBOOK.md, MIGRATION-TASK APP-ACCOUNTS-3) on their screens, at the three sizes of the migration
// (390×844, 834×1112, 1440×900), against the real hubs and billing (no mocks): the business is created by its
// operation, ERPlora's invoice is a row billing reads. Each test names its flow by its registry key; in
// accounts/WORKBOOK.md: G108=F21, G114=F22, G115=F23, G127=F24, G128=F25, G111=F26, G112=F27, G35=F13.
// Accounts of this spec: `e2e-acc3-…@example.com`, removed before and after.
import { readFile } from "node:fs/promises";

import { type Page } from "@playwright/test";

import {
  djangoPrint,
  expect,
  settled,
  shot,
  sidewaysScroll,
  signIn,
  test,
  watchPageErrors,
} from "./fixtures";

const PREFIX = "e2e-acc3-";
const PASSWORD = "Centeno-y-masa-madre-26";
const SIZES = [
  { name: "390", width: 390, height: 844 },
  { name: "834", width: 834, height: 1112 },
  { name: "1440", width: 1440, height: 900 },
] as const;

/** A fresh address of this spec, never used before. */
const address = (name: string) => `${PREFIX}${name}-${Date.now()}@example.com`;

function removeAccounts(): void {
  djangoPrint(
    [
      "from django.contrib.auth import get_user_model",
      "from hubs.models import Hub",
      `Hub.objects.filter(members__user__email__startswith="${PREFIX}").delete()`,
      `get_user_model().objects.filter(email__startswith="${PREFIX}", email__endswith="@example.com").delete()`,
    ].join("\n"),
  );
}

/** An account with its address proven, as one that signed in before; `staff` makes it a platform administrator. */
function createAccount(
  email: string,
  options: { staff?: boolean; firstName?: string } = {},
): { email: string; password: string } {
  djangoPrint(
    [
      "from allauth.account.models import EmailAddress",
      "from django.contrib.auth import get_user_model",
      `user = get_user_model().objects.${options.staff ? "create_superuser" : "create_user"}(email="${email}", password="${PASSWORD}", first_name="${options.firstName ?? "Ana"}", last_name="García", language="en")`,
      "EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)",
    ].join("\n"),
  );
  return { email, password: PASSWORD };
}

/** A business of `email` made by its operation, with one ERPlora invoice it paid, numbered `sequence`. */
function businessWithInvoice(
  email: string,
  name: string,
  sequence: number,
): void {
  djangoPrint(
    [
      "from datetime import date",
      "from django.contrib.auth import get_user_model",
      "from django.utils import timezone",
      "from billing.models import Invoice, InvoiceLine",
      "from hubs.models import Hub",
      "from hubs.tests.conftest import create_business",
      `user = get_user_model().objects.get(email="${email}")`,
      `hub = create_business(user, name="${name}")`,
      `invoice = Invoice.objects.create(stripe_invoice_id=f"in_{hub.slug}_${sequence}", hub=hub, business_name=hub.name,` +
        ` billing_profile=hub.billing_profile, payer_account=user, payment_status="paid", series="ERP", sequence=${sequence},` +
        ` number="ERP-2026-0${sequence}", issued_on=date(2026, 9, 1), billed_at=timezone.now(), net_cents=2999,` +
        ' tax_cents=630, total_cents=3629, tax_country="ES", fiscal_status="accepted", payer_name=hub.name, payer_country="ES")',
      'InvoiceLine.objects.create(invoice=invoice, position=1, description="1 × Starter", item_kind="plan",' +
        ' item_slug="starter", net_cents=2999, tax_cents=630, total_cents=3629)',
    ].join("\n"),
  );
}

/** The value Django reads back for `expression` of the account `email` (`user`), printed. */
const readBack = (email: string, expression: string) =>
  djangoPrint(
    [
      "from django.contrib.auth import get_user_model",
      `user = get_user_model().objects.filter(email="${email}").first()`,
      `print(${expression})`,
    ].join("\n"),
  ).trim();

/** Each size of the migration: the page as `ready` leaves it, no sideways scroll, and its full-page shot; `after`
 *  undoes what `ready` opened (a menu) before the next size. */
async function atEverySize(
  page: Page,
  key: string,
  ready: () => Promise<void>,
  after?: () => Promise<void>,
): Promise<void> {
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await ready();
    await settled(page);
    expect(
      await sidewaysScroll(page),
      `${key} scrolls sideways at ${size.name}`,
    ).toEqual([]);
    await page.screenshot({
      path: shot(`APP-ACCOUNTS-3-${key}-${size.name}`),
      fullPage: true,
    });
    await after?.();
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}

/** The user menu (`UserMenuPopover`): in the side menu, a drawer behind the topbar's menu button below `lg`. */
async function openUserMenu(page: Page): Promise<void> {
  const trigger = page.getByTestId("user-menu-trigger");
  await expect(trigger).toBeAttached();
  await settled(page);
  if (!(await trigger.isVisible())) {
    await page
      .locator(
        "ion-router-outlet > .ion-page:not(.ion-page-hidden) ion-menu-button",
      )
      .last()
      .click();
    await expect(trigger).toBeVisible();
  }
  const presented = page.evaluate(
    () =>
      new Promise<void>((resolve) =>
        document.addEventListener("ionPopoverDidPresent", () => resolve(), {
          once: true,
        }),
      ),
  );
  await trigger.click();
  await presented;
  await expect(page.getByTestId("user-menu-logout")).toBeVisible();
}

/** Closes whatever the user menu left open (the popover, the side menu on a phone). */
async function closeUserMenu(page: Page): Promise<void> {
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("user-menu-logout")).toBeHidden();
  await page.evaluate(async () => {
    const menu = document.querySelector("ion-menu") as
      (HTMLElement & { close?: () => Promise<boolean> }) | null;
    await menu?.close?.();
  });
}

const toast = (page: Page, text: string) =>
  page.locator("ion-toast").filter({ hasText: text });

test.beforeAll(removeAccounts);
test.afterAll(removeAccounts);

test("ACCOUNTS-G108 (F21): Profile shows the account and keeps the names after a reload", async ({
  page,
}) => {
  const errors = watchPageErrors(page);
  const account = createAccount(address("profile"));
  await signIn(page.request, account);

  await page.goto("/dashboard/account/profile");
  await expect(page.getByTestId("profile-email")).toContainText(account.email);
  await page.getByTestId("profile-first-name").locator("input").fill("Lucía");
  await page.getByTestId("profile-last-name").locator("input").fill("Martín");
  await page.getByTestId("profile-save").click();
  await expect(toast(page, "Changes saved")).toBeVisible();
  await page.reload();
  await expect(
    page.getByTestId("profile-first-name").locator("input"),
  ).toHaveValue("Lucía");
  expect(readBack(account.email, "user.get_full_name()")).toBe("Lucía Martín");
  await atEverySize(page, "G108", async () => {
    await expect(page.getByTestId("profile-card")).toBeVisible();
  });
  expect(errors).toEqual([]);
});

test("ACCOUNTS-G114 (F22): Preferences saves the appearance and the language on their own, kept after a reload", async ({
  page,
}) => {
  const errors = watchPageErrors(page);
  const account = createAccount(address("preferences"));
  await signIn(page.request, account);

  await page.goto("/dashboard/account/preferences");
  await page
    .getByTestId("preferences-theme")
    .locator("ion-segment-button", { hasText: "Dark" })
    .click();
  await expect(page.locator("html")).toHaveClass(/ion-palette-dark/);
  await expect(toast(page, "Preferences saved")).toBeVisible();
  await page.getByTestId("preferences-language").click();
  await page.locator("ion-popover ion-radio", { hasText: "Español" }).click();
  await expect(toast(page, "Preferencias guardadas")).toBeVisible();
  await page.reload();
  await expect(page.getByTestId("preferences-appearance")).toContainText(
    "Apariencia",
  );
  await expect(page.locator("html")).toHaveClass(/ion-palette-dark/);
  expect(
    readBack(account.email, "user.language, user.preferences.theme_mode"),
  ).toBe("es dark");
  await atEverySize(page, "G114", async () => {
    await expect(page.getByTestId("preferences-language-card")).toBeVisible();
  });
  expect(errors).toEqual([]);
});

test("ACCOUNTS-G115 (F23): «Business notices» is the one switch, kept after a reload; the mails that always go say so", async ({
  page,
}) => {
  const errors = watchPageErrors(page);
  const account = createAccount(address("notices"));
  await signIn(page.request, account);

  await page.goto("/dashboard/account/preferences");
  const mails = page.getByTestId("preferences-mails");
  await expect(mails).toContainText("Security, invoices and payments");
  await expect(mails).toContainText(
    "Always on: sign-in codes, security notices, invoices, payments and anything that needs you to act.",
  );
  await expect(mails.locator("ion-toggle")).toHaveCount(2);
  await expect(page.getByTestId("preferences-invoices")).toHaveJSProperty(
    "disabled",
    true,
  );
  await expect(page.getByTestId("preferences-hub-alerts")).toHaveJSProperty(
    "checked",
    true,
  );
  await page.getByTestId("preferences-hub-alerts").click();
  await expect(toast(page, "Preferences saved")).toBeVisible();
  await page.reload();
  await expect(page.getByTestId("preferences-hub-alerts")).toHaveJSProperty(
    "checked",
    false,
  );
  expect(readBack(account.email, "user.preferences.hub_alerts")).toBe("False");
  await atEverySize(page, "G115", async () => {
    await mails.scrollIntoViewIfNeeded();
    await expect(mails).toBeVisible();
    // Every title and hint of the switches reads whole: wrapped, never cut with «…» (Ionic's label is one line).
    const cut = await mails
      .locator(".toggle-title, .toggle-hint")
      .evaluateAll((spans) =>
        spans
          .filter(
            (span) =>
              span.scrollWidth > span.clientWidth + 1 ||
              span.getBoundingClientRect().right >
                span.closest("ion-item")!.getBoundingClientRect().right + 1,
          )
          .map((span) => span.textContent),
      );
    expect(cut).toEqual([]);
  });
  expect(errors).toEqual([]);
});

test("ACCOUNTS-G127 (F24): the theme of the user menu is painted at once and kept in the account", async ({
  page,
}) => {
  const errors = watchPageErrors(page);
  const account = createAccount(address("theme"));
  await signIn(page.request, account);

  await page.goto("/dashboard/businesses");
  await openUserMenu(page);
  // The segment's buttons, as the menu lists them: light, dark, system.
  const dark = page
    .getByTestId("user-menu-theme")
    .locator("ion-segment-button")
    .nth(1);
  await expect(dark).toHaveJSProperty("value", "dark");
  await dark.click();
  await expect(page.locator("html")).toHaveClass(/ion-palette-dark/);
  await expect
    .poll(() => readBack(account.email, "user.preferences.theme_mode"))
    .toBe("dark");
  await closeUserMenu(page);
  await page.reload();
  await expect(page.locator("html")).toHaveClass(/ion-palette-dark/);
  await atEverySize(
    page,
    "G127",
    async () => {
      await openUserMenu(page);
      await expect(
        page.getByTestId("user-menu-theme").locator("ion-segment"),
      ).toHaveJSProperty("value", "dark");
    },
    () => closeUserMenu(page),
  );
  expect(errors).toEqual([]);
});

test("ACCOUNTS-G128 (F25): the user menu has «Account», «Report a problem», «Help», the theme and «Sign out»; «Account» opens the profile", async ({
  page,
}) => {
  const errors = watchPageErrors(page);
  const account = createAccount(address("menu"), { firstName: "Marta" });
  await signIn(page.request, account);

  await page.goto("/dashboard/businesses");
  await atEverySize(
    page,
    "G128",
    async () => {
      await openUserMenu(page);
      const menu = page.locator("ion-popover.sidebar-user-popover");
      await expect(menu.locator("ion-item")).toHaveText([
        "Account",
        "Report a problem",
        "Help",
        "Theme",
        "Sign out",
      ]);
    },
    () => closeUserMenu(page),
  );
  await openUserMenu(page);
  await page.getByTestId("user-menu-account").click();
  await expect(page).toHaveURL(/\/dashboard\/account\/profile$/);
  await expect(page.getByTestId("profile-email")).toContainText(account.email);
  expect(errors).toEqual([]);
});

test("ACCOUNTS-G111 (F26): «Download my data» saves a JSON with the account, its business and its ERPlora invoice, nothing of another account", async ({
  page,
}) => {
  const errors = watchPageErrors(page);
  const account = createAccount(address("export"));
  const other = createAccount(address("export-other"), { firstName: "Bea" });
  businessWithInvoice(account.email, "Panadería de Ana", 4242);
  businessWithInvoice(other.email, "Bodega de Bea", 4243);
  await signIn(page.request, account);

  await page.goto("/dashboard/account/profile");
  const card = page.getByTestId("profile-export-card");
  await expect(card).toContainText(
    "A copy of your account, your businesses and your ERPlora invoices, in a file other apps can read.",
  );
  const download = page.waitForEvent("download");
  await page.getByTestId("profile-export").click();
  const file = await download;
  expect(file.suggestedFilename()).toMatch(
    /^erplora-data-\d{4}-\d{2}-\d{2}\.json$/,
  );
  const text = await readFile((await file.path())!, "utf8");
  const data = JSON.parse(text) as {
    format: string;
    account: { email: string };
    businesses: Array<{ name: string }>;
    invoices: Array<{ number: string }>;
  };
  expect(data.format).toBe("erplora.account-export");
  expect(data.account.email).toBe(account.email);
  expect(data.businesses.map((row) => row.name)).toEqual(["Panadería de Ana"]);
  expect(data.invoices.map((row) => row.number)).toEqual(["ERP-2026-04242"]);
  expect(text).not.toContain(other.email);
  expect(text).not.toContain("Bodega de Bea");
  await atEverySize(page, "G111", async () => {
    await card.scrollIntoViewIfNeeded();
    await expect(card).toBeVisible();
  });
  expect(errors).toEqual([]);
});

test("ACCOUNTS-G112 (F27): an owner is told to hand over its business first; without one, the account goes and its invoice stays", async ({
  page,
}) => {
  const errors = watchPageErrors(page);
  const account = createAccount(address("delete"));
  businessWithInvoice(account.email, "Café de Ana", 4244);
  await signIn(page.request, account);

  await page.goto("/dashboard/account/profile");
  const danger = page.getByTestId("profile-danger");
  await expect(danger).toContainText(
    "You own 1 business: transfer or delete it before deleting your account.",
  );
  await expect(page.getByTestId("profile-danger-business")).toHaveText(
    "Café de Ana",
  );
  await expect(page.getByTestId("profile-delete")).toHaveJSProperty(
    "disabled",
    true,
  );
  await atEverySize(page, "G112-held", async () => {
    await danger.scrollIntoViewIfNeeded();
    await expect(danger).toBeVisible();
  });

  // The business deleted (its own flow, 90 days of recovery): it holds the account no more.
  djangoPrint(
    [
      "from django.utils import timezone",
      "from hubs.models import Hub",
      `Hub.objects.filter(name="Café de Ana", members__user__email="${account.email}").update(status=Hub.Status.DELETED, deletion_requested_at=timezone.now())`,
    ].join("\n"),
  );
  await page.reload();
  await expect(page.getByTestId("profile-delete")).toHaveJSProperty(
    "disabled",
    false,
  );
  await page.getByTestId("profile-delete").click();
  const dialog = page.getByTestId("delete-account");
  await expect(dialog).toContainText(
    "Your ERPlora invoices are kept for as long as the law requires.",
  );
  await atEverySize(page, "G112", async () => {
    await expect(dialog).toBeVisible();
  });
  await page
    .getByTestId("delete-account-input")
    .locator("input")
    .fill(account.email);
  await page.getByTestId("delete-account-submit").click();
  await expect(page).not.toHaveURL(/\/dashboard\/account/);
  expect(readBack(account.email, "user is None")).toBe("True");
  expect(
    djangoPrint(
      'from billing.models import Invoice;print(Invoice.objects.filter(number="ERP-2026-04244", payer_account=None).count())',
    ).trim(),
  ).toBe("1");
  expect(errors).toEqual([]);
});

test("ACCOUNTS-G35 (F13): the admin shows an account with its preferences and its photo, only to read", async ({
  page,
}) => {
  const errors = watchPageErrors(page);
  const staff = createAccount(address("root"), { staff: true });
  const account = createAccount(address("seen"));
  djangoPrint(
    [
      "from accounts.models import UserPreferences",
      "from django.contrib.auth import get_user_model",
      `UserPreferences.objects.create(user=get_user_model().objects.get(email="${account.email}"), theme_mode="dark", hub_alerts=False)`,
    ].join("\n"),
  );
  const id = readBack(account.email, "user.pk");
  await signIn(page.request, staff);

  await page.goto(`/admin/accounts/user/${id}/change/`);
  const inline = page.locator("#preferences-group");
  await expect(inline).toContainText("Dark");
  await expect(inline).toContainText("Business notices");
  await expect(inline).not.toContainText("ERPlora news");
  await expect(
    inline.locator('input:not([type="hidden"]), select, textarea'),
  ).toHaveCount(0);
  await atEverySize(page, "G35", async () => {
    await expect(page.locator("#user_form")).toBeVisible();
  });
  expect(errors).toEqual([]);
});
