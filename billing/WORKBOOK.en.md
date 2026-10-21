<!-- generated from WORKBOOK.md sha256:ae7f35c6aed94c81f6a6cd7b38061f1bc8de9d8bf36d0ef7a08ab62763becab0 -->

## What it is for and who it is for

Billing is what an account pays ERPlora for its businesses. Every business starts on **Free** and, when it
needs to, its owner moves it to a paid plan from the **Store**. ERPlora charges the card through Stripe, adds
the VAT that applies to where the payer is, and issues its own legal invoice for every charge, which is seen
and downloaded in **Billing**.

- One subscription per business: the plan and the modules bought go together and are charged on a single
  invoice a month (or a year).
- Cancelling never deletes anything: the business keeps its plan until the end of the paid period and then
  goes back to Free.
- If a charge fails, the business keeps working for 7 days while it is retried; then it is suspended until it
  is paid, without losing any data.

Who uses it:

- The business's **owner** pays, changes and cancels its plan, and sees its invoices.
- The **paying account** of a business (usually the owner; after a transfer it may still be the previous one
  until the new owner changes it) sees its invoices and is the only one that can pay them.
- **ERPlora staff** keep the VAT table, the prices in Stripe and the promo codes, and review what Stripe did
  from the admin.

## Reference adopted

- **Stripe Billing** as gateway and lifecycle model: one subscription per business, payment with Stripe's
  secure form inside the page, price change with proration, automatic retries of a failed charge and
  cancellation at the end of the paid period (https://docs.stripe.com/billing/subscriptions/overview).
- **Square Free** and **Shopify**: one plan per shop; cancelling goes back to the free plan without deleting
  anything; an upgrade is charged at once and a downgrade waits for the end of the period.
- **WooCommerce Subscriptions, Square and Lightspeed**: a short grace after a failed charge (7, 9 and 21 days)
  with a notice in the panel and by email before suspending.
- **ERPlora sets the VAT, not Stripe Tax**: net prices, and the rate comes from our table according to where
  the payer is, as the European market does with the Canary Islands, Ceuta and Melilla (outside VAT) and with
  the reverse charge of an EU VAT number checked in VIES.
- **Stripe's receipt is not the legal invoice**: ERPlora numbers its invoice and its own platform business
  issues it, with VeriFactu, as any Spanish company that charges with Stripe does.

## Before you start

- Sign in at erplora.com with the owner's account. In development the panel is on port 8001 and Stripe is
  always in test mode (test card 4242 4242 4242 4242).
- The plans live in the admin, with the monthly and annual price Stripe charges; a plan without its Stripe
  price is not sold. Since 15 October 2026 no plan comes with trial days: the Free plan is the way in.
- Without the VAT table of the payer's territory, nothing is sold: better not to charge than to charge wrong.
- In the apps (Android, Windows) and from the account opened in the app nothing is sold or charged: invoices
  and subscriptions are shown there, and to pay or change plan they say to go to erplora.com in the browser.

## Screens

### Store
Menu **Store**, with two sections: **Plans** and **Modules**, and at the top the business it buys for (only
the businesses one owns). Plans shows each plan with its price without VAT, the period ("Monthly" or
"Annual · −n %"), "Your current plan" on the one it has and each plan's button: "Upgrade to …",
"Change to …", "Change to annual · …" or "Downgrade to Free"; with the plan cancelled, "Keep the plan". If the
business has an unpaid invoice, the notice with "Pay the invoice" comes at the top and nothing is sold to that
business.

### Secure payment
Dialog that opens when upgrading a business that does not pay yet: first "Who do we invoice?" (only the first
time), then Stripe's card form inside the dialog, with "Have a promo code?". When done, "Paying…" and the
business's page.

### Change plan
Dialog of a business that already pays: what is charged today prorated, the VAT, the total and what will be
charged afterwards, with "Pay … and change" (or "Change plan" if nothing is charged today, as in a downgrade,
which waits for the end of the period).

### Billing
Menu **Billing**, with three tabs: **Invoices** (table with Invoice, Date, Business, Amount and Status;
filters by business, status and year; search by number; "Download PDF", "Download Excel" and "Pay" on the
uncollected ones), **Subscriptions** (one row per paying business: plan, modules, next invoice with VAT and
status; "Change plan", "Keep the plan", "View the invoice", "View invoices" and "Cancel plan") and **Payment
details** (the card with "Change card" and the billing details with "Edit details"). At the top of all three,
the notices of unpaid invoices.

### Business summary
On each business's page, the **Plan** card says which plan it is on, how many users and devices fit and, to
the owner, the button to upgrade or change it.

## States of each screen

| State | What the person sees |
|---|---|
| Loading | "Loading…" or the table's skeleton while the data arrives; "Working out what is charged today…" in a plan change. |
| Empty | Invoices: "No invoices yet" and "See plans"; Subscriptions: "All your businesses are on Free"; Payment details: "No card saved yet". |
| Error | "We could not load …" with "Retry"; a payment that does not open says "Nothing has been charged" with "Retry". |
| Stripe not answering | The card: "We cannot show you the card right now: try again in a few minutes"; a payment: the notice that nothing has been charged. |
| Unpaid invoice | Notice at the top with the amount, the business and until when it works, and "Pay the invoice"; with the card declined, "Change card" first. |
| In the app | Everything that does not charge is shown; where a payment button would be, "go to erplora.com in the browser", without a link. |
| No permission | A business that is not yours does not appear; through the API, "Not found". |

## Flows

| ID | Flow | Status |
|---|---|---|
| BILLING-F01 | Say where the business is invoiced and with which tax ID | done |
| BILLING-F02 | Work out the tax of a sale from where the payer is | partial |
| BILLING-F03 | Decide the VAT of each charge | done |
| BILLING-F04 | Keep the VAT rate table and never sell with it broken | partial |
| BILLING-F05 | Check the payer's EU VAT number in VIES | done |
| BILLING-F06 | Follow the EU distance-selling threshold (OSS) | partial |
| BILLING-F07 | Pay the plan of a newly created business | done |
| BILLING-F08 | Move a free business to a paid plan | done |
| BILLING-F09 | Come back from the payment: confirmed, pending or closed | done |
| BILLING-F10 | Retry a payment that was not finished | done |
| BILLING-F11 | Change between paid plans | done |
| BILLING-F12 | Give trial days with a promo code | done |
| BILLING-F13 | Cancel the plan at the end of the period | done |
| BILLING-F14 | Undo a pending cancellation | done |
| BILLING-F15 | End the subscription: the business goes back to Free | done |
| BILLING-F16 | Unpaid plan: retries, suspension and return | done |
| BILLING-F17 | Reactivate a suspended business by paying its invoice | done |
| BILLING-F18 | See, cancel or keep the business's plan through the API | done |
| BILLING-F19 | Receive and validate a notice from Stripe | done |
| BILLING-F20 | Renew the plan every period | done |
| BILLING-F21 | Keep the plan in step with what Stripe says | done |
| BILLING-F22 | See the invoices and download them | done |
| BILLING-F23 | See the subscriptions of each business | done |
| BILLING-F24 | Open Stripe's payment portal to change the card | done |
| BILLING-F25 | Issue ERPlora's invoice for a charge | done |
| BILLING-F26 | Refund a charge | done |
| BILLING-F27 | What ERPlora staff can do about a customer's billing | done |
| BILLING-F28 | Keep the plans' prices in Stripe | done |
| BILLING-F29 | Test real charging in PRE with a Stripe test clock | done |
| BILLING-F30 | Use live Stripe keys only in production and test keys elsewhere | done |

### BILLING-F01 Say where the business is invoiced and with which tax ID
<!-- origen: old-saas:SAAS_DASHBOARD-F90 -->
Status: done
Actor: owner, paying account
Screen: Secure payment, Billing › Payment details
Steps:
1. The first time a plan or a module is paid, the payment dialog asks "Who do we invoice?": "Company name", "Tax ID (optional)", "Address", "City", "Postal code", "Country" and "Email for invoices (optional)", or "Use the business's name and country".
2. Tap "Continue to payment": the details are saved and the payment goes on. The following times the dialog only says "Invoiced to …" with "Change".
3. At any time, in **Billing › Payment details**, the "Billing details" card shows company name, tax ID, address, email and which businesses it pays, with "Edit details".
4. When an EU VAT number of another country is typed, the window checks it in VIES and says "Checked in VIES: … The invoice goes without VAT", "VIES does not recognise this number: the invoice will carry VAT" or "VIES is not answering now: we check it again when invoicing".
5. Tap "Save details": "Billing details saved". They apply to the next invoices; those already issued do not change.
In: what the person types; the business's country and name if they choose to use them.
Out: the business's billing details (shared by the businesses the same account pays) and the VIES check recorded; the change is announced (`hubs.billing_profile.updated`).
If it fails: a Spanish postal code without five digits, a missing country or a tax ID that is not valid for its country are shown under their field and nothing is saved. After a transfer, if another account paid the business, the dialog says "Until now another account paid this business: say who pays from now on".
Involved: hubs (the business's and the payer's details)

### BILLING-F02 Work out the tax of a sale from where the payer is
<!-- origen: old-saas:SAAS_DASHBOARD-F91 -->
Status: partial — with a downgrade already scheduled, the first invoice of the new plan goes out with the rate from before the billing details changed (the following ones carry the new one)
Actor: system
Screen: none
Steps:
1. Before opening any payment (a plan, a plan change or a module), erplora.com reads the payer's country and postal code. Without both, the payment does not start and the billing details are asked for.
2. It qualifies the sale with the same rule the invoice uses afterwards: mainland Spain and the Balearic Islands, Spanish VAT; Canary Islands, Ceuta and Melilla, no VAT (the price is charged with nothing on top); another EU country with an EU VAT number checked in VIES, reverse charge, no VAT; a consumer in another EU country, Spanish VAT until the distance-selling threshold is passed and then their country's; United Kingdom, businesses only and no VAT.
3. If the total with VAT goes over €400 and the payer has no tax ID, the sale is refused and the tax ID is asked for (a simplified invoice cannot go beyond that).
4. The resulting rate travels to Stripe with each line of the subscription; Stripe only adds what it is given.
5. When the **billing details** are saved, the subscription already being charged takes the rate of the new place from the next invoice, without touching what is already paid (for example, someone who moves from Madrid to Las Palmas stops paying VAT). A daily review repeats the same with every live subscription in case a change did not get through.
In: the payer's country, postal code and tax ID, the latest VIES check, the price without VAT and what is sold (plan or module).
Out: the rate of each line in Stripe, or the refusal with its reason.
If it fails: "Billing details are missing" leads to the form; a territory without a rule in the table is not sold to; a UK consumer does not buy; over €400 without a tax ID asks for it. A €0 price is never refused. If Stripe does not answer when the details are saved, the details are saved anyway and the daily review applies the rate; if the new place is not sold to, the subscription keeps its rate and the daily review goes red for the team.
Involved: hubs (the payer's details)

### BILLING-F03 Decide the VAT of each charge
<!-- origen: old-saas:SAAS_DASHBOARD-F142 gh:saas#2528 -->
Status: done
Actor: system
Screen: none
Steps:
1. When pricing (before charging) and when invoicing (afterwards), the same engine qualifies the sale: domestic, not subject (Canary Islands, Ceuta, Melilla, United Kingdom), reverse charge or the VAT of the customer's country (distance sales above the threshold).
2. When invoicing, it splits what Stripe charged into base and tax and stamps on the invoice the table's nominal rate (21 %, never a 21.01 % that comes from dividing cents).
3. If Stripe charged no tax on a sale subject to VAT, the invoice takes the VAT out of what was charged and leaves an alarm for the team: VAT is never left undeclared.
In: the payer's country, postal code and tax ID, their VIES check at the date of the charge, the tax policy and the rate table.
Out: the treatment, the rate, the base and the tax, stamped on each line of the invoice.
If it fails: if VIES does not answer and there is no earlier check, the invoice waits and Stripe sends the notice again: Spanish VAT is never put on a sale between EU businesses because VIES was not answering. If the lines do not add up to what was charged, the invoice is not issued and the alarm stays.
Involved: none

### BILLING-F04 Keep the VAT rate table and never sell with it broken
<!-- origen: old-saas:SAAS_DASHBOARD-F143 -->
Status: partial — the review of the table exists and goes red, but it is not scheduled every day yet: until then a person of the team runs it
Actor: ERPlora staff
Screen: Admin › Tax rules
Steps:
1. A person of ERPlora edits in the admin the **tax rules** (country, region, category, rate, subject or not, from and until) and the **categories**. The most specific rule wins.
2. The list shows what is needed to operate and is filtered by country and category; two rules of the same territory starting on the same day are refused when saving.
3. Every sale reads the table at that moment: a territory without a rule in force is not sold to.
4. The **review of the table** looks at every possible sale and goes red, saying what to fix and where, if the rule of the invoicing country is missing, if the Canary Islands, Ceuta or Melilla stop going out without VAT (rule deleted, deactivated, marked as subject or a postal code that no longer recognises them) or if a country with a registered payer has no rate. A country only covered by the general backstop rate is a warning, not a failure.
In: the table and the businesses' billing details.
Out: the table changed.
If it fails: deactivating a territory's rule makes every sale to it be refused from that moment.
Involved: none

### BILLING-F05 Check the payer's EU VAT number in VIES
<!-- origen: old-saas:SAAS_DASHBOARD-F144 gh:saas#2665 -->
Status: done
Actor: system, ERPlora staff
Screen: Billing › Payment details, Admin › VAT checks
Steps:
1. When an EU VAT number of another country is typed in the billing details, and when charging, erplora.com asks VIES identifying itself with ERPlora's VAT number, so VIES returns the consultation number, which is the proof. A Spanish tax ID is not asked about; a British one is not in VIES.
2. Each answer is a new row that is never rewritten (checked, not valid, not available). Only a "checked" in force with its consultation number (or the manual override) allows invoicing without VAT.
3. Staff can ask again with the "Check now in VIES" action of **VAT checks**, or leave a manual "checked" with its reason, which records who and when.
4. Each person has 20 checks a minute and there is a global cap; only one check at a time per person.
In: the EU VAT number and the country.
Out: the history of checks (`billing.vat_check.completed`) and the consultation number stamped on the invoice.
If it fails: VIES not answering is "not available" and the sale carries VAT; past the cap, "Too many checks: wait a minute"; a number without a valid format is shown under the field. The checks admin only opens with the SaaS's sign-in, which asks for the email code and the authenticator app.
Involved: none

### BILLING-F06 Follow the EU distance-selling threshold (OSS)
<!-- origen: old-saas:SAAS_DASHBOARD-F145 -->
Status: partial — there is no notice to the team past 80 % of the threshold (the new SaaS has no team mailbox) and the daily review that changes the rate of live subscriptions is not scheduled yet
Actor: system, ERPlora staff
Screen: Admin › Tax policy
Steps:
1. Each invoice to a consumer in another EU country adds its base to the year's total (credit notes subtract); the total sold by the previous SaaS is loaded once by hand in **Tax policy**.
2. **Tax policy** shows the year's total against the threshold (€10,000 by default) and the switches of the OSS and ROI registrations.
3. Above the threshold (or with the voluntary OSS registration, or if the previous year closed above it) new sales to EU consumers carry the VAT of the customer's country.
4. The daily review of the live subscriptions moves those customers to their country's rate from the next invoice (and back to the Spanish one when the year returns to origin); what Stripe already has is not sent again.
In: the invoices and the policy.
Out: the rate of each new sale and that of the live subscriptions.
If it fails: a business Stripe does not let change does not stop the review: it is retried the next day and the team sees it red. While the year's total has not been loaded, the admin says "unknown" and with live keys nothing is sold (better not to sell than to cross the threshold without seeing it).
Involved: none

### BILLING-F07 Pay the plan of a newly created business
<!-- origen: old-saas:SAAS_DASHBOARD-F92 gh:saas#2527 -->
Status: done
Actor: owner
Screen: Business summary, Store, Secure payment
Steps:
1. The business is always born on Free (signing it up only asks for name, country and type of business).
2. In the Business summary, the Plan card says "Free" and offers "Upgrade plan" (on a paid plan, "Change plan"), which opens the Store with that business chosen. Only whoever manages the business's billing sees it, and only on the web: in the apps it says to go to erplora.com in the browser.
3. Choose the plan and the period and tap "Upgrade to …": the payment goes on as in BILLING-F08.
In: the newly created business and the plans offered to that person (the internal ones, only to staff).
Out: the same as BILLING-F08.
If it fails: the same refusals as BILLING-F08.
Involved: hubs (the sign-up and the business's page)

### BILLING-F08 Move a free business to a paid plan
<!-- origen: old-saas:SAAS_DASHBOARD-F95 gh:saas#2527 -->
Status: done
Actor: owner
Screen: Store, Secure payment
Steps:
1. In **Store › Plans**, with the business chosen at the top, the owner picks "Monthly" or "Annual" and taps "Upgrade to …".
2. The secure payment opens: the billing details if they are missing and then Stripe's card form inside the dialog, titled "Upgrade to …" with "For … · renews every month" (or every year).
3. Enter the card; if the bank asks for authentication, Stripe shows it in the same form.
4. When done, "Paying…", the notice "… is now on …" and the business's page, whose Plan card changes as soon as Stripe confirms it. The business keeps working all the time.
In: the chosen plan (only those offered to that person), the period, the billing details and the promo code if there is one.
Out: the business on the new plan, its subscription and its customer in Stripe, the new plan sent to the business (`hubs.subscription.changed`) and ERPlora's invoice for the first charge (BILLING-F25), whether the payment notice arrives before or after.
If it fails: if the payment cannot be opened, "We could not open the secure payment" and "Nothing has been charged" with "Retry"; a plan without a price in Stripe, "is not on sale"; without billing details, the form; with an unpaid invoice, nothing is sold to that business. If the person closes the dialog, nothing is charged and the business stays on Free.
Involved: hubs (the business's subscription), the business (receives its plan)

### BILLING-F09 Come back from the payment: confirmed, pending or closed
<!-- origen: old-saas:SAAS_DASHBOARD-F93 -->
Status: done
Actor: owner
Screen: Secure payment, Business summary
Steps:
1. When the payment is finished in Stripe's form, the dialog says "Paying…", closes the form, says "… is now on …" (or "… added to …: it turns on in a few seconds" for a module) and opens the business's page.
2. The business's plan changes when Stripe confirms the charge: if the payment method takes time to confirm, the business stays on its previous plan until then and changes by itself, without reloading.
3. If the person closes the dialog before paying, nothing is charged and they can open it again.
In: the payment Stripe considers finished.
Out: the same new plan that Stripe's notice leaves (BILLING-F19); the return and the notice never apply the same payment twice.
If it fails: a payment that Stripe later considers failed closes that attempt without changing the plan; a payment for something else (a module) never changes the plan.
Involved: the business (receives its plan)

### BILLING-F10 Retry a payment that was not finished
<!-- origen: old-saas:SAAS_DASHBOARD-F94 gh:saas#2527 -->
Status: done
Actor: owner
Screen: Store, Secure payment
Steps:
1. The owner opens "Upgrade to …" again with the same choice: the same payment reopens, without creating another.
2. If they change the plan or the period, the previous payment is voided in Stripe and a new one opens; there are never two open payments for the same business.
3. Pay as in BILLING-F08.
In: the business that does not pay yet and its choice.
Out: a single open payment per business; when paid, the same as BILLING-F08.
If it fails: if by mistake two were paid (two tabs at once), the second is not applied: its subscription is cancelled at once with what was not used as credit, and an alarm stays for the team. An expired payment is not reused: another one opens.
Involved: none

### BILLING-F11 Change between paid plans
<!-- origen: old-saas:SAAS_DASHBOARD-F96 -->
Status: done
Actor: paying owner
Screen: Store, Change plan
Steps:
1. In **Store › Plans** of a business that already pays, the owner taps "Change to …", "Change to annual · …" or "Change to monthly · …".
2. The dialog works out what is charged today ("Working out what is charged today…") and shows "Today (prorated)", the VAT, the "Total today" and what will be charged "Afterwards", with the note that the modules stay the same.
3. An upgrade is confirmed with "Pay … and change": it is charged at once with the saved card and the business moves to the new plan at once. A downgrade (a cheaper plan, or annual to monthly) charges nothing today: it moves to the new plan at the end of the paid period, and **Billing › Subscriptions** says "Changes to … on …".
4. Notice: "… is now on …" (or "…, paid annually").
In: the new plan and period and the business's subscription with its card; when the period changes, each module's price changes too.
Out: the plan changed (`billing.plan.changed`) or the downgrade scheduled (`billing.plan.change_scheduled`), with the table's VAT on each line, and the new plan sent to the business.
If it fails: "The price was out of date: here it is again, check it before confirming" if too much time went by; a declined card changes nothing; the same plan and period is no change; downgrading to Free is cancelling (BILLING-F13); with a pending cancellation, "Keep the plan first to change it"; with an unpaid invoice, "First, pay the pending invoice"; over €400 without a tax ID asks for it.
Involved: the business (receives its plan)

### BILLING-F12 Give trial days with a promo code
<!-- origen: old-saas:SAAS_DASHBOARD-F122 -->
Status: done
Actor: ERPlora staff, owner
Screen: Admin › Promo codes, Secure payment
Steps:
1. A person of ERPlora creates a code in the admin: the code, the trial days (1 to 365), whether it is active, until when it is valid, how many uses and a note.
2. The owner, in the secure payment of a business that does not pay yet, taps "Have a promo code?", types it and taps "Apply": "Code …: n free days before the first charge".
3. Pay: the first charge comes when those days end.
In: the code (case and spaces do not matter).
Out: the trial days on the subscription and the use counted once per business and per payer.
If it fails: an unknown, inactive, expired or used-up code says "This code is not valid or has already been used" and does not stop paying without it; trying codes has a cap per person. A code never lowers the price and never goes past its number of uses.
Involved: none

### BILLING-F13 Cancel the plan at the end of the period
<!-- origen: old-saas:SAAS_DASHBOARD-F101 gh:saas#2530 -->
Status: done
Actor: paying owner
Screen: Billing › Subscriptions, Store
Steps:
1. In **Billing › Subscriptions**, on the business's row, the owner opens "⋮" and taps "Cancel plan" (or, in the Store, "Downgrade to Free").
2. The "Cancel the plan" dialog talks about that business: "Stays on … until …; then it moves to Free and is not charged again", which modules turn off that day, how many users and devices fit on Free against those it has, and that until then it can be undone with "Keep the plan".
3. Tap "Cancel plan": "Plan cancelled: … stays on … until …". The row says "Free from …" and has no next invoice any more.
In: the business's Stripe subscription.
Out: the subscription marked in Stripe to end at the end of the period (`billing.plan.cancelled`); nothing else changes until that date (BILLING-F15).
If it fails: if Stripe refuses it or does not answer, nothing changes and it is said. Cancelling with an unpaid invoice is allowed, but it does not void it: the dialog warns about it. A business on Free has nothing to cancel.
Involved: the business (receives the end date)

### BILLING-F14 Undo a pending cancellation
<!-- origen: old-saas:SAAS_DASHBOARD-F102 gh:saas#2529 gh:saas#2574 -->
Status: done
Actor: paying owner
Screen: Billing › Subscriptions, Store
Steps:
1. On the row of a business with its plan cancelled, the owner taps "Keep the plan" (in the Store: "Cancelled: … until … and then Free" with "Keep the plan").
2. Notice: "… stays on …" or "… is kept: it renews on …". The row has a next invoice again.
In: the subscription with its end marked.
Out: the subscription renews again in Stripe, with the status Stripe says (`billing.plan.kept`); a scheduled downgrade is undone too.
If it fails: with an unpaid invoice it is not kept: it is paid first (a plan is not recovered without paying it). Keeping a plan that was not cancelled changes nothing.
Involved: none

### BILLING-F15 End the subscription: the business goes back to Free
<!-- origen: old-saas:SAAS_DASHBOARD-F103 gh:saas#2575 gh:saas#2527 -->
Status: done
Actor: system
Screen: none
Steps:
1. The end of the period of a cancelled plan arrives (or Stripe considers the subscription ended). Stripe sends a notice.
2. erplora.com moves the business to Free: without a Stripe subscription, owing nothing and with the bought modules ended that day. No data is deleted.
3. The business receives its new plan and keeps working within Free's limits.
In: Stripe's notice that the subscription ended.
Out: the business on Free (`hubs.subscription.changed`) and its plan sent to the business. There is no email when it ends: since it was cancelled, the panel already says "Free from …".
If it fails: a notice about an unknown subscription is acknowledged without touching anything; that of a deleted business neither creates nor moves anything.
Involved: the business (receives Free)

### BILLING-F16 Unpaid plan: retries, suspension and return
<!-- origen: old-saas:SAAS_DASHBOARD-F100 gh:saas#2529 gh:saas#2574 gh:saas#2593 gh:saas#2594 -->
Status: done
Actor: system, owner, paying account
Screen: Billing, Businesses, the business itself
Steps:
1. The charge of a renewal fails. Stripe retries it for some days and sends a notice of each failure.
2. erplora.com reads the subscription again in Stripe: if the retry already charged, it does nothing; if not, it records the invoice as "Not collected", with why it was not collected (card declined, authentication or failure).
3. **Grace**: for 7 days from the invoice that failed, the business keeps working with all its plan. The paying account receives an email, once per invoice: how much could not be charged, until what day it keeps working and the link to Billing to pay it (if the bank declined the card, to change it first). In **Businesses** and in **Billing** the notice "We could not charge … for …" appears: "Pay it before … or the business is suspended; nothing is deleted", with "Pay the invoice" (or "Change card" first if the bank declined it).
4. **Suspension**: after the 7 days, or if Stripe runs out of retries, the business is suspended and the paying account receives another email, only once. The business does not open: neither from the panel nor from its own address, not even on the devices that already had the session open, which show "This business is suspended" with the way to ERPlora. The panel's notice says "… is suspended: … unpaid" and that the data is safe.
5. **Safety net**: every hour the businesses with their plan unpaid are gone over and their oldest open invoice is looked at, in case Stripe stopped retrying without sending another notice.
6. **Return**: when the invoice is paid (with "Pay the invoice", or because a retry collects it), the business is active again at once: "Invoice paid: … is up to date again".
In: Stripe's notices of the failed charge and of the subscription, and the live subscription.
Out: the "Not collected" invoice, the emails to the payer and the business's status (payment pending, suspended or up to date) sent to the business (`hubs.subscription.changed`).
If it fails: if Stripe does not answer when reading the subscription again, nothing is applied and Stripe sends the notice again. A repeated notice of an invoice already paid does not reopen it. A later failure of the same unpaid episode does not move the grace date nor repeat the email. An email that could not go out is sent again in the hourly pass, which warns the team while any is left.
Involved: hubs (the business's status), the business (receives the status)

### BILLING-F17 Reactivate a suspended business by paying its invoice
<!-- origen: old-saas:SAAS_DASHBOARD-F104 gh:saas#2575 gh:saas#2527 gh:saas#2529 -->
Status: done
Actor: paying account
Screen: Billing › Invoices, Businesses
Steps:
1. On the notice of the suspended business (in **Businesses** or in **Billing**), the paying account taps "Pay the invoice · …" (if the bank declined the card, "Change card" first).
2. Stripe's payment page of that invoice opens; pay.
3. Back, "Invoice paid: … is up to date again" and the business works again with its data and its plan, without opening another subscription.
In: the unpaid invoice and its payment page in Stripe.
Out: the invoice paid and numbered (BILLING-F25), the business active and its status sent to the business.
If it fails: "Paying…" blocks a second click; only the paying account of the business can pay its invoice ("Only the account that pays this business can pay its invoices"); an invoice already paid or voided is not paid again. A business whose plan already ended is on Free and goes back to a paid plan from the Store (BILLING-F08).
Involved: hubs (the business's status), the business (opens again)

### BILLING-F18 See, cancel or keep the business's plan through the API
<!-- origen: old-saas:SAAS_DASHBOARD-F64 gh:saas#2529 gh:saas#2574 -->
Status: done
Actor: owner, integration
Screen: none
Steps:
1. With their session, the owner (or an integration of their account) asks for the list of subscriptions: one row per business Stripe charges, with plan, modules, next invoice and status.
2. They ask to cancel the plan at the end of the period or to keep it, with the same rules as the screen.
In: the account's session.
Out: the same as BILLING-F13 and BILLING-F14.
If it fails: a business that is not that account's is not found; keeping a plan with an unpaid invoice is refused; without a session, "You are not signed in".
Involved: none

### BILLING-F19 Receive and validate a notice from Stripe
<!-- origen: old-saas:SAAS_DASHBOARD-F97 gh:saas#2530 gh:saas#2539 -->
Status: done
Actor: system
Screen: none
Steps:
1. Stripe sends a notice to erplora.com, to a single address for everything.
2. erplora.com checks the signature with its secret; without a valid signature, or with an old repeated notice, it refuses it without doing anything.
3. It claims the notice only once: if it was already processed, it answers "duplicate"; if another delivery is processing it, it asks Stripe to come back later.
4. If it is a payment, it looks at what it pays by the tag erplora.com put on it when opening it: one that is not ours is acknowledged without touching anything.
5. It processes it by its type (sign-up, renewal, unpaid, end, refund) and records it as processed.
In: the signed notice.
Out: the notice's row with its type and its result, read-only in the admin.
If it fails: an error while processing it is recorded and answered with an error, so that Stripe sends it again; the claim of a delivery that died halfway expires and the next one takes it over. Without the secret configured, Stripe receives "come back later".
Involved: none

### BILLING-F20 Renew the plan every period
<!-- origen: old-saas:SAAS_DASHBOARD-F98 gh:saas#2527 gh:saas#2529 gh:saas#2530 gh:saas#2540 -->
Status: done
Actor: system
Screen: none
Steps:
1. At the end of each period Stripe charges the saved card and sends a notice of the charge.
2. erplora.com reads the live subscription again and saves its new period and its status (a trial is still a trial).
3. If the business was unpaid, it is up to date again at once.
4. It records and numbers the invoice of that charge and sends it to be issued (BILLING-F25).
In: the notice of the paid charge.
Out: the period and status of the business's subscription and its invoice (`billing.invoice.recorded`).
If it fails: if Stripe does not answer when reading the subscription again, nothing is applied and Stripe sends the notice again. A €0 charge makes no invoice. The late charge of an old invoice, with the subscription still unpaid, reactivates nothing.
Involved: the business (receives its status)

### BILLING-F21 Keep the plan in step with what Stripe says
<!-- origen: old-saas:SAAS_DASHBOARD-F99 gh:saas#2530 gh:saas#2540 -->
Status: done
Actor: system
Screen: none
Steps:
1. Stripe sends a notice that the business's subscription changed (price, status, period or cancellation).
2. erplora.com reads the live subscription again and finds the plan and the modules by their prices.
3. It saves plan, billing period, status, period and whether it is cancelled at the end of the period, also when the cancellation was made outside the panel.
In: the notice of the changed subscription.
Out: the business's subscription with what Stripe says (`hubs.subscription.changed`) and its plan sent to the business.
If it fails: a price that sells no plan leaves the plan as it was, but the status, the period and the cancellation are saved anyway and an alarm stays; an unknown subscription is not read from Stripe.
Involved: the business (receives its plan)

### BILLING-F22 See the invoices and download them
<!-- origen: old-saas:SAAS_DASHBOARD-F117 -->
Status: done
Actor: owner, paying account
Screen: Billing › Invoices
Steps:
1. In **Billing › Invoices** ERPlora's invoices of all the account's businesses are shown: Invoice, Date, Business, Amount and Status, from newest to oldest.
2. Filter by business, status ("Paid", "Not collected") and year, or search by number; the filters are kept in the address.
3. Tap "Download PDF" on a row (or select several and "Download PDF (n)"), or "Download Excel" for the list of what is filtered, ready for the accountant.
4. A credit note says "Credit note R1 · reason" and the invoice it corrects.
In: the invoices the account paid and those of the businesses it owns.
Out: the PDF of the issued invoice and the spreadsheet of what is filtered.
If it fails: an invoice still being issued says "Issuing" and offers no PDF; if the invoice service does not answer, "The invoice service is not answering. Try again in a moment"; without invoices, "No invoices yet". An invoice of another account is not found.
Involved: none

### BILLING-F23 See the subscriptions of each business
<!-- origen: old-saas:SAAS_DASHBOARD-F118 -->
Status: done
Actor: owner, paying account
Screen: Billing › Subscriptions
Steps:
1. In **Billing › Subscriptions** there is one row per paying business: the plan and its modules at their price without VAT (a cancelled module says "(until …)"), the next invoice with VAT and the status.
2. Each row has its actions: the main one in view ("View the invoice" if there is an uncollected one; otherwise "Change plan" or "Keep the plan") and in "⋮" "View invoices" and "Cancel plan".
In: the subscriptions of the businesses the account pays or owns.
Out: nothing.
If it fails: without paid businesses, "All your businesses are on Free" with "See plans"; without the payer's details, the next invoice cannot work out its VAT and it is said. An owner who does not pay only looks.
Involved: none

### BILLING-F24 Open Stripe's payment portal to change the card
<!-- origen: old-saas:SAAS_DASHBOARD-F120 gh:saas#2554 -->
Status: done
Actor: paying account
Screen: Billing › Payment details
Steps:
1. In **Billing › Payment details**, the "Payment method" card says which card pays which businesses and, if the last charge failed, when and for which business.
2. Tap "Change card": Stripe's secure page of that account opens, which only allows changing the card and seeing the receipts.
3. Back, the panel returns to Billing and, if there was a declined invoice, the notice says "Card changed" and "Pay" comes back.
In: the paying account of the business.
Out: the new card in Stripe; plan changes are never made there.
If it fails: before the first payment there is nothing to change; if Stripe does not answer, it is said; only the paying account opens it, never another owner.
Involved: none

### BILLING-F25 Issue ERPlora's invoice for a charge
<!-- origen: old-saas:SAAS_DASHBOARD-F130 gh:saas#2527 gh:saas#2528 -->
Status: done
Actor: system
Screen: none
Steps:
1. Stripe sends a notice of a paid charge (sign-up, renewal, plan change or module).
2. erplora.com qualifies the sale (BILLING-F03), gives it a number of its series (ERP-year-number, consecutive without gaps) and the day's date, and copies the payer's details of that day.
3. It sends it to ERPlora's platform business, which records it with VeriFactu and returns its status and its QR; when it issues it, the payer is told by email.
In: Stripe's charge with its lines and the payer's details.
Out: the invoice and its lines (`billing.invoice.recorded`), its tax status and the email.
If it fails: if the platform business does not answer, the invoice stays "issuing" and is retried (after 15 minutes, then double each time, at most 6 hours); if it refuses it, the reason is saved and it is retried. An uncollected renewal is listed "Not collected", without a number, and is numbered when paid. With live keys, without a way to issue, nothing is charged.
Involved: ERPlora's platform business (issues the invoice)

### BILLING-F26 Refund a charge
<!-- origen: old-saas:SAAS_DASHBOARD-F121 gh:saas#2527 -->
Status: done
Actor: ERPlora staff
Screen: none
Steps:
1. ERPlora staff refund a charge (in full or in part) or issue a credit note in Stripe's dashboard.
2. Stripe sends a notice to erplora.com, which issues a corrective invoice with negative amounts, the qualification and the recipient of the original, its type (R1 for refunds and price changes, R4 for the rest) and its reason.
3. The corrective invoice appears in **Billing › Invoices** with "Credit note R1 · reason" and the invoice it corrects.
In: the notice of the refund or the credit note.
Out: the corrective invoice of its own series (ERPR-year-number), issued as any invoice (`billing.credit_note.recorded`).
If it fails: a refund of an invoice that does not exist yet waits and Stripe sends the notice again; the same refund never corrects twice.
Involved: ERPlora's platform business (issues the corrective invoice)

### BILLING-F27 What ERPlora staff can do about a customer's billing
<!-- origen: old-saas:SAAS_DASHBOARD-F123 gh:saas#2529 gh:saas#2575 -->
Status: done
Actor: ERPlora staff
Screen: Admin
Steps:
1. A person of ERPlora enters the admin with the SaaS account (email code and authenticator app).
2. They see, read-only, the subscriptions and their lines, Stripe's notices and the payment attempts: what Stripe says is not edited here, it is changed in Stripe and arrives with its notice.
3. On the businesses they can "Send the latest state to the business" and "Retry what the business still owes"; on the invoices, "Send again to the platform business" and "Send the invoice email again".
4. They keep the promo codes, the VAT table, the tax policy and ERPlora's details; refunds and immediate cancellations are made in Stripe's dashboard.
In: the staff account with its role.
Out: what its actions do; nothing that belongs to Stripe changes from the admin.
If it fails: without the role, the admin does not open; the support group only looks, it does not run actions.
Involved: hubs (the businesses' status)

### BILLING-F28 Keep the plans' prices in Stripe
<!-- origen: old-saas:SAAS_DASHBOARD-F124 -->
Status: done
Actor: ERPlora staff
Screen: Admin › Plans
Steps:
1. A person of ERPlora creates in Stripe the plan's product and its monthly and annual prices, without VAT included.
2. In **Admin › Plans**, on the plan, they paste the product and its two Stripe prices next to the plan's monthly and annual price, and save.
3. When saving, erplora.com asks Stripe about each price and only accepts it if it exists with that environment's keys, is active, in euros, is charged every month (or every year) as its field says, charges the same as the plan, is without VAT and belongs to that product.
4. From that moment the plan is sold at that price; without its prices, it is not on sale.
In: the plan and its Stripe prices.
Out: the plan on sale with its prices checked.
If it fails: a price that does not match is not saved and says why under its field ("This price is not in euros", "Stripe charges … and the plan says …", "This price includes VAT or does not say…", a test price in production is not found…). If Stripe does not answer, it is not saved and it asks to try again; without Stripe keys (in development) it is saved and the admin warns that it was not checked. A plan without its Stripe price is not sold and the Store says so.
Involved: hubs (the plans' admin)

### BILLING-F29 Test real charging in PRE with a Stripe test clock
<!-- origen: old-saas:SAAS_DASHBOARD-F105 -->
Status: done
Actor: ERPlora staff
Screen: Admin › Businesses
Steps:
1. In PRE, a person of ERPlora creates a test business with a new account and fills in its billing details.
2. In **Admin › Businesses** they select that business and run "Attach its payer to a Stripe test clock (test keys only)": the admin says which clock its payer is on, born in Stripe attached to it.
3. From the panel, they subscribe to a normal plan with the test card.
4. Back in the admin they run "Advance its Stripe test clock by a month": the clock jumps a month from its own time and Stripe renews and charges as in production, with its notices (BILLING-F20).
In: the test business and PRE's test keys.
Out: a Stripe payer on a test clock and, when it is advanced, the renewal with its test invoice, without an internal €1 plan.
If it fails: with live keys the two actions are not even offered and, if they are asked for, they are refused before calling Stripe; a payer who is already a Stripe customer is not attached to a clock (Stripe only allows it when creating it); a clock still advancing is not advanced again ("try again in a minute"); a business without a clock says to attach it first. Only a superuser runs them; the support group only looks.
Involved: hubs (the businesses' admin)

### BILLING-F30 Use live Stripe keys only in production and test keys elsewhere
<!-- origen: old-saas:SAAS_DASHBOARD-F106 -->
Status: done
Actor: system
Screen: none
Steps:
1. On deploy, the SaaS's checks review the Stripe keys: in production only the restricted live key is valid; the account's secret key, never.
2. In PRE, any live key (secret, restricted or publishable) stops the deploy; in production, any test key too.
3. Even if the deploy got to start, the door to Stripe treats a key of the wrong environment as if there were no key: nothing is charged and the payment says it is not available.
4. The test tools (Stripe's clock) are refused with a live key.
In: the Stripe keys and the environment.
Out: nothing saved; the deploy stopped if the key is not the environment's.
If it fails: without a key, no payment starts and it says payments are not available; in development one always works with test keys.
Involved: none
