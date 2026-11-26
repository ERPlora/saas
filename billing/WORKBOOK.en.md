<!-- generated from WORKBOOK.md sha256:b9db280b26c90b052293d79e3feea9755d8e2c6366a649f16428dfaa0a83f7f3 -->

## What it is for and who it is for

Billing is what an account pays ERPlora for its businesses. Every business starts on **Free** and, when it
needs to, its owner moves it to a paid plan from the **Store**. ERPlora charges the card through Stripe, adds
the VAT that applies to where the payer is, and issues its own legal invoice for every charge, which is seen
and downloaded in **Billing**. For now it only sells to payers with a billing address in Spain; in the Canary
Islands, Ceuta and Melilla, only to businesses and professionals.

- One subscription per business: the plan and the modules bought go together and are charged on a single
  invoice a month (or a year).
- Cancelling never deletes anything: the business keeps its plan until the end of the paid period and then
  goes back to Free.
- If a charge fails, the business keeps working for 7 days while it is retried; then it is suspended until it
  is paid, without losing any data.

Today no app is paid: every app comes with every plan. What this
manual tells of the paid apps (the **Store › Modules** screen, and buying, cancelling, ending and taking one to
another business, BILLING-F31 to BILLING-F35) works and is tested, but is not used until there is one again.

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
"Annual · −n %"), its lines as on /pricing/ (after "All apps included" or "Everything in …", "Up to 40 apps
turned on at once", or "All the apps turned on at once" when the plan has no cap; then the messages a month, "Your own domain for your website (www.yourbusiness.com)" on the plans that include it and,
last, the trial), "Your current plan" on the one it has and each plan's button: "Upgrade to …",
"Change to …", "Change to annual · …" or "Downgrade to Free"; with the plan cancelled or a downgrade scheduled,
"Keep the plan". A plan that is not sold with the chosen period, because it lacks its Stripe price, has its button
disabled and says why under it: "Only with monthly billing", "Only with annual billing" or "Not on sale right now".
Each card shows its first five lines, with the button right under the price; "Show all
features" unfolds the rest in every card at once and "Show fewer" folds them again. A business ERPlora staff marked in the admin (BILLING-F27) also sees, last, the internal plan
"Payment Test (internal)"; no other business sees it. If the
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
details** (the card with "Change card" and the billing details with "Edit details"). Unpaid invoices are not
announced inside the tabs: they are announced in the bell of the top bar (Bell notices).

### Bell notices
The bell of the panel's top bar, on every screen. With an unpaid invoice it turns into a red pill with the number of
businesses that have one. A new notice arrives as a card at the top right (full width on a phone) and a few seconds
later settles in the bell. Tapping it opens the "Notifications" panel, with the most urgent business on top: "… has an
unpaid invoice", the amount, "… days left" (or "suspended"), what happens if it is not paid ("If it is not paid by …,
the business is suspended. Nothing is deleted.") and "Pay the invoice · …" with "Change card" beside it; if the bank
declined the card, only "Change card". The other businesses, in rows below. A notice cannot be dismissed: it goes away
when the invoice is paid. Whoever does not pay the business sees the notice without buttons and "Only the account that
pays this business can pay its invoices."; in the app, "To pay it, go to erplora.com in your browser."

### Invoice
Page of one invoice, opened with "View invoice": its number (or "not collected"), the date, the business, the
charge and its VeriFactu status; "What it charges", one line per item with its period, its base, its VAT and its discount if it has one;
the taxable base, the VAT and the total; and "Made out to", the payer's details as they were that day. At the
top, "Download PDF" once it is issued and "Pay" if it was not collected; a credit note links the invoice it
corrects. The arrow at the top goes back to Invoices.

### Business summary
On each business's page, the **Plan** card says which plan it is on, how many users and devices fit, how many
apps can be turned on at once ("Apps turned on at once": the number or "Unlimited") and, to the owner, the button
to upgrade or change it.

## States of each screen

| State | What the person sees |
|---|---|
| Loading | "Loading…" or the table's skeleton while the data arrives; "Working out what is charged today…" in a plan change. |
| Empty | Invoices: "No invoices yet" and "See plans"; Subscriptions: "All your businesses are on Free"; Payment details: "No card saved yet". |
| Error | "We could not load …" with "Retry"; a payment that does not open says "Nothing has been charged" with "Retry". If it could not be checked whether there are unpaid invoices, the bell's panel says "Could not load notifications" with "Retry". |
| Stripe not answering | The card: "We cannot show you the card right now: try again in a few minutes"; a payment: the notice that nothing has been charged. |
| Unpaid invoice | The bell of the top bar, red with its number; in its panel, the notice of each business with the amount, until when it works and "Pay the invoice · …"; with the card declined, "Change card". |
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
| BILLING-F12 | Give trial days or a discount with a promo code | done |
| BILLING-F13 | Cancel the plan at the end of the period | done |
| BILLING-F14 | Undo a pending cancellation or downgrade | done |
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
| BILLING-F33 | Cancel a paid app | done |
| BILLING-F34 | End a paid app at the end of its period | done |
| BILLING-F35 | Take a paid app to another business | done |
| BILLING-F36 | See an invoice | done |
| BILLING-F37 | Forget Stripe's notices older than 30 days | done |
| BILLING-F38 | Read the subscriptions again in Stripe every night and put right what drifted | done |
| BILLING-F39 | Check every day that Stripe sends a notice of everything erplora.com handles | done |
| BILLING-F40 | Get the billing report of a period for the accountant | done |
| BILLING-F41 | See which customers pay, on what plan, since when and how much | done |

### BILLING-F01 Say where the business is invoiced and with which tax ID
Status: done
Actor: owner, paying account
Screen: Secure payment, Billing › Payment details
Steps:
1. The first time a plan or a module is paid, the payment dialog asks "Who do we invoice?": "Company name", "Tax ID (optional)", "Address", "City", "Postal code", "Country" and "Email for invoices (optional)", or "Use the business's name and country". "Country" only offers Spain and says under it "For now ERPlora only invoices payers in Spain."; the tax ID says "Required in the Canary Islands, Ceuta and Melilla, where we only sell to businesses and professionals.".
2. Tap "Continue to payment": the details are saved and the payment goes on. The following times the dialog only says "Invoiced to …" with "Change".
3. At any time, in **Billing › Payment details**, the "Billing details" card shows company name, tax ID, address, email and which businesses it pays, with "Edit details".
4. When the tax ID is typed, the window says "Valid tax ID.". An EU VAT number of another country is checked in VIES and the window says "Checked in VIES: …. Billed in Spain, the invoice carries VAT.", "VIES does not recognise this number: the invoice will carry VAT" or "VIES is not answering now: we check it again when invoicing". "Checked in VIES: … The invoice goes without VAT" only shows when the sale is reverse charged, which does not happen today: only Spain is invoiced.
5. Tap "Save details": "Billing details saved". They apply to the next invoices and to what Stripe sends (the page to confirm a charge the bank wants authenticated, its receipts and its payment portal); the invoices already issued do not change. What Stripe sends carries only the current tax ID: the previous one is removed, and so is the tax ID when it is deleted.
In: what the person types; the business's country and name if they choose to use them.
Out: the business's billing details (shared by the businesses the same account pays), the VIES check recorded and, if the payer has ever paid, its customer record in Stripe up to date, with the current tax ID as its only one (none without one, or with an EU VAT number VIES has not checked); the change is announced (`hubs.billing_profile.updated`).
If it fails: a Spanish postal code without five digits, a missing country or a tax ID that is not valid for its country are shown under their field, with "Check the highlighted details." on top until something is corrected, and nothing is saved. A country other than Spain is shown under "Country" and on top with "For now ERPlora only invoices payers in Spain.", also when "Use the business's name and country" is ticked for a business outside Spain (which can exist: a business is created in any EU country), and nothing is saved. After a transfer, if another account paid the business, the dialog says "Until now another account paid this business: say who pays from now on". If Stripe does not answer, the details are saved anyway and Stripe gets them with the next payment from the panel. If Stripe does not let the previous tax ID be removed, the details are saved anyway, the payment goes on and the team sees it in the error log.
Involved: hubs (the business's and the payer's details)

### BILLING-F02 Work out the tax of a sale from where the payer is
Status: done
Actor: system
Screen: none
Steps:
1. Before opening any payment (a plan, a plan change, a module, keeping the plan after a transfer or keeping a cancelled module), erplora.com reads the payer's country and postal code. Without both, the payment does not start and the billing details are asked for. For now it only sells to payers in Spain: with another country the payment does not start and the dialog goes back to the details with "For now ERPlora only sells to payers billed in Spain: change the billing details." (`billing.country_not_sold`), also for a business with an EU VAT number checked in VIES.
2. It qualifies the sale with the same rule the invoice uses afterwards: mainland Spain and the Balearic Islands, Spanish VAT; Canary Islands, Ceuta and Melilla, no VAT (the price is charged with nothing on top) and only to businesses and professionals, who declare the IGIC or the IPSI themselves: without a tax ID the payment does not start and the dialog goes back to the details with "In the Canary Islands, Ceuta and Melilla we only sell to businesses and professionals: add the tax ID of the payer." (`billing.business_required`). The engine keeps the rules for outside Spain (reverse charge with an EU VAT number checked in VIES; a consumer in another EU country, Spanish VAT until the distance-selling threshold is passed and then their country's; United Kingdom, businesses only and no VAT) for what is already charged and for when selling abroad reopens, which is adding the country to the list of those sold to.
3. If the total with VAT goes over €400 and the payer has no tax ID, the sale is refused and the tax ID is asked for (a simplified invoice cannot go beyond that).
4. The resulting rate travels to Stripe with each line of the subscription; Stripe only adds what it is given.
5. When the **billing details** are saved, the subscription already being charged takes the rate of the new place from the next invoice, without touching what is already paid (for example, someone who moves from Madrid to Las Palmas stops paying VAT). What is already charged is never refused for the country nor for being a consumer in the Canary Islands, Ceuta or Melilla: whoever already paid from another country keeps renewing with the engine and only cannot buy anything new; cancelling is always possible. With a downgrade already scheduled, the rate of what will be charged at the change changes too, so the first invoice of the new plan already carries today's rate. A daily review repeats the same with every live subscription in case a change did not get through.
In: the payer's country, postal code and tax ID, the latest VIES check, the price without VAT and what is sold (plan or module).
Out: the rate of each line in Stripe, or the refusal with its reason.
If it fails: "Billing details are missing" leads to the form; a payer outside Spain or a consumer in the Canary Islands, Ceuta or Melilla goes back to the form with the reason; a territory without a rule in the table is not sold to; a UK consumer does not buy; over €400 without a tax ID asks for it. A €0 price is never refused. If Stripe does not answer when the details are saved, the details are saved anyway and the daily review applies the rate; if the new place is not sold to, the subscription keeps its rate and the daily review goes red for the team.
Involved: hubs (the payer's details)

### BILLING-F03 Decide the VAT of each charge
Status: done
Actor: system
Screen: none
Steps:
1. When pricing (before charging) and when invoicing (afterwards), the same engine qualifies the sale: domestic, not subject (Canary Islands, Ceuta, Melilla, United Kingdom), reverse charge or the VAT of the customer's country (distance sales above the threshold). Since today only Spain is sold to (BILLING-F02), the last two only show in what was already charged to a payer from another country.
2. When invoicing, it splits what Stripe charged into base and tax and stamps on the invoice the table's nominal rate (21 %, never a 21.01 % that comes from dividing cents).
3. If Stripe charged no tax on a sale subject to VAT, the invoice takes the VAT out of what was charged and leaves an alarm for the team: VAT is never left undeclared.
In: the payer's country, postal code and tax ID, their VIES check at the date of the charge, the tax policy and the rate table.
Out: the treatment, the rate, the base and the tax, stamped on each line of the invoice.
If it fails: if VIES does not answer and there is no earlier check, the invoice waits and Stripe sends the notice again: Spanish VAT is never put on a sale between EU businesses because VIES was not answering. If the lines do not add up to what was charged, the invoice is not issued and the alarm stays.
Involved: none

### BILLING-F04 Keep the VAT rate table and never sell with it broken
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
Status: done
Actor: system, ERPlora staff
Screen: Billing › Payment details, Admin › VAT checks
Steps:
1. When an EU VAT number of another country is typed in the billing details, and when charging, erplora.com asks VIES identifying itself with ERPlora's VAT number, so VIES returns the consultation number, which is the proof. A Spanish tax ID is not asked about; a British one is not in VIES. Since today only Spain is invoiced, the proof only takes the VAT off what was already charged to a business in another EU country.
2. Each answer is a new row that is never rewritten (checked, not valid, not available). Only a "checked" in force with its consultation number (or the manual override) allows invoicing without VAT.
3. Staff can ask again with the "Check now in VIES" action of **VAT checks**, or leave a manual "checked" with its reason, which records who and when.
4. Each person has 20 checks a minute and there is a global cap; only one check at a time per person.
In: the EU VAT number and the country.
Out: the history of checks (`billing.vat_check.completed`) and the consultation number stamped on the invoice.
If it fails: VIES not answering is "not available" and the sale carries VAT; past the cap, "Too many checks: wait a minute"; a number without a valid format is shown under the field. The checks admin only opens with the SaaS's sign-in, which asks for the email code and the authenticator app.
Involved: none

### BILLING-F06 Follow the EU distance-selling threshold (OSS)
Status: done
Actor: system, ERPlora staff
Screen: Admin › Tax policy, Admin › OSS notices
Steps:
1. Each invoice to a consumer in another EU country adds its base to the year's total (credit notes subtract); the total invoiced outside erplora.com is loaded once by hand in **Tax policy**. Since today only Spain is sold to (BILLING-F02), the total only grows with what was already charged to consumers in another country.
2. **Tax policy** shows the year's total against the threshold (€10,000 by default) and the switches of the OSS and ROI registrations.
3. Above the threshold (or with the voluntary OSS registration, or if the previous year closed above it) new sales to EU consumers carry the VAT of the customer's country.
4. The charged sale that takes the year's total past 80 % of the threshold sends a notice to the team's mailbox to start the OSS registration now, which takes days; the one that crosses it (or the first one of the year if the previous one closed above) sends another: from it those sales carry the VAT of the customer's country. Each notice goes out only once a year and stays in **Admin › OSS notices**, read-only.
5. The daily review of the live subscriptions moves those customers to their country's rate from the next invoice (and back to the Spanish one when the year returns to origin); what Stripe already has is not sent again.
In: the invoices and the policy.
Out: the rate of each new sale and that of the live subscriptions, and the notices to the team's mailbox.
If it fails: a business Stripe does not let change does not stop the review: it is retried the next day and the team sees it red. A notice that could not leave is sent again in the daily review, which stays red while any is left; noting the notice never stops the charge. While the year's total has not been loaded, the admin says "unknown" and with live keys nothing is sold (better not to sell than to cross the threshold without seeing it).
Involved: none

### BILLING-F07 Pay the plan of a newly created business
Status: done
Actor: owner
Screen: Business summary, Store, Secure payment
Steps:
1. The business is always born on Free (signing it up only asks for name, country and type of business).
2. In the Business summary, the Plan card says "Free" and offers "Upgrade plan" (on a paid plan, "Change plan"), which opens the Store with that business chosen. Only whoever manages the business's billing sees it, and only on the web: in the apps it says to go to erplora.com in the browser.
3. Choose the plan and the period and tap "Upgrade to …": the payment goes on as in BILLING-F08.
In: the newly created business and the plans offered to that business (the internal ones, only if ERPlora staff marked it in the admin, BILLING-F27).
Out: the same as BILLING-F08.
If it fails: the same refusals as BILLING-F08.
Involved: hubs (the sign-up and the business's page)

### BILLING-F08 Move a free business to a paid plan
Status: done
Actor: owner
Screen: Store, Secure payment
Steps:
1. In **Store › Plans**, with the business chosen at the top, the owner sees each plan with its price without VAT and its first features, such as its users and its devices; "Show all features" unfolds the rest, among them, when they fall beyond the fifth line, the apps it can have turned on at once and its own domain. The owner picks "Monthly" or "Annual" (which says how much is saved) and taps "Upgrade to …".
2. The secure payment opens: the billing details if they are missing and then Stripe's card form inside the dialog, titled "Upgrade to …" with "For … · renews every month" (or every year).
3. Enter the card; if the bank asks for authentication, Stripe shows it in the same form.
4. When done, "Paying…" until the business's page arrives, which says "… is now on …" and whose Plan card changes as soon as Stripe confirms it. The business keeps working all the time.
In: the chosen plan (only those offered to that business; the internal ones, only to one the staff marked), the period, the billing details and the promo code if there is one.
Out: the business on the new plan, its subscription and its customer in Stripe, the new plan sent to the business (`hubs.subscription.changed`) and ERPlora's invoice for the first charge (BILLING-F25), whether the payment notice arrives before or after.
If it fails: if the payment cannot be opened, "We could not open the secure payment" and "Nothing has been charged" with "Retry"; a plan without its Stripe price for the chosen period cannot be pressed: under its button it says "Only with monthly billing", "Only with annual billing" or "Not on sale right now", and asked through the API anyway it is refused, "This cannot be bought right now. Contact support." (`billing.not_on_sale`); a plan not offered to that business (an internal one without the mark, even if asked through the API) is refused before the payment opens, "There is no plan with this identifier"; without billing details, the form; with an unpaid invoice, nothing is sold to that business. If the person closes the dialog, nothing is charged and the business stays on Free.
Involved: hubs (the business's subscription), the business (receives its plan)

### BILLING-F09 Come back from the payment: confirmed, pending or closed
Status: done
Actor: owner
Screen: Secure payment, Business summary
Steps:
1. When the payment is finished in Stripe's form, the dialog says "Paying…", closes the form and opens the business's page; once that page is there, the dialog goes and the notice "… is now on …" (or "… added to …: it turns on in a few seconds" for a module) shows on it, naming the business paid for, just above its section bar and never over it, however long the page takes to arrive.
2. The business's plan (or the app bought) changes when Stripe confirms the charge: if the payment method takes time to confirm, such as a SEPA direct debit, the business stays as it was until then and changes by itself, without reloading.
3. If the person closes the dialog before paying, nothing is charged and they can open it again (BILLING-F10); the business stays as it was and nothing is deleted.
In: the payment Stripe considers finished.
Out: the same new plan that Stripe's notice leaves (BILLING-F19); the return and the notice never apply the same payment twice.
If it fails: a payment that Stripe later considers failed closes that attempt without changing the plan; a payment for something else (a module) never changes the plan. A payment completed by somebody who no longer owns the business (handed over with the payment open, HUBS-F28) is not applied: its subscription is cancelled, the charge is refunded in full (BILLING-F26 makes its corrective invoice), the attempt says "Refunded: no longer the owner" (`billing.checkout.refunded`) and they get "Your payment for … was refunded" with the link to Billing; if nothing was charged, "Your plan for … was cancelled". Once, even if Stripe repeats the notice; if Stripe does not answer, nothing is marked and Stripe sends it again.
Involved: the business (receives its plan)

### BILLING-F10 Retry a payment that was not finished
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
Status: done
Actor: paying owner
Screen: Store, Change plan
Steps:
1. In **Store › Plans** of a business that already pays, the owner taps "Change to …", "Change to annual · …" or "Change to monthly · …".
2. The dialog works out what is charged today ("Working out what is charged today…") and shows "Today (prorated)", the VAT, the "Total today" and what will be charged "Afterwards", with the note that the modules stay the same.
3. An upgrade is confirmed with "Pay … and change": it is charged at once with the saved card and the business moves to the new plan at once. A downgrade (a cheaper plan, or annual to monthly) charges nothing today: it moves to the new plan at the end of the paid period, and **Billing › Subscriptions** says "Changes to … on …" and its next invoice is already that plan's. Until that date it is undone with "Keep the plan", on that row and on the card of the current plan in the Store (BILLING-F14).
4. Notice: "… is now on …" (or "…, paid annually"); a downgrade, which waits, says "… moves to … on …" (or "… moves to …, billed monthly, on …").
In: the new plan and period and the business's subscription with its card; when the period changes, each module's price changes too.
Out: the plan changed (`billing.plan.changed`) or the downgrade scheduled (`billing.plan.change_scheduled`), with the table's VAT on each line, and the new plan sent to the business.
If it fails: "The price was out of date: here it is again, check it before confirming" if too much time went by; a declined card changes nothing; the same plan and period is no change; downgrading to Free is cancelling (BILLING-F13); with a pending cancellation, "Keep the plan first to change it"; with an unpaid invoice, "First, pay the pending invoice"; a plan or a period without its Stripe price cannot be pressed, as in BILLING-F08; over €400 without a tax ID asks for it.
Involved: the business (receives its plan), ASSISTANT-F25 (asked of the panel's assistant, which sends it here)

### BILLING-F12 Give trial days or a discount with a promo code
Status: done
Actor: ERPlora staff, owner
Screen: Admin › Discounts, Admin › Promo codes, Secure payment, Billing › Subscriptions
Steps:
1. A person of ERPlora creates a discount in the admin: a percentage (1 to 100) or an amount in euros, one of the two; how long it lasts (the first payment, a number of months, 1 to 36, or forever); the plans it applies to (none = every paid plan; never an app), whether it is active and a note. Below, its codes: the code, whether it is active, until when it is valid, how many uses and a note. A code can also give trial days (1 to 365) instead of a discount.
2. The owner, in the secure payment of a business that does not pay yet, taps "Have a promo code?", types it and taps "Apply". With trial days: "Code …: n days free before the first charge.". With a discount: "Code …: Free for 6 months.", "Code …: 20% off on the first payment." or "Code …: €10.00 off forever.".
3. With trial days, pay: the first charge comes when those days end.
4. With a discount, the secure payment warns, next to the card, "Free for 6 months. Then €29.99/month + VAT. Your card is not charged today." (without "Then" if it is forever, and without the last sentence if something is charged today); give the card and the plan starts now. Each invoice carries its discount on the plan's line, also the €0 one, numbered and registered in VeriFactu as any other; when the discount ends the regular price is charged without doing anything.
5. While it lasts, **Billing › Subscriptions** says "Free until …" (or "€10.00 off forever") and the next invoice with the discount. Moving up a plan keeps it; moving down too, on the renewal; an app is charged in full. If the business changes hands and the new owner keeps the plan with their card, the discount goes on: one forever, as it was; one for a number of months, for the whole months it has left (none if less than one); one on the first payment, already spent, does not come back.
In: the code (case and spaces do not matter).
Out: the trial days on the subscription, or the discount in Stripe and when it ends; the use counted once per business and per payer.
If it fails: an unknown, inactive, expired or used-up code (or one whose discount is turned off) says "This code is not valid or has already been used" and does not stop paying without it; trying codes has a cap per person; a code never goes past its number of uses: the use is held when the secure payment opens and given back if that payment is not completed. If the code stops being valid between checking it and paying, the payment does not start and says "This code is not valid or has already been used: remove it to pay without it.". A discount for a number of months only goes with monthly billing: with yearly, the payment does not start and says "This code’s discount lasts a number of months: choose monthly billing to use it."; a plan the discount does not name says "This code does not apply to the plan chosen."; in a change of plan, "This code gives a discount to a business that starts paying a plan, not to a change of plan.". While one for months lasts, moving to yearly says "This business has a discount until …: it can move to yearly billing after that date." and changes nothing. Moving to a plan the discount does not cover (it does not name it, or it was made after the code) is allowed: that plan is charged in full and Subscriptions no longer shows the discount. Cancelling is always allowed, and the plan ends at the end of the period. In the admin, once a code is used, its discount no longer changes its terms, and neither the discount nor the code can be deleted (they are turned off).
Involved: ERPlora's platform business (issues the discounted invoices, also the €0 ones, BILLING-F25)

### BILLING-F13 Cancel the plan at the end of the period
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
Involved: the business (receives the end date), ASSISTANT-F25 (asked from the panel's assistant, its card shows what the dialog says)

### BILLING-F14 Undo a pending cancellation or downgrade
Status: done
Actor: paying owner
Screen: Billing › Subscriptions, Store
Steps:
1. On the row of a business with its plan cancelled or with a downgrade scheduled ("Changes to … on …"), the owner taps "Keep the plan". In the Store, the card of the current plan says "Cancelled: … until … and then Free" or "Downgrade scheduled: … until … and then …", with "Keep the plan"; the card of the plan it moves to says "The business moves to … on …", with no button.
2. Notice: "… stays on …" or "… is kept: it renews on …". The row has a next invoice again.
In: the subscription with its end marked or with its downgrade scheduled.
Out: the subscription renews again in Stripe, with the status Stripe says (`billing.plan.kept`); a scheduled downgrade is undone and the row stops saying "Changes to … on …".
If it fails: with an unpaid invoice, a cancelled plan is not kept: it is paid first (a plan is not recovered without paying it). A scheduled downgrade is undone even with an unpaid invoice: it charges nothing and hands back no plan that was lost. Keeping a plan that was neither cancelled nor had a downgrade changes nothing.
Involved: none

### BILLING-F15 End the subscription: the business goes back to Free
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
Status: done
Actor: system, owner, paying account
Screen: Bell notices, the business itself
Steps:
1. The charge of a renewal fails. Stripe retries it for some days and sends a notice of each failure. The paid apps go on the same invoice as the plan: their non-payment is that of the whole business, and paying brings everything back.
2. erplora.com reads the subscription again in Stripe: if the retry already charged, it does nothing; if not, it records the invoice as "Not collected", with why it was not collected (card declined, authentication or failure).
3. **Grace**: for 7 days from the invoice that failed, the business keeps working with all its plan. The paying account receives an email, once per invoice: how much could not be charged, until what day it keeps working and the link to Billing to pay it (if the bank declined the card, to change it first). In the panel's top bar, the bell turns red and the notice "… has an unpaid invoice" arrives: the amount, "… days left" and "If it is not paid by …, the business is suspended. Nothing is deleted.", with "Pay the invoice · …" and "Change card" (only "Change card" if the bank declined it). It is one notice per business, the same on every screen.
4. **Suspension**: after the 7 days, or if Stripe runs out of retries, the business is suspended and the paying account receives another email, only once. The business does not open: neither from the panel nor from its own address, not even on the devices that already had the session open, which show "This business is suspended" with the way to ERPlora. The bell's notice says "suspended" and "It was suspended because of an unpaid invoice. Nothing is deleted: once it is paid it works again at once."
5. **Safety net**: every hour the businesses with their plan unpaid are gone over and their oldest open invoice is looked at, in case Stripe stopped retrying without sending another notice.
6. **Return**: when the invoice is paid (with "Pay the invoice", or because a retry collects it), the business is active again at once: "Invoice paid: … is up to date again", and its notice leaves the bell.
In: Stripe's notices of the failed charge and of the subscription, and the live subscription.
Out: the "Not collected" invoice, the emails to the payer and the business's status (payment pending, suspended or up to date) sent to the business (`hubs.subscription.changed`).
If it fails: if Stripe does not answer when reading the subscription again, nothing is applied and Stripe sends the notice again. A repeated notice of an invoice already paid does not reopen it. A later failure of the same unpaid episode does not move the grace date nor repeat the email. An email that could not go out is sent again in the hourly pass, which warns the team while any is left.
Involved: hubs (the business's status), the business (receives the status)

### BILLING-F17 Reactivate a suspended business by paying its invoice
Status: done
Actor: paying account
Screen: Bell notices, Billing › Invoices
Steps:
1. On the notice of the suspended business, in the bell of the top bar, the paying account taps "Pay the invoice · …" (if the bank declined the card, "Change card" first); it can also pay it from the invoice, in **Billing › Invoices**.
2. Stripe's payment page of that invoice opens; pay.
3. Back, "Invoice paid: … is up to date again" and the business works again with its data and its plan, without opening another subscription.
In: the unpaid invoice and its payment page in Stripe.
Out: the invoice paid and numbered (BILLING-F25), the business active and its status sent to the business.
If it fails: "Paying…" blocks a second click; only the paying account of the business can pay its invoice ("Only the account that pays this business can pay its invoices"); an invoice already paid or voided is not paid again. A business whose plan already ended is on Free and goes back to a paid plan from the Store (BILLING-F08).
Involved: hubs (the business's status), the business (opens again)

### BILLING-F18 See, cancel or keep the business's plan through the API
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
Status: done
Actor: owner, paying account
Screen: Billing › Invoices
Steps:
1. **Billing** opens on **Invoices**, with ERPlora's invoices of all the account's businesses: Invoice, Date, Business, Amount and Status, from newest to oldest. What was paid for an app is a line of its business's invoice.
2. Filter by business, status ("Paid", "Not collected") and year, or search by number; the filters are kept in the address.
3. Tap "Download PDF" on a row (or select several and "Download PDF (n)", the download icon with the number of those that have a PDF), or "Download Excel" for the list of what is filtered, ready for the accountant.
4. A credit note says "Credit note R1 · reason" and the invoice it corrects.
5. "View invoice" opens its page (BILLING-F36).
6. An integration of the account, with a Billing read key, reads the same list with the same filters, each invoice with its business, its lines, its VAT and who it is made out to, its PDF and the spreadsheet.
In: the invoices the account paid and those of the businesses it owns.
Out: the PDF of the issued invoice, which ERPlora's platform business makes on each download with its VeriFactu QR (BILLING-F25), and the spreadsheet of what is filtered.
If it fails: an invoice still being issued says "Issuing" and offers no PDF; if the invoice service does not answer, "The invoice service is not answering. Try again in a moment"; if in "Download PDF (n)" some fail and others are still being issued, a single notice says both (one download, one notice); without invoices, "No invoices yet". An invoice of another account is not found.
Involved: none

### BILLING-F23 See the subscriptions of each business
Status: done
Actor: owner, paying account
Screen: Billing › Subscriptions
Steps:
1. In **Billing › Subscriptions** there is one row per paying business: the plan and its paid apps at their price without VAT (a cancelled one says "(until …)" and stops showing once it ends), the next invoice with VAT (with a scheduled downgrade, that of the new plan and billing, with its apps at the price of that billing; keeping the plan brings back the current one's) and the status. A deleted business shows "Being deleted", as its page does, with no next invoice and nothing to change, until the next pass ends its subscription in Stripe; then it stops showing.
2. Each row has its actions: the main one in view ("View the invoice" if there is an uncollected one; otherwise "Keep it with my card", "Change plan" or "Keep the plan") and in "⋮" "View invoices" and "Cancel plan".
In: the subscriptions of the businesses the account pays or owns.
Out: nothing.
If it fails: without paid businesses, "All your businesses are on Free" with "See plans"; without the payer's details, the next invoice cannot work out its VAT and it is said. An owner whose plan is charged to another account's card (the previous owner's after a transfer) sees "Paid with another account’s card": they neither change nor cancel it, they keep it with their card (HUBS-F28).
Involved: hubs (HUBS-F28: the plan of a business handed over; HUBS-F18: a deleted business)

### BILLING-F24 Open Stripe's payment portal to change the card
Status: done
Actor: paying account
Screen: Billing › Payment details, Bell notices
Steps:
1. In **Billing › Payment details**, the "Payment method" card says which card pays which businesses and, if the last charge failed, when and for which business.
2. Tap "Change card" (there or on the bell's notice of a business with an unpaid invoice): Stripe's secure page of that account opens, which only allows changing the card and seeing the receipts.
3. Back, the panel returns to Billing and, if there was a declined invoice, its bell notice says "Card changed: you can pay it now." and "Pay the invoice · …" comes back.
In: the paying account of the business.
Out: the new card in Stripe; plan changes are never made there.
If it fails: before the first payment there is nothing to change; if Stripe does not answer, it is said; only the paying account opens it, never another owner.
Involved: none

### BILLING-F25 Issue ERPlora's invoice for a charge
Status: done
Actor: system
Screen: none
Steps:
1. Stripe sends a notice of a paid charge (sign-up, renewal, plan change or module).
2. erplora.com qualifies the sale (BILLING-F03), gives it a number of its series (ERP-year-number, consecutive without gaps) and the day's date, and copies the payer's details of that day.
3. It sends it to ERPlora's platform business, which records it with VeriFactu and returns its status and its QR; when it issues it, the payer gets an email with the invoice's PDF attached and no links: "The invoice is attached. You can also find it in your panel, under Billing.".
In: Stripe's charge with its lines and the payer's details.
Out: the invoice and its lines (`billing.invoice.recorded`), its tax status and the email with its PDF.
If it fails: if the platform business does not answer, the invoice stays "issuing" and is retried (after 15 minutes, then double each time, at most 6 hours); if it refuses it, the reason is saved and it is retried. If it does not hand over the PDF yet, the email does not go without it: it is sent again in the next pass. An uncollected renewal is listed "Not collected", without a number, and is numbered when paid. A €0 charge of a trial makes no invoice; the one of a code's discount does (BILLING-F12), with the discount on each line. The same charge notified several times makes only one. With live keys, without a way to issue, nothing is charged.
Involved: ERPlora's platform business (issues the invoice)

### BILLING-F26 Refund a charge
Status: done
Actor: ERPlora staff
Screen: none
Steps:
1. ERPlora staff refund a charge (in full or in part) or issue a credit note in Stripe's dashboard.
2. Stripe sends a notice to erplora.com, which issues a corrective invoice with negative amounts, the qualification and the recipient of the original, its type (R1 for refunds and price changes, R4 for the rest) and its reason.
3. The corrective invoice appears in **Billing › Invoices** with "Credit note R1 · reason" and the invoice it corrects.
In: the notice of the refund or the credit note.
Out: the corrective invoice of its own series (ERPR-year-number), issued as any invoice (`billing.credit_note.recorded`), and its email with the PDF attached: "The credit note is attached. You can also find it in your panel, under Billing.".
If it fails: a refund of an invoice that does not exist yet waits and Stripe sends the notice again; the same refund never corrects twice. A credit note voided in Stripe (only possible while its invoice is not paid) never becomes a corrective invoice, even if its notice arrives later; and if it already was one, the corrective invoice is not touched —an invoice sent to the AEAT is not modified— and support gets an email to issue by hand the invoice that cancels it.
Involved: ERPlora's platform business (issues the corrective invoice)

### BILLING-F27 What ERPlora staff can do about a customer's billing
Status: done
Actor: ERPlora staff
Screen: Admin
Steps:
1. A person of ERPlora enters the admin with the SaaS account (email code and authenticator app).
2. They see, read-only, the subscriptions and their lines, Stripe's notices, the payment attempts, the promo codes used, the counters of each invoice series and the plan changes waiting for the end of the period: what Stripe says is not edited here, it is changed in Stripe and arrives with its notice.
3. On the businesses they can "Send the latest state to the business" and "Retry what the business still owes" and, a superuser only, "Let its owner buy the internal plans" and "Stop selling it the internal plans": with the mark, the owner of that business sees "Payment Test (internal)" (1 € + VAT) in the Store and buys it like any plan, in production too, to make a real purchase and see its invoice with the QR; the list's "internal plans" column says which businesses have it. On the invoices, with their lines, "Send again to the platform business", "Send the invoice email again", "Download the PDF" of any invoice already issued and, choosing several in the list, "Download the PDFs (ZIP)"; from the list, the "Billing report" of a month, a quarter or a year (BILLING-F40). In **Paying customers**, which businesses pay, on what plan, since when and how much, with its Excel (BILLING-F41).
4. They keep the promo codes, the VAT table, the tax policy and ERPlora's details (born with those of the Modelo 036, and the ones VIES sees of who asks); refunds and immediate cancellations are made in Stripe's dashboard.
5. A paid app some business has is not deleted from the catalog: the admin says which business has it and to take it off sale.
In: the staff account with its role.
Out: what its actions do; nothing that belongs to Stripe changes from the admin. Removing the mark does not cancel an internal plan already bought: the business still sees it as its plan and can no longer buy it.
If it fails: without the role, the admin does not open; the support group only looks, it does not run actions. The PDF of an invoice not issued yet does not exist: the admin says so ("Not issued yet"), and if the platform business does not answer, it goes back to the invoice saying why. In the ZIP, the invoices without a PDF (still being issued, or that the platform business does not return) are left out with their reason, in an admin notice and in `not-included.txt` inside the ZIP; if none has a PDF, nothing is downloaded and the notice says so.
Involved: hubs (the businesses' status)

### BILLING-F28 Keep the plans' prices in Stripe
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
If it fails: a price that does not match is not saved and says why under its field ("This price is not in euros", "Stripe charges … and the plan says …", "This price includes VAT or does not say…", a test price in production is not found…). If Stripe does not answer, it is not saved and it asks to try again; without Stripe keys (in development) it is saved and the admin warns that it was not checked. A plan without its Stripe price for a period is not sold with that period: in the Store its button is disabled and says why (BILLING-F08).
Involved: hubs (the plans' admin)

### BILLING-F29 Test real charging in PRE with a Stripe test clock
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
Status: done
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
Status: done
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
Status: done
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
Status: done
Actor: owner, paying account
Screen: Invoice
Steps:
1. In **Billing › Invoices**, the person taps "View invoice" on a row.
2. The page says its number (or "Invoice … (not collected)"), the date, the business, the charge and its VeriFactu status; "What it charges", one line per item with its period, "Prorated" if it is, its base and its VAT, and its "Discount" if a code lowered it; the taxable base, the VAT and the total; and "Made out to", with the payer's details as they were that day.
3. From it they download the PDF of an issued invoice, pay an uncollected one or, on a credit note, open the invoice it corrects. While it is being issued, the page turns by itself into its number and its QR.
4. The arrow at the top goes back to Invoices.
In: an invoice of the account.
Out: nothing.
If it fails: an invoice of another account is not found; if it does not load, "We could not load this invoice" with "Retry"; one still being issued says its PDF will be there when it ends. In the app it is seen, but not paid.
Involved: none

### BILLING-F37 Forget Stripe's notices older than 30 days
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

### BILLING-F39 Check every day that Stripe sends a notice of everything erplora.com handles
Status: done
Actor: system
Screen: none
Steps:
1. Every day, erplora.com reads in Stripe the destinations of its notices.
2. It checks that an enabled one points at its notice address (`/webhooks/stripe/`) and that it sends exactly the notices erplora.com handles (BILLING-F19), not one fewer and not one more.
3. If everything matches, it notes it and ends; if not, it ends with an error, which tells the team, saying what is missing and what is extra.
In: the notice destinations of the Stripe account.
Out: nothing that changes: what was seen and, if something does not match, the warning to the team.
If it fails: no enabled destination to the address, one that points at a route erplora.com does not serve or at another environment, more than one to the address, or one that sends every notice (`*`) or misses or adds any, ends with an error and names it. If Stripe does not answer, too. Without a Stripe key (in development) there is nothing to check: it says so and ends well.
Involved: none

### BILLING-F40 Get the billing report of a period for the accountant
Status: done
Actor: ERPlora staff
Screen: Admin › Invoices › Billing report
Steps:
1. In the admin, on the **Invoices** list, press "Billing report".
2. It opens on the current quarter; choose the year and the period (the whole year, a quarter or a month) and press "Show".
3. Read the period's totals: tax base, VAT and total of the invoices (ERP series), of the credit notes (ERPR series, negative) and the net of both.
4. Below, the breakdown by tax treatment, customer's country and VAT rate, taken from the lines as they reached VeriFactu (domestic goes to form 303, reverse charge to form 349 and the One-Stop Shop, OSS, to form 369), and the breakdown by kind of customer: company (a Spanish tax ID of a company or a tax ID from outside Spain), self-employed or individual with a Spanish tax ID, and individual without a tax ID.
5. Press "Download Excel": one row per invoice of the period with its number, date, business, payer, tax ID, country, tax treatment, VAT %, base, VAT, total, currency, payment and status, in the format of the panel's Excel (BILLING-F22).
In: the year and the period.
Out: the totals on screen and the spreadsheet for the accountant; nothing changes.
If it fails: only invoices collected and already issued by the platform business count, by their issue date; those collected in the period that are still being issued or that the platform business rejected do not add up, and a notice names them ("Collected in this period but not issued yet, so not counted: …"). A period that does not exist shows the error next to the field, and its Excel goes back to the report. Without invoices in the period, the totals are zero and the breakdown says "Nothing was invoiced in this period". Whoever cannot see the invoices in the admin does not open it.
Involved: none

### BILLING-F41 See which customers pay, on what plan, since when and how much
Status: done
Actor: ERPlora staff
Screen: Admin › Billing › Paying customers
Steps:
1. In the admin, open **Billing › Paying customers**: one row per business Stripe charges today (also when it is on a trial, has a payment pending or is paused), in order of business.
2. Each row says the business, who pays for it (its payer's legal name), their country, the kind of customer (company, self-employed or individual with a Spanish tax ID, or individual without a tax ID, as in the billing report, BILLING-F40), the plan, whether it pays monthly or yearly, the monthly amount before VAT, since when it is a customer and the status of its subscription.
3. The monthly amount is the tax base of its last invoice collected for a whole period, with its paid apps and without the prorations of a change in the middle of a period; a yearly one, divided by 12. "Customer since" is the date of its first collected invoice.
4. Filter by plan, status or country (each filter offers only what some paying customer has) or search by business, payer or tax ID.
5. Press "Download Excel": one row per customer of what the list shows (with its filters and its search) and the same columns, in the format of the billing report's Excel (BILLING-F40).
In: the filters and the search.
Out: the list on screen and the spreadsheet; nothing changes.
If it fails: a business without any collected invoice yet (on a trial with a promo code) shows the amount and "customer since" empty ("-"). A subscription that ended (cancelled, or expired without ever being paid) is no longer a paying customer and does not show. Without paying customers, the list says "0 paying customers". Whoever cannot see the subscriptions in the admin neither sees nor downloads it.
Involved: hubs (the subscriptions and the payers of the businesses)
