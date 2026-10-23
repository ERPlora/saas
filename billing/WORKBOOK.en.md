<!-- generated from WORKBOOK.md sha256:5f00728fbd5e4907adce02cadd7b8d30636a2c10f7223058c78c023039c64223 -->

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

**Modules** shows each paid app with its icon, its name, its summary and its price without VAT at the
business's period, and the one thing the business can do with it: "Add · …", "You have it" (or "Included in
your plan"), "Cancel module", "Keep · no charge today" on a cancelled one or "Activating… in …" right after
buying it. One no longer sold is only seen by the business that pays it, with "No longer sold".

### Secure payment
Dialog that opens when upgrading a business that does not pay yet: first "Who do we invoice?" (only the first
time), then Stripe's card form inside the dialog, with "Have a promo code?". When done, "Paying…" and the
business's page.

### Change plan
Dialog of a business that already pays: what is charged today prorated, the VAT, the total and what will be
charged afterwards, with "Pay … and change" (or "Change plan" if nothing is charged today, as in a downgrade,
which waits for the end of the period). Adding an app to a business that already pays opens the same dialog,
titled "Add …", with "Pay … and add".

### Billing
Menu **Billing**, with three tabs: **Invoices** (table with Invoice, Date, Business, Amount and Status;
filters by business, status and year; search by number; "Download PDF", "View invoice", "Download Excel"
and "Pay" on the uncollected ones), **Subscriptions** (one row per paying business: plan, modules, next invoice with VAT and
status; "Change plan", "Keep the plan", "View the invoice", "View invoices" and "Cancel plan") and **Payment
details** (the card with "Change card" and the billing details with "Edit details"). At the top of all three,
the notices of unpaid invoices.

### Invoice
Page of one invoice, opened with "View invoice": its number (or "not collected"), the date, the business, the
charge and its VeriFactu status; "What it charges", one line per item with its period, its base and its VAT;
the taxable base, the VAT and the total; and "Made out to", the payer's details as they were that day. At the
top, "Download PDF" once it is issued and "Pay" if it was not collected; a credit note links the invoice it
corrects. The arrow at the top goes back to Invoices.

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
| BILLING-F02 | Work out the tax of a sale from where the payer is | done |
| BILLING-F03 | Decide the VAT of each charge | done |
| BILLING-F04 | Keep the VAT rate table and never sell with it broken | done |
| BILLING-F05 | Check the payer's EU VAT number in VIES | done |
| BILLING-F06 | Follow the EU distance-selling threshold (OSS) | done |
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
| BILLING-F31 | See the paid apps and their state in each business | done |
| BILLING-F32 | Subscribe a business to a paid app | done |
| BILLING-F33 | Cancel a paid app | partial |
| BILLING-F34 | End a paid app at the end of its period | partial |
| BILLING-F35 | Take a paid app to another business | partial |
| BILLING-F36 | See an invoice | done |
| BILLING-F37 | Forget Stripe's notices older than 30 days | done |
| BILLING-F38 | Read the subscriptions again in Stripe every night and put right what drifted | done |

### BILLING-F01 Say where the business is invoiced and with which tax ID
<!-- origen: old-saas:SAAS_DASHBOARD-F90 fi:saas/orgs-users#informacion-de-facturacion-de-la-organizacion-ver-editar -->
Status: done
Actor: owner, paying account
Screen: Secure payment, Billing › Payment details
Steps:
1. The first time a plan or a module is paid, the payment dialog asks "Who do we invoice?": "Company name", "Tax ID (optional)", "Address", "City", "Postal code", "Country" and "Email for invoices (optional)", or "Use the business's name and country".
2. Tap "Continue to payment": the details are saved and the payment goes on. The following times the dialog only says "Invoiced to …" with "Change".
3. At any time, in **Billing › Payment details**, the "Billing details" card shows company name, tax ID, address, email and which businesses it pays, with "Edit details".
4. When an EU VAT number of another country is typed, the window checks it in VIES and says "Checked in VIES: … The invoice goes without VAT", "VIES does not recognise this number: the invoice will carry VAT" or "VIES is not answering now: we check it again when invoicing".
5. Tap "Save details": "Billing details saved". They apply to the next invoices and to what Stripe sends (the page to confirm a charge the bank wants authenticated, its receipts and its payment portal); the invoices already issued do not change.
In: what the person types; the business's country and name if they choose to use them.
Out: the business's billing details (shared by the businesses the same account pays), the VIES check recorded and, if the payer has ever paid, its customer record in Stripe up to date; the change is announced (`hubs.billing_profile.updated`).
If it fails: a Spanish postal code without five digits, a missing country or a tax ID that is not valid for its country are shown under their field and nothing is saved. After a transfer, if another account paid the business, the dialog says "Until now another account paid this business: say who pays from now on". If Stripe does not answer, the details are saved anyway and Stripe gets them with the next payment from the panel.
Involved: hubs (the business's and the payer's details)

### BILLING-F02 Work out the tax of a sale from where the payer is
<!-- origen: old-saas:SAAS_DASHBOARD-F91 -->
Status: done
Actor: system
Screen: none
Steps:
1. Before opening any payment (a plan, a plan change or a module), erplora.com reads the payer's country and postal code. Without both, the payment does not start and the billing details are asked for.
2. It qualifies the sale with the same rule the invoice uses afterwards: mainland Spain and the Balearic Islands, Spanish VAT; Canary Islands, Ceuta and Melilla, no VAT (the price is charged with nothing on top); another EU country with an EU VAT number checked in VIES, reverse charge, no VAT; a consumer in another EU country, Spanish VAT until the distance-selling threshold is passed and then their country's; United Kingdom, businesses only and no VAT.
3. If the total with VAT goes over €400 and the payer has no tax ID, the sale is refused and the tax ID is asked for (a simplified invoice cannot go beyond that).
4. The resulting rate travels to Stripe with each line of the subscription; Stripe only adds what it is given.
5. When the **billing details** are saved, the subscription already being charged takes the rate of the new place from the next invoice, without touching what is already paid (for example, someone who moves from Madrid to Las Palmas stops paying VAT). With a downgrade already scheduled, the rate of what will be charged at the change changes too, so the first invoice of the new plan already carries today's rate. A daily review repeats the same with every live subscription in case a change did not get through.
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
Status: done
Actor: ERPlora staff
Screen: Admin › Tax rules
Steps:
1. A person of ERPlora edits in the admin the **tax rules** (country, region, category, rate, subject or not, from and until) and the **categories**. The most specific rule wins.
2. The list shows what is needed to operate and is filtered by country and category; two rules of the same territory starting on the same day are refused when saving.
3. Every sale reads the table at that moment: a territory without a rule in force is not sold to.
4. Every day, the **review of the table** looks at every possible sale and goes red for the team, saying what to fix and where, if the rule of the invoicing country is missing, if the Canary Islands, Ceuta or Melilla stop going out without VAT (rule deleted, deactivated, marked as subject or a postal code that no longer recognises them) or if a country with a registered payer has no rate. A country only covered by the general backstop rate is a warning, not a failure.
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
Status: done
Actor: system, ERPlora staff
Screen: Admin › Tax policy, Admin › OSS notices
Steps:
1. Each invoice to a consumer in another EU country adds its base to the year's total (credit notes subtract); the total sold by the previous SaaS is loaded once by hand in **Tax policy**.
2. **Tax policy** shows the year's total against the threshold (€10,000 by default) and the switches of the OSS and ROI registrations.
3. Above the threshold (or with the voluntary OSS registration, or if the previous year closed above it) new sales to EU consumers carry the VAT of the customer's country.
4. The charged sale that takes the year's total past 80 % of the threshold sends a notice to the team's mailbox to start the OSS registration now, which takes days; the one that crosses it (or the first one of the year if the previous one closed above) sends another: from it those sales carry the VAT of the customer's country. Each notice goes out only once a year and stays in **Admin › OSS notices**, read-only.
5. The daily review of the live subscriptions moves those customers to their country's rate from the next invoice (and back to the Spanish one when the year returns to origin); what Stripe already has is not sent again.
In: the invoices and the policy.
Out: the rate of each new sale and that of the live subscriptions, and the notices to the team's mailbox.
If it fails: a business Stripe does not let change does not stop the review: it is retried the next day and the team sees it red. A notice that could not leave is sent again in the daily review, which stays red while any is left; noting the notice never stops the charge. While the year's total has not been loaded, the admin says "unknown" and with live keys nothing is sold (better not to sell than to cross the threshold without seeing it).
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
<!-- origen: old-saas:SAAS_DASHBOARD-F95 gh:saas#2527 pc:cloud/dashboard/hubs-pricing fi:saas/hubs#pagina-de-planes-precios fi:saas/hubs#stripe-gestion-de-suscripciones-servicio-interno fi:saas/support/hubs#service-stripeservice -->
Status: done
Actor: owner
Screen: Store, Secure payment
Steps:
1. In **Store › Plans**, with the business chosen at the top, the owner sees each plan with its price without VAT, its users and its devices, picks "Monthly" or "Annual" (which says how much is saved) and taps "Upgrade to …".
2. The secure payment opens: the billing details if they are missing and then Stripe's card form inside the dialog, titled "Upgrade to …" with "For … · renews every month" (or every year).
3. Enter the card; if the bank asks for authentication, Stripe shows it in the same form.
4. When done, "Paying…", the notice "… is now on …" and the business's page, whose Plan card changes as soon as Stripe confirms it. The business keeps working all the time.
In: the chosen plan (only those offered to that person), the period, the billing details and the promo code if there is one.
Out: the business on the new plan, its subscription and its customer in Stripe, the new plan sent to the business (`hubs.subscription.changed`) and ERPlora's invoice for the first charge (BILLING-F25), whether the payment notice arrives before or after.
If it fails: if the payment cannot be opened, "We could not open the secure payment" and "Nothing has been charged" with "Retry"; a plan without a price in Stripe, "is not on sale"; without billing details, the form; with an unpaid invoice, nothing is sold to that business. If the person closes the dialog, nothing is charged and the business stays on Free.
Involved: hubs (the business's subscription), the business (receives its plan)

### BILLING-F09 Come back from the payment: confirmed, pending or closed
<!-- origen: old-saas:SAAS_DASHBOARD-F93 old-saas:SAAS_DASHBOARD-F109 gh:saas#2566 fi:saas/hubs#paginas-de-resultado-de-pago-success-cancel fi:saas/public#paginas-de-resultado-de-pago-success-cancel -->
Status: done
Actor: owner
Screen: Secure payment, Business summary
Steps:
1. When the payment is finished in Stripe's form, the dialog says "Paying…", closes the form, says "… is now on …" (or "… added to …: it turns on in a few seconds" for a module) and opens the business's page.
2. The business's plan (or the app bought) changes when Stripe confirms the charge: if the payment method takes time to confirm, such as a SEPA direct debit, the business stays as it was until then and changes by itself, without reloading.
3. If the person closes the dialog before paying, nothing is charged and they can open it again (BILLING-F10); the business stays as it was and nothing is deleted.
In: the payment Stripe considers finished.
Out: the same new plan that Stripe's notice leaves (BILLING-F19); the return and the notice never apply the same payment twice.
If it fails: a payment that Stripe later considers failed closes that attempt without changing the plan; a payment for something else (a module) never changes the plan.
Involved: the business (receives its plan)

### BILLING-F10 Retry a payment that was not finished
<!-- origen: old-saas:SAAS_DASHBOARD-F94 gh:saas#2527 fi:saas/hubs#reintento-de-pago-retry-payment -->
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
<!-- origen: old-saas:SAAS_DASHBOARD-F96 fi:saas/hubs#cambio-de-plan-upgrade -->
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
<!-- origen: old-saas:SAAS_DASHBOARD-F100 old-saas:SAAS_DASHBOARD-F111 gh:saas#2529 gh:saas#2574 gh:saas#2593 gh:saas#2594 -->
Status: done
Actor: system, owner, paying account
Screen: Billing, Businesses, the business itself
Steps:
1. The charge of a renewal fails. Stripe retries it for some days and sends a notice of each failure. The paid apps go on the same invoice as the plan: their non-payment is that of the whole business, and paying brings everything back.
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
<!-- origen: old-saas:SAAS_DASHBOARD-F64 fi:saas/billing#api-rest-de-suscripciones-drf gh:saas#2529 gh:saas#2574 fi:saas/hubs#subscriptions-cancelar-reanudar-estado-stripe fi:saas/hubs#subscriptions-rest-listado-detalle-scoped-por-usuario fi:saas/support/billing-fiscal#serializer-subscriptionlistserializer-subscriptiondetailserializer -->
Status: done
Actor: owner, integration
Screen: none
Steps:
1. With their session, the owner (or an integration of their account, with a Billing read key) asks for the list of subscriptions: one row per business Stripe charges, with plan, modules, next invoice and status (the one Stripe gave in its last notice, BILLING-F21, or in the nightly pass, BILLING-F38). They can ask for only one business's or only those with one status.
2. They ask to cancel the plan at the end of the period or to keep it, with the same rules as the screen.
In: the account's session.
Out: the same as BILLING-F13 and BILLING-F14.
If it fails: a business that is not that account's is not found (filtering by it gives the empty list); keeping a plan with an unpaid invoice is refused; without a session, "You are not signed in". Those of every business are seen only by ERPlora staff, in the admin (BILLING-F27).
Involved: none

### BILLING-F19 Receive and validate a notice from Stripe
<!-- origen: old-saas:SAAS_DASHBOARD-F97 gh:saas#2530 gh:saas#2539 fi:saas/hubs#webhook-de-stripe-pagos-suscripciones fi:saas/support/billing-fiscal#modelo-webhookevent fi:saas/support/public-core-config#service-stripe_webhook-handlers-webhooks-py -->
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
Out: the notice's row with its type and its result, read-only in the admin for 30 days (BILLING-F37).
If it fails: an error while processing it is recorded and answered with an error, so that Stripe sends it again; the claim of a delivery that died halfway expires and the next one takes it over. Without the secret configured, Stripe receives "come back later".
Involved: none

### BILLING-F20 Renew the plan every period
<!-- origen: old-saas:SAAS_DASHBOARD-F98 old-saas:SAAS_DASHBOARD-F110 gh:saas#2527 gh:saas#2529 gh:saas#2530 gh:saas#2540 -->
Status: done
Actor: system
Screen: none
Steps:
1. At the end of each period Stripe charges the saved card and sends a notice of the charge. The business's paid apps are renewed in the same charge as the plan, one line each; a cancelled one whose period ended is no longer charged (BILLING-F34).
2. erplora.com reads the live subscription again and saves its new period and its status (a trial is still a trial).
3. If the business was unpaid, it is up to date again at once.
4. It records and numbers the invoice of that charge and sends it to be issued (BILLING-F25).
In: the notice of the paid charge.
Out: the period and status of the business's subscription and its invoice (`billing.invoice.recorded`).
If it fails: if Stripe does not answer when reading the subscription again, nothing is applied and Stripe sends the notice again. A €0 charge makes no invoice. The late charge of an old invoice, with the subscription still unpaid, reactivates nothing.
Involved: the business (receives its status)

### BILLING-F21 Keep the plan in step with what Stripe says
<!-- origen: old-saas:SAAS_DASHBOARD-F99 gh:saas#2530 gh:saas#2540 fi:saas/support/hubs#modelo-subscription-alias-hubsubscription -->
Status: done
Actor: system
Screen: none
Steps:
1. Stripe sends a notice that the business's subscription changed (price, status, period or cancellation).
2. erplora.com reads the live subscription again and finds the plan and the modules by their prices.
3. It saves plan, billing period, status, period and whether it is cancelled at the end of the period, also when the cancellation was made outside the panel.
In: the notice of the changed subscription.
Out: the business's subscription with what Stripe says (`hubs.subscription.changed`) and its plan sent to the business.
If it fails: a price that sells no plan leaves the plan as it was, but the status, the period and the cancellation are saved anyway and an alarm stays; an unknown subscription is not read from Stripe. A notice that never arrives is put right by the nightly pass (BILLING-F38).
Involved: the business (receives its plan)

### BILLING-F22 See the invoices and download them
<!-- origen: old-saas:SAAS_DASHBOARD-F117 fi:saas/billing#api-rest-de-facturas-drf fi:saas/billing#descarga-de-pdf-de-factura fi:saas/billing#exportar-facturas-a-csv fi:saas/billing#historial-de-compras-pagos fi:saas/billing#listado-de-facturas-invoices fi:saas/billing#redireccion-raiz-de-billing fi:saas/hubs#facturas-del-hub pc:cloud/dashboard/billing-invoices fi:saas/support/billing-fiscal#serializer-hubbasicserializer fi:saas/support/billing-fiscal#serializer-invoiceitemserializer fi:saas/support/billing-fiscal#serializer-invoicelistserializer-invoicedetailserializer fi:saas/support/billing-fiscal#service-invoicepdfgenerator-generate_invoice_pdf -->
Status: done
Actor: owner, paying account
Screen: Billing › Invoices
Steps:
1. **Billing** opens on **Invoices**, with ERPlora's invoices of all the account's businesses: Invoice, Date, Business, Amount and Status, from newest to oldest. What was paid for an app is a line of its business's invoice.
2. Filter by business, status ("Paid", "Not collected") and year, or search by number; the filters are kept in the address.
3. Tap "Download PDF" on a row (or select several and "Download PDF (n)"), or "Download Excel" for the list of what is filtered, ready for the accountant.
4. A credit note says "Credit note R1 · reason" and the invoice it corrects.
5. "View invoice" opens its page (BILLING-F36).
6. An integration of the account, with a Billing read key, reads the same list with the same filters, each invoice with its business, its lines, its VAT and who it is made out to, its PDF and the spreadsheet.
In: the invoices the account paid and those of the businesses it owns.
Out: the PDF of the issued invoice, which ERPlora's platform business makes on each download with its VeriFactu QR (BILLING-F25), and the spreadsheet of what is filtered.
If it fails: an invoice still being issued says "Issuing" and offers no PDF; if the invoice service does not answer, "The invoice service is not answering. Try again in a moment"; without invoices, "No invoices yet". An invoice of another account is not found.
Involved: none

### BILLING-F23 See the subscriptions of each business
<!-- origen: old-saas:SAAS_DASHBOARD-F118 fi:saas/billing#compras-de-modulos-purchases fi:saas/billing#suscripciones pc:cloud/dashboard/billing-purchases pc:cloud/dashboard/billing-subscriptions fi:saas/support/billing-fiscal#serializer-modulebasicserializer -->
Status: done
Actor: owner, paying account
Screen: Billing › Subscriptions
Steps:
1. In **Billing › Subscriptions** there is one row per paying business: the plan and its paid apps at their price without VAT (a cancelled one says "(until …)" and stops showing once it ends), the next invoice with VAT and the status.
2. Each row has its actions: the main one in view ("View the invoice" if there is an uncollected one; otherwise "Keep it with my card", "Change plan" or "Keep the plan") and in "⋮" "View invoices" and "Cancel plan".
In: the subscriptions of the businesses the account pays or owns.
Out: nothing.
If it fails: without paid businesses, "All your businesses are on Free" with "See plans"; without the payer's details, the next invoice cannot work out its VAT and it is said. An owner whose plan is charged to another account's card (the previous owner's after a transfer) sees "Paid with another account’s card": they neither change nor cancel it, they keep it with their card (HUBS-F28).
Involved: hubs (HUBS-F28: the plan of a business handed over)

### BILLING-F24 Open Stripe's payment portal to change the card
<!-- origen: old-saas:SAAS_DASHBOARD-F120 gh:saas#2554 fi:saas/orgs-users#portal-de-facturacion-stripe fi:saas/support/orgs-users#service-organizationstripeservice -->
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
<!-- origen: old-saas:SAAS_DASHBOARD-F130 gh:saas#2527 gh:saas#2528 fi:saas/support/billing-fiscal#modelo-invoice fi:saas/support/billing-fiscal#modelo-invoiceitem fi:saas/support/billing-fiscal#service-create_hub_invoice fi:saas/support/billing-fiscal#task-generate_invoice_pdf_async-regenerate_all_invoice_pdfs -->
Status: done
Actor: system
Screen: none
Steps:
1. Stripe sends a notice of a paid charge (sign-up, renewal, plan change or module).
2. erplora.com qualifies the sale (BILLING-F03), gives it a number of its series (ERP-year-number, consecutive without gaps) and the day's date, and copies the payer's details of that day.
3. It sends it to ERPlora's platform business, which records it with VeriFactu and returns its status and its QR; when it issues it, the payer is told by email.
In: Stripe's charge with its lines and the payer's details.
Out: the invoice and its lines (`billing.invoice.recorded`), its tax status and the email.
If it fails: if the platform business does not answer, the invoice stays "issuing" and is retried (after 15 minutes, then double each time, at most 6 hours); if it refuses it, the reason is saved and it is retried. An uncollected renewal is listed "Not collected", without a number, and is numbered when paid. A €0 charge makes no invoice, and the same charge notified several times makes only one. With live keys, without a way to issue, nothing is charged.
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
<!-- origen: old-saas:SAAS_DASHBOARD-F123 fi:saas/django-admin#admin-companyconfig-singleton fi:saas/django-admin#admin-invoice fi:saas/django-admin#admin-invoiceitem fi:saas/django-admin#admin-modulepurchase fi:saas/django-admin#admin-subscription fi:saas/django-admin#admin-subscription-2 fi:saas/hubs#admin-django-subscription-hub-subscriptions gh:saas#2529 gh:saas#2575 fi:saas/support/billing-fiscal#command-seed_company_036 fi:saas/support/billing-fiscal#modelo-companyconfig -->
Status: done
Actor: ERPlora staff
Screen: Admin
Steps:
1. A person of ERPlora enters the admin with the SaaS account (email code and authenticator app).
2. They see, read-only, the subscriptions and their lines, Stripe's notices and the payment attempts: what Stripe says is not edited here, it is changed in Stripe and arrives with its notice.
3. On the businesses they can "Send the latest state to the business" and "Retry what the business still owes"; on the invoices, with their lines, "Send again to the platform business", "Send the invoice email again" and "Download the PDF" of any invoice already issued.
4. They keep the promo codes, the VAT table, the tax policy and ERPlora's details (born with those of the Modelo 036, and the ones VIES sees of who asks); refunds and immediate cancellations are made in Stripe's dashboard.
5. A paid app some business has is not deleted from the catalog: the admin says which business has it and to take it off sale.
In: the staff account with its role.
Out: what its actions do; nothing that belongs to Stripe changes from the admin.
If it fails: without the role, the admin does not open; the support group only looks, it does not run actions. The PDF of an invoice not issued yet does not exist: the admin says so ("Not issued yet"), and if the platform business does not answer, it goes back to the invoice saying why.
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

### BILLING-F31 See the paid apps and their state in each business
<!-- origen: old-saas:SAAS_DASHBOARD-F107 gh:saas#2504 gh:saas#2535 -->
Status: done
Actor: owner
Screen: Store
Steps:
1. In **Store › Modules**, with the business chosen at the top, the owner sees each paid app with its icon, its name, its summary and its price without VAT at the business's period ("… /month + VAT" or "… /year + VAT"), in their language.
2. Each card says what the app is in that business: "Add · …" if it does not have it; "You have it" with "Cancel module" if it pays it; "Included in your plan" if it comes with the plan; "You have it until … (cancelled)" with "Keep · no charge today" if it is cancelled; "Activating… in …" right after buying it.
3. An app ERPlora no longer sells still shows to the business that pays it, with "No longer sold: you keep it while you pay it, and can cancel it whenever you want"; it is not offered to the other businesses.
In: the chosen business (only those that person owns), the app catalog and the business's subscription.
Out: nothing.
If it fails: "We could not load the prices" with "Retry"; without apps on sale, "There are no modules on sale right now"; with an unpaid invoice, what charges is disabled with "Pay the pending invoice first"; with annual billing, an app only sold monthly says "Only with monthly billing". The app does not sell: it says to go to erplora.com in the browser.
Involved: apps (the name, the summary and the icon of each app)

### BILLING-F32 Subscribe a business to a paid app
<!-- origen: old-saas:SAAS_DASHBOARD-F108 gh:saas#2566 gh:saas#2629 gh:saas#2639 gh:saas#2640 fi:saas/public#compra-de-un-modulo-stripe-embedded-checkout fi:saas/public#webhook-de-stripe-compras-de-modulos fi:saas/support/billing-fiscal#modelo-subscription fi:saas/support/public-core-config#modelo-modulepurchase fi:saas/support/public-core-config#service-send_module_purchase_email-send_vendor_sale_email-emails-py fi:saas/support/public-core-config#task-send_module_purchase_email_task-send_vendor_sale_email_task-tasks-py -->
Status: done
Actor: owner
Screen: Store, Change plan, Secure payment
Steps:
1. In **Store › Modules**, with the business chosen at the top, the owner taps "Add · …" on the app.
2. If the business already pays, the "Add …" dialog says "It is added to the subscription of …" and what is charged: "Today (prorated)", the VAT, the "Total today" and what will be charged "From …"; it is confirmed with "Pay … and add", which charges the saved card.
3. If the business is on Free, the secure payment opens with the app alone, as in BILLING-F08; an app has no trial days.
4. Notice "… added to …: it turns on in a few seconds"; the card says "Activating… in …" and then "You have it". The app goes on the same monthly (or annual) invoice as the plan.
In: the business, the app (only one on sale that the business does not have) and the business's period.
Out: the app in the business's subscription (`billing.module.added`), its invoice (BILLING-F25), whose email is the confirmation of the purchase, and the app sent to the business.
If it fails: an app the business already has is not sold twice; a retired or unknown one is not sold; a free one is not bought, it comes with every business; with an unpaid invoice, "Pay the pending invoice first"; if too much time went by, "The price was out of date: here it is again, check it before confirming"; a declined card adds nothing. With a payment method that takes time (SEPA direct debit), the app arrives when Stripe confirms the charge (BILLING-F09).
Involved: hubs (the business's subscription), the business (receives the app)

### BILLING-F33 Cancel a paid app
<!-- origen: old-saas:SAAS_DASHBOARD-F112 gh:saas#2535 gh:saas#2568 gh:saas#2589 -->
Status: partial — the business does not turn off an app that stopped being paid yet: today every app is on in every business
Actor: owner who pays
Screen: Store
Steps:
1. In **Store › Modules**, with the business chosen at the top, the owner taps "Cancel module" on an app it pays.
2. The "Cancel the module" dialog says "… keeps working in … until …; then it turns off and is not charged again", that nothing the business wrote with it is deleted and that until then it can be undone with "Keep".
3. Tap "Cancel module": "… cancelled: it works until …". The card says "You have it until … (cancelled)" with "Keep · no charge today", and **Billing › Subscriptions**, "(until …)".
4. "Keep · no charge today" undoes the cancellation: "… is kept: it renews on …".
In: the business's bought app (not one that comes with the plan).
Out: the app out of the subscription in Stripe without refunding anything, with its end date (`billing.module.cancelled`; when kept, `billing.module.kept`), and that date sent to the business.
If it fails: an app that comes with the plan is dropped by changing the plan; one the business does not have is not found; with a scheduled plan change, that is undone first; if Stripe refuses it or does not answer, the dialog stays open and says why. An app no longer sold is cancelled all the same, but cannot be kept; one that already ended is bought again. Keeping with an unpaid invoice is refused.
Involved: hubs (the business's subscription), the business (receives until when it has it)

### BILLING-F34 End a paid app at the end of its period
<!-- origen: old-saas:SAAS_DASHBOARD-F113 -->
Status: partial — the business does not turn off the ended app yet: today every app is on in every business
Actor: system
Screen: Store, Billing › Subscriptions
Steps:
1. The end date of a cancelled app arrives.
2. It is no longer sent to the business, the renewal no longer charges it, **Billing › Subscriptions** no longer lists it and the Store offers it again with "Add · …".
3. No data is deleted: if it is subscribed to again, the business has it as it was.
In: the app's end date.
Out: the business without the app from that day.
If it fails: if the plan is cancelled, its apps end with it (BILLING-F15).
Involved: the business (stops receiving the app)

### BILLING-F35 Take a paid app to another business
<!-- origen: old-saas:SAAS_DASHBOARD-F114 gh:saas#2589 -->
Status: partial — it depends on BILLING-F33: the business of origin does not turn the app off yet when it ends
Actor: owner
Screen: Store
Steps:
1. An app is not transferred: it is cancelled in one business and subscribed to in the other, as Square, Shopify, Toast, Clover and Lightspeed do.
2. In **Store › Modules**, with the business of origin chosen, the owner taps "Cancel module" (BILLING-F33): it keeps working there until the end of what was paid.
3. They choose the destination business at the top and tap "Add · …" (BILLING-F32): it is charged prorated on that business's subscription.
In: the two businesses, which they own.
Out: the same as BILLING-F33 in the origin and BILLING-F32 in the destination.
If it fails: the refusals of BILLING-F33 and BILLING-F32.
Involved: hubs (the subscriptions of the two businesses)

### BILLING-F36 See an invoice
<!-- origen: fi:saas/billing#detalle-de-factura -->
Status: done
Actor: owner, paying account
Screen: Invoice
Steps:
1. In **Billing › Invoices**, the person taps "View invoice" on a row.
2. The page says its number (or "Invoice … (not collected)"), the date, the business, the charge and its VeriFactu status; "What it charges", one line per item with its period, "Prorated" if it is, its base and its VAT; the taxable base, the VAT and the total; and "Made out to", with the payer's details as they were that day.
3. From it they download the PDF of an issued invoice, pay an uncollected one or, on a credit note, open the invoice it corrects. While it is being issued, the page turns by itself into its number and its QR.
4. The arrow at the top goes back to Invoices.
In: an invoice of the account.
Out: nothing.
If it fails: an invoice of another account is not found; if it does not load, "We could not load this invoice" with "Retry"; one still being issued says its PDF will be there when it ends. In the app it is seen, but not paid.
Involved: none

### BILLING-F37 Forget Stripe's notices older than 30 days
<!-- origen: fi:saas/support/billing-fiscal#task-cleanup_old_webhook_events -->
Status: done
Actor: system
Screen: none
Steps:
1. Every night, erplora.com deletes the Stripe notices it received more than 30 days ago, processed or not.
2. Those of the last 30 days stay: they are the ones Stripe can still send again and the ones the staff look at in the admin (BILLING-F27).
In: the notices kept (BILLING-F19).
Out: the notices older than 30 days deleted and, in the task's log, how many.
If it fails: the next night deletes what was left. Stripe only sends a notice again for 3 days, so a deleted one is never processed twice.
Involved: none

### BILLING-F38 Read the subscriptions again in Stripe every night and put right what drifted
<!-- origen: fi:saas/support/hubs#command-sync_subscriptions -->
Status: done
Actor: system
Screen: none
Steps:
1. Every night, erplora.com reads again in Stripe the subscription of every business that pays, one by one.
2. If something does not match (the plan, the period, a cancellation, a trial or an app changed in Stripe whose notice never arrived), it puts it right as that notice would have (BILLING-F21) and notes it for the team with what drifted.
3. A subscription still waiting for its first payment is left for the next night; a business on Free is not read.
In: the subscriptions Stripe charges.
Out: each subscription as Stripe says (`hubs.subscription.changed` if anything changed) and its plan sent to the business.
If it fails: a subscription Stripe does not know, or that could not be read, is not touched and the task ends with an error, which tells the team; a business that fails does not stop the others. It can run as a trial, writing nothing, to only see what drifted.
Involved: hubs (the business's subscription), the business (gets its plan)
