// The flows of «the profile, the preferences, the user menu, downloading the data and deleting the account»
// (accounts/WORKBOOK.md, MIGRATION-TASK APP-ACCOUNTS-3) on their screens, at the three sizes of the migration
// (390×844, 834×1112, 1440×900), against the real hubs and billing (no mocks): the business is created by its
// operation, ERPlora's invoice is a row billing reads. Each test names its flow by its registry key; in
// accounts/WORKBOOK.md: G108=F21, G114=F22, G115=F23, G127=F24, G128=F25, G111=F26, G112=F27, G35=F13.
// Accounts of this spec: `e2e-acc3-…@example.com`, removed before and after.
import { readFile } from "node:fs/promises";

import { type APIRequestContext, type Page } from "@playwright/test";

import {
  captureAtEverySize,
  djangoPrintWarm,
  expect,
  sessionOf,
  settled,
  signIn,
  test,
  toast,
  watchPageErrors,
} from "./fixtures";

const atEverySize = captureAtEverySize("APP-ACCOUNTS-3");

const PREFIX = "e2e-acc3-";
const PASSWORD = "Centeno-y-masa-madre-26";

/** A fresh address of this spec, never used before. */
const address = (name: string) => `${PREFIX}${name}-${Date.now()}@example.com`;

async function removeAccounts(): Promise<void> {
  await djangoPrintWarm(
    [
      "from django.contrib.auth import get_user_model",
      "from hubs.models import Hub",
      `Hub.objects.filter(members__user__email__startswith="${PREFIX}").delete()`,
      `get_user_model().objects.filter(email__startswith="${PREFIX}", email__endswith="@example.com").delete()`,
    ].join("\n"),
  );
}

/** An account with its address proven, as one that signed in before; `staff` makes it a platform administrator. */
async function createAccount(
  email: string,
  options: { staff?: boolean; firstName?: string } = {},
): Promise<{ email: string; password: string }> {
  await djangoPrintWarm(
    [
      "from allauth.account.models import EmailAddress",
      "from django.contrib.auth import get_user_model",
      `user = get_user_model().objects.${options.staff ? "create_superuser" : "create_user"}(email="${email}", password="${PASSWORD}", first_name="${options.firstName ?? "Ana"}", last_name="García", language="en")`,
      "EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)",
    ].join("\n"),
  );
  return { email, password: PASSWORD };
}

let lastSequence = 0;

/** The sequence of this spec's next ERPlora invoice, never given before, as `address()` gives a fresh address: an
 *  invoice is never deleted (ACCOUNTS-G112 checks that the deleted account's stays), so a fixed one met the previous
 *  run's on the same e2e database (saas#227). The clock in seconds, since the field is a 32-bit integer too small for
 *  `Date.now()`; one more than the last when two fall in the same second. */
function nextSequence(): number {
  lastSequence = Math.max(lastSequence + 1, Math.floor(Date.now() / 1000));
  return lastSequence;
}

/** A business of `email` made by its operation, with one ERPlora invoice it paid; the invoice's number. */
async function businessWithInvoice(email: string, name: string): Promise<string> {
  const sequence = nextSequence();
  const number = `ERP-2026-${sequence}`;
  await djangoPrintWarm(
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
        ` number="${number}", issued_on=date(2026, 9, 1), billed_at=timezone.now(), net_cents=2999,` +
        ' tax_cents=630, total_cents=3629, tax_country="ES", fiscal_status="accepted", payer_name=hub.name, payer_country="ES")',
      'InvoiceLine.objects.create(invoice=invoice, position=1, description="1 × Starter", item_kind="plan",' +
        ' item_slug="starter", net_cents=2999, tax_cents=630, total_cents=3629)',
    ].join("\n"),
  );
  return number;
}

/** The value Django reads back for `expression` of the account `email` (`user`), printed: for what no page shows. */
const readBack = (email: string, expression: string) =>
  djangoPrintWarm(
    [
      "from django.contrib.auth import get_user_model",
      `user = get_user_model().objects.filter(email="${email}").first()`,
      `print(${expression})`,
    ].join("\n"),
  );

/** Account › Preferences of `request`'s account, as the panel reads it (`GET /api/accounts/preferences`). */
async function preferencesOf(
  request: APIRequestContext,
): Promise<{ theme_mode: string; language: string; hub_alerts: boolean }> {
  const response = await request.get("/api/accounts/preferences");
  expect(response.status(), "GET /api/accounts/preferences").toBe(200);
  return (await response.json()) as { theme_mode: string; language: string; hub_alerts: boolean };
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

test.beforeAll(removeAccounts);
test.afterAll(removeAccounts);

test("ACCOUNTS-G108 (F21): Profile shows the account and keeps the names after a reload", async ({
  page,
}) => {
  const errors = watchPageErrors(page);
  const account = await createAccount(address("profile"));
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
  expect((await sessionOf(page.request)).user?.label).toBe("Lucía Martín");
  await atEverySize(page, "G108", async () => {
    await expect(page.getByTestId("profile-card")).toBeVisible();
  });
  expect(errors).toEqual([]);
});

test("ACCOUNTS-G114 (F22): Preferences saves the appearance and the language on their own, kept after a reload", async ({
  page,
}) => {
  const errors = watchPageErrors(page);
  const account = await createAccount(address("preferences"));
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
  expect(await preferencesOf(page.request)).toMatchObject({
    language: "es",
    theme_mode: "dark",
  });
  await atEverySize(page, "G114", async () => {
    await expect(page.getByTestId("preferences-language-card")).toBeVisible();
  });
  expect(errors).toEqual([]);
});

test("ACCOUNTS-G115 (F23): «Business notices» is the one switch, kept after a reload; the mails that always go say so", async ({
  page,
}) => {
  const errors = watchPageErrors(page);
  const account = await createAccount(address("notices"));
  await signIn(page.request, account);

  await page.goto("/dashboard/account/preferences");
  const mails = page.getByTestId("preferences-mails");
  await expect(mails).toContainText("Security, invoices and payments");
  await expect(mails).toContainText(
    "Always on: sign-in codes, security notices, invoices, payments, the messages you have left with the assistant and anything that needs you to act.",
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
  expect((await preferencesOf(page.request)).hub_alerts).toBe(false);
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
  const account = await createAccount(address("theme"));
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
    .poll(async () => (await preferencesOf(page.request)).theme_mode)
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
    { after: () => closeUserMenu(page) },
  );
  expect(errors).toEqual([]);
});

test("ACCOUNTS-G128 (F25): the user menu has «Account», «Report a problem», «Help», the theme and «Sign out»; «Account» opens the profile", async ({
  page,
}) => {
  const errors = watchPageErrors(page);
  const account = await createAccount(address("menu"), { firstName: "Marta" });
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
    { after: () => closeUserMenu(page) },
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
  const account = await createAccount(address("export"));
  const other = await createAccount(address("export-other"), { firstName: "Bea" });
  const number = await businessWithInvoice(account.email, "Panadería de Ana");
  await businessWithInvoice(other.email, "Bodega de Bea");
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
  expect(data.invoices.map((row) => row.number)).toEqual([number]);
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
  const account = await createAccount(address("delete"));
  const number = await businessWithInvoice(account.email, "Café de Ana");
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
  await djangoPrintWarm(
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
  expect(await readBack(account.email, "user is None")).toBe("True");
  expect(
    await djangoPrintWarm(
      `from billing.models import Invoice;print(Invoice.objects.filter(number="${number}", payer_account=None).count())`,
    ),
  ).toBe("1");
  expect(errors).toEqual([]);
});

test("ACCOUNTS-G35 (F13): the admin shows an account with its preferences and its photo, only to read", async ({
  page,
}) => {
  const errors = watchPageErrors(page);
  const staff = await createAccount(address("root"), { staff: true });
  const account = await createAccount(address("seen"));
  await djangoPrintWarm(
    [
      "from accounts.models import UserPreferences",
      "from django.contrib.auth import get_user_model",
      `UserPreferences.objects.create(user=get_user_model().objects.get(email="${account.email}"), theme_mode="dark", hub_alerts=False)`,
    ].join("\n"),
  );
  const id = await readBack(account.email, "user.pk");
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
