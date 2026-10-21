<!-- generated from WORKBOOK.md sha256:899c55989f4e4c68dfa287c876e89b0d83f6429728cbd0bb8f274195b0f4911d -->

## What it is for and who it is for

A business is where the work happens: its till, its calendar and its data, with its own web address
(`<nombre>.erplora.com`). An erplora.com account creates its businesses, sees them in a list and enters them
without typing the password again. Every business is born on the Free plan, without a card; the plan is changed
afterwards.

- Each account has one free business; to create another, the first one moves to a paid plan first.
- A business just created takes a few seconds to be ready: meanwhile it shows "Preparing" and, if the person has
  just created it, it is entered by itself as soon as it is ready.
- The installed app (Windows and Android) starts on the same entrance screen as erplora.com and, when it opens a
  business, stays linked to it to use the printer, the drawer and the rest of the hardware.

Who uses it:

- **Anyone with an account** creates their business and enters the businesses they are a member of.
- **The owner** sees the list of their businesses, recovers a deleted one and changes its plan.
- **ERPlora's staff** keep the plans from the admin.

## Reference adopted

- **Shopify and Square**: creating the shop asks only for the name and the country, with the address proposed while
  typing; the shop is born on a trial or free plan and the plan is chosen afterwards
  (https://help.shopify.com/en/manual/intro-to-shopify/initial-setup/sign-up).
- **Vercel and Netlify**: a list of projects with their status ("Building", "Ready", "Error") that changes by
  itself, and the waiting screen that goes in by itself as soon as it is ready (https://vercel.com/docs/deployments).
- **Odoo and Toast**: a single sign-in for several businesses, with the last one used on top and the choice of
  where to work (https://www.odoo.com/documentation/18.0/applications/general/users.html).
- **Stripe**: the plans and their prices are kept by the staff in a panel of their own, with the name and the
  description in each language of sale (https://docs.stripe.com/products-prices/manage-prices).

## Before you start

- One signs in at erplora.com. In development, the panel is on port 8001 and every email stays in the local mail
  folder instead of being sent.
- For a business to go from "Preparing" to "Active", the businesses' service has to be running: it is the one
  that reports it ready.

## Screens

### Entrance (erplora.com and the installed app)
The centred card of erplora.com, the same one the installed app opens when it starts. Without a session, the form
to sign in or create the account. With a session and no businesses, "Create your business" with the sign-up form;
with one business, "Hello, …" with "Open …" and "Go to the panel"; with several, "Where are you working today?"
with the last opened on top. A pending invitation shows above.

### Create business
The sign-up form: "What is your business called?", "Business name", "Country" (suggested by the browser's
language), "Business type (optional)" with "I don't know yet" and, under the name, "Your address will be …". On the
Entrance it is in the card; in **Businesses**, in the "Create business" dialog.

### Preparing
The running bar and three steps: "Business created", "Setting up your business" (or "Installing the modules for …")
and "It opens by itself when it finishes" on the Entrance or "Ready to open" in the dialog.

### Businesses
The panel's home: the list of the account's businesses with "Business", "Web address", "Status", "Plan", "Role"
and "Last used", the search box, "Create business" and, per row, "Open", "Manage" and "Recover". On the phone
they are cards. Above, the invitations, the ownership offers and the unpaid invoices.

### Business summary
Each business's page opens on its Summary: the plan (with "Upgrade plan" or "Change plan"), the usage and the "On
your devices" card with the business's web address, "Copy address" and the apps for Windows and Android.

### Your business is being prepared
The page the address of a business still being prepared shows: "Your business is being prepared" and "It takes a
few seconds. This page refreshes by itself.".

### admin › Businesses › Plans
Each plan's form for the staff: the texts in English and in Spanish, the price, what it includes, its limits and
its Stripe prices.

## States of each screen

| State | What the person sees |
|---|---|
| Loading | The list and the Entrance show their skeleton; "Create my business" is switched off while the request runs. |
| Empty | Without businesses, the list and the Entrance are the "Create your first business" form ("Free and no card: just the name and the country."). A search without results: "Nothing matches the search" with "Show all". |
| Error | "We could not load your businesses" with "Retry"; a business that could not be prepared: "Not prepared" and "We could not prepare it. We keep retrying; if it keeps failing, contact us.". |
| Preparing | The row says "Preparing" and "We are preparing it. It opens by itself when it is ready."; "Open" waits. |
| Offline | "Reconnecting… what you see may be a few seconds old." while the live connection comes back. |
| No permission | A business of another account does not exist for that person: it is neither listed nor opened. |

## Flows

| ID | Flow | Status |
|---|---|---|
| HUBS-F01 | Create the free business with a single question | done |
| HUBS-F02 | Create the free business from the installed app | done |
| HUBS-F03 | Take out a paid business | done |
| HUBS-F04 | Wait for the business to be ready and go in by itself | done |
| HUBS-F05 | Keep the plans in the admin | done |
| HUBS-F06 | See "your business is being prepared" | done |
| HUBS-F07 | Mark the business as ready | done |
| HUBS-F08 | Retry what the business did not receive | done |
| HUBS-F09 | See the list of businesses | done |
| HUBS-F10 | See the panel's home | done |
| HUBS-F11 | Enter a business from erplora.com | done |
| HUBS-F12 | Choose the business in the installed app | done |
| HUBS-F13 | Open the business on another device | done |
| HUBS-F14 | See the businesses through the API | done |

### HUBS-F01 Create the free business with a single question
Status: done
Actor: anyone with an account
Screen: Entrance › Create business
Steps:
1. After creating the account and signing in without any business, the Entrance shows "Create your business" ("Free and no card: just the name and the country.").
2. They type the "Business name"; underneath appears "Your address will be …" with the address the name proposes. The "Country" comes suggested by the browser's language and the "Business type (optional)" accepts "I don't know yet".
3. They press "Create my business": "Business created: …" shows and the card moves to **Preparing** (HUBS-F04).
In: the name, the country (one of the 27 of the European Union where ERPlora sells) and, if the person knows it, the business type; the account's session.
Out: the business on the Free plan (without a card and without a trial), with the person as owner, its address taken from the name (if it is taken it is numbered, `bar-manolo-2`; a reserved word is completed by itself) and who pays, with the business's country. The businesses' service receives the sign-up as soon as it is saved and, with the business type, the modules of its sector. Records `hubs.business.created`.
If it fails: without a name, "Write the name of your business." and nothing is sent; a country outside the list, the error on the field. If the account already has its free business, it does not create another: the dialog says "You already have a free business" and offers "Change the plan of …". Without the Free plan available, "Businesses cannot be created right now. Try again in a few minutes.". An account of ERPlora's staff does not create businesses. Two presses in a row create a single one.
Involved: accounts (the account and the Entrance), the business (receives its sign-up)

### HUBS-F02 Create the free business from the installed app
Status: done
Actor: anyone with an account
Screen: Entrance (in the installed app) › Create business
Steps:
1. The freshly installed app starts on the Entrance of erplora.com; without a session, the person signs in or creates their account right there.
2. Without any business, the Entrance shows "Create your business" with the same form as HUBS-F01 (name, country and optional type, with the address proposed while typing).
3. They press "Create my business": the card moves to **Preparing** and, when the business is ready, the app goes into it by itself and stays linked to that business (HUBS-F12).
In: the same as HUBS-F01.
Out: the same as HUBS-F01, with the country and the business type the person chooses (the old app did not ask for them).
If it fails: the same notices as HUBS-F01. Inside the app nothing is sold: to change the plan it says "To change your plan or add modules, go to erplora.com in your browser.".
Involved: accounts (the Entrance), the installed app (starts on the Entrance and links to the business)

### HUBS-F03 Take out a paid business
Status: done
Actor: owner, integration
Screen: Businesses › Create business, Business summary, Store
Steps:
1. In **Businesses**, "Create business" opens the dialog with the form of HUBS-F01; the business is born on Free.
2. In the Business summary, the plan card offers "Upgrade plan", which opens the Store with that business chosen.
3. They choose the plan and the period and pay with Stripe's secure payment (BILLING-F07 and BILLING-F08); the business keeps working all the time and changes plan as soon as Stripe confirms it.
4. An integration does the same with the account's session: it creates the business and then starts its payment.
In: the same as HUBS-F01 and, to pay, the plan, the period, the billing details and the card.
Out: the business created as in HUBS-F01 and, on paying, its paid subscription (`hubs.subscription.changed`), with the new plan sent to the business.
If it fails: the same notices as HUBS-F01 when creating and those of BILLING-F08 when paying; if the person closes the payment, nothing is charged and the business stays on Free, working. An account's second business is created after moving the first one to a paid plan.
Involved: billing (the payment and the plan), the business (receives its plan)

### HUBS-F04 Wait for the business to be ready and go in by itself
Status: done
Actor: owner
Screen: Preparing
Steps:
1. After "Create my business", the Entrance shows "Preparing …" ("It usually takes a few seconds.") with the bar and the three steps; in **Businesses**, the dialog shows the same and the row says "Preparing".
2. The screen updates by itself: there is no need to reload or to stay ("Go to the panel meanwhile").
3. When the business is ready, the Entrance takes the person into the business without asking for the password again; the dialog of **Businesses** says "Your business is ready" with "Open business".
4. The owner also gets the email "… is ready" with the link to open it and the one to its page in the panel.
In: the notice that the business is ready (HUBS-F07).
Out: the entry into the business with a one-time pass, which never travels in the address; the "is ready" email, only once.
If it fails: if the business could not be prepared, the screen says "It could not be prepared" and "We saved …, but it could not be prepared. We keep retrying; if it keeps failing, contact us.", and goes in by itself if the retry (HUBS-F08) fixes it. With several businesses it goes into none by itself: the person chooses.
Involved: accounts (the jump into the business), the business (reports it is ready)

### HUBS-F05 Keep the plans in the admin
Status: done
Actor: ERPlora's staff
Screen: admin › Businesses › Plans
Steps:
1. The staff open the list of plans, search by identifier or name and filter by "active", "only as an upgrade" or "internal".
2. In a plan's form they write its name, its description, the lines of its card and its badge in English and in Spanish, its monthly and annual price, what it includes (module level, support, own domain, businesses, devices and people), the limits of its database, the assistant and WhatsApp messages per month and its Stripe prices.
3. They save: the customer sees the texts in their language (English when the Spanish is missing) in the Store and on the pricing web page.
In: what the staff type.
Out: the plan, with each text in English and in Spanish. Free is offered at sign-up and without a trial; Pro, Enterprise and Max only as an upgrade; an internal plan is never offered to customers.
If it fails: a price Stripe refuses is not saved and the plan stays as it was; without Stripe, it is saved and warns that it was not checked. An account without the staff mark does not get into the admin.
Involved: billing (the prices in Stripe, BILLING-F28), public (the pricing web page)

### HUBS-F06 See "your business is being prepared"
Status: done
Actor: anyone
Screen: Your business is being prepared
Steps:
1. Whoever opens the address of a business still being prepared sees "Your business is being prepared" and "It takes a few seconds. This page refreshes by itself.".
2. The page looks again every few seconds and, as soon as the business is ready, shows the business (or its entrance, without a session).
In: the business's address.
Out: nothing; the page does not change the business.
If it fails: an address that belongs to no business says it does not exist; that of a deleted business says it is no longer there, with the way back to erplora.com.
Involved: the business (serves the page)

### HUBS-F07 Mark the business as ready
Status: done
Actor: system
Screen: none
Steps:
1. When the business finishes being prepared, it tells erplora.com with a signed call.
2. erplora.com moves it from "Preparing" to "Active", notes the time and its owner's screens change by themselves.
3. The owner gets the email "… is ready", only once.
In: the business's signed notice.
Out: the active business and the time it became ready; `hubs.business.ready`; the email, after saving.
If it fails: a notice without a valid signature, of another business or of an unknown business is refused and changes nothing. A business that was deleted or suspended meanwhile stays as it was and is not announced. If the notice does not arrive, the next pass of HUBS-F08 asks the business about a sign-up that has been more than 2 minutes without it.
Involved: the business (sends the notice)

### HUBS-F08 Retry what the business did not receive
Status: done
Actor: system
Screen: none
Steps:
1. Every 15 minutes, erplora.com looks for what the businesses' service has not received yet: a sign-up, a deletion, a recovery or the latest state of a business.
2. It sends it again and, for a sign-up that has been more than 2 minutes without the "ready" notice, it asks how it is going: if it is already ready, it marks it ready; if the service does not know it, it sends it again.
3. It notes in the log how much it delivered, how much stayed pending and how much the business refused.
In: the businesses with something pending.
Out: what was delivered, marked as delivered; what fails stays pending for the next pass.
If it fails: a business that fails does not stop the pass; the pass ends with an error if something stayed pending, unreachable or refused, and that error raises an alarm. Two passes at once do not step on each other: the second leaves without doing anything.
Involved: the business (receives what was pending)

### HUBS-F09 See the list of businesses
Status: done
Actor: owner, administrator, manager, employee
Screen: Businesses
Steps:
1. In the menu, "Businesses" opens the list of the account's businesses, the last opened first; the old addresses of the businesses panel lead here.
2. Each row shows the business (a link to its page), its web address, its "Status" ("Active", "Preparing", "Payment due", "Suspended", "Being deleted"), with the reason and the date when it matters ("Deleted. You can recover it until …"), its "Plan", the person's "Role" and its "Last used".
3. They search by name or web address and open the row's action: "Open", "Manage" (owner and administrators) or "Recover" (the owner, a deleted business within its 90 days).
4. The list changes by itself when a business becomes ready, changes plan or people, without reloading.
In: the businesses the person is a member of with the invitation accepted.
Out: nothing; the list keeps itself up to date.
If it fails: without businesses, "Create your first business" with the sign-up form; a search without results, "Nothing matches the search" with "Show all"; offline, the error with "Retry", never an empty list. A purged business no longer shows.
Involved: billing (the plan and the unpaid invoices of each row)

### HUBS-F10 See the panel's home
Status: done
Actor: owner, administrator, manager, employee
Screen: Businesses
Steps:
1. From the Entrance, "Go to the panel" opens **Businesses**, the panel's home, with the menu "Businesses", "Store", "Billing" and "Account".
2. Above, they see what waits for an answer (invitations, ownership offers, unpaid invoices) and below all their businesses with their plan, their status and their last use (HUBS-F09).
3. Without businesses, the home is "Create your first business"; the old address of the overview leads here.
In: the account's businesses.
Out: nothing.
If it fails: the states of the list of businesses (HUBS-F09).
Involved: billing (Billing), accounts (Account)

### HUBS-F11 Enter a business from erplora.com
Status: done
Actor: owner, administrator, manager, employee
Screen: Entrance, Businesses
Steps:
1. On the Entrance (with one or several businesses) or in **Businesses**, the person presses "Open" on their business ("Opening …").
2. The browser goes to the business's address, which asks erplora.com for the entry pass with the session already open, without asking for the password again.
3. They enter the business already identified; erplora.com remembers that business as the last opened and the Entrance puts it on top next time.
4. From an invitation, "Accept and enter" accepts and enters the same way.
In: the person who is a member of the business and their session.
Out: the entry into the business with a one-time pass that never travels in the address; the business as the last opened (`hubs.business.opened`).
If it fails: a business being prepared, suspended or deleted does not open and the row says why; one with a payment pending still opens. A business of another account or an invitation not accepted do not open. To an account with the second sign-in step, erplora.com asks for it before giving the pass.
Involved: accounts (the entry pass), the business (opens its session)

### HUBS-F12 Choose the business in the installed app
Status: done
Actor: owner, administrator, manager, employee
Screen: Entrance (in the installed app)
Steps:
1. The app without a remembered business (or after "Change business") opens the Entrance: with one business, "Open …"; with several, "Where are you working today?" with the last opened on top and each one's status.
2. The person presses "Open" on the business where they want to work.
3. The app goes to the business, enters without asking for the password again and stays linked to it: from then on the printer, the drawer and the rest of the hardware answer only that business.
4. Next time the app starts directly in the remembered business.
In: the businesses the person is a member of.
Out: the same as HUBS-F11, and the app linked to that business; never to an address that is not a business of ERPlora.
If it fails: a business of another account is not found; one that does not open now (being prepared, suspended, deleted) goes back to the Entrance, which says why. Without a session, the Entrance asks to sign in and then goes back to the business. The Entrance never goes into an existing business by itself: the person always chooses.
Involved: accounts (the entry pass), the installed app (links to the business), the business

### HUBS-F13 Open the business on another device
Status: done
Actor: owner, administrator
Screen: Business summary › On your devices
Steps:
1. On the business's page, the Summary shows the "On your devices" card ("Enter from anywhere").
2. The person copies the "Web address of the business" with "Copy address" and opens it in the browser of the till, the tablet or the phone, or downloads the "App for Windows" or the "App for Android".
3. On the other device they sign in with their account as always (HUBS-F11).
In: the business's web address.
Out: nothing; the card only shares the address.
If it fails: if the browser does not allow copying, "The address could not be copied. Select it and copy it by hand.". Inside the app the downloads do not show: the card speaks of the other devices.
Involved: public (the apps' downloads)

### HUBS-F14 See the businesses through the API
Status: done
Actor: owner, integration
Screen: none
Steps:
1. With their account's session, or with an API key of that account that reads Businesses, an integration asks for the list of businesses, with the same order, search and pages as the screen.
2. It asks for the record of one of them, with its status, its plan, its people and what it may do.
In: the account's session or API key.
Out: the same data the panel shows; nothing is saved.
If it fails: without a session or a key, the request is refused; a key without permission to read Businesses too; a business of another account is not found. Keys only read: creating or changing a business needs the session.
Involved: accounts (the API keys)
