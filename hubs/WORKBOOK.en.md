<!-- generated from WORKBOOK.md sha256:8a8bd43dba184ba02816381d1220bc8567580c8b952c2492b30a6a685d2e0d51 -->

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
- **The owner** sees the list of their businesses, changes its web address, deletes it, recovers a deleted one and
  changes its plan; with the **administrators**, they change its name, its language and its time zone.
- **The owner** and the **administrators** invite the people of the business, change their role and remove them;
  only the owner hands out the administrator role and transfers the ownership. A **manager** or an **employee** only
  opens the business.
- **ERPlora's staff** keep the plans from the admin and, from there, send a business again what it did not
  receive and look up who has access to each business.

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
- **Slack, Squarespace and Odoo**: the owner changes the space's own address in its settings; the old one stops
  serving (https://slack.com/help/articles/201719807).
- **Shopify, Square Online, Toast, Lightspeed, Odoo, Fresha and Vagaro**: the own domain is connected to the shop's
  public website, not to the point of sale, on paid plans and with the certificate set up by itself
  (https://squareup.com/help/article/6916, https://support.toasttab.com/en/article/Toast-Online-Ordering-Pro-Domains,
  https://www.fresha.com/help-center/knowledge-base/online-presence/109902-manage-your-domains).
- **Shopify, Square and Toast**: the owner gives their staff access with a role, and each role brings its
  permissions; the access is changed and removed from the same place, and whoever only works with a PIN at the till
  is managed inside the point of sale (https://help.shopify.com/en/manual/your-account/staff-accounts).

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

### Business settings
Each business's "Settings" tab. "General": "Business name", "Country" (only text once ready), "Time zone",
"Business language" and "Web address" with its copy button and, for the owner, "Change address"; "Save changes"
is enabled when something changes. Below, the "Danger zone" with "Delete business".

### Change the web address
The dialog of "Change address": "New address", under it "Your business will open at:" with the address it will
give and what happens next; "Change address" is enabled when it differs from the current one.

### admin › Businesses › Plans
Each plan's form for the staff: the texts in English and in Spanish, the price, what it includes, its limits and
its Stripe prices.

### Members
The "Members" tab of each business, for the owner and the administrators: the "Team" table with "Name" (one's own
row marked "You"), "Email", "Role", "Status" and "Last access", the owner first; per row, only what the person may
do with it ("Change role", "Remove", "Resend", "Cancel invitation" and, in the row's menu, "Transfer ownership").
Below, the places of the plan and "What can each one do?"; above, the ownership offered and waiting for an answer,
with "Withdraw the offer". On a phone they are cards.

### Invite
The "Invite to …" dialog: "Email", "Role" and "Message (optional)", with "We send an email with the link. The
invitation lasts 7 days." and the places left; "Send invitation" is enabled with an address.

### You have been invited
The centred card of the invitations waiting for an answer: "Someone gave you access to their business. Accept to
enter.", one card per business with "… invites you · …", "Accept and enter" and "Decline", and at the foot "The
owner or an admin of the business can take this access away.". In **Businesses** and in the Entrance the same
invitation shows above the list.

### Transfer the ownership
The "Transfer …" dialog: to whom it is offered, that they have 7 days to accept it, that the invoices keep going to
the same payer, and the business's name typed to confirm. Whoever receives it sees "… offers you …" in
**Businesses**, with "Accept the ownership" and "Decline".

### admin › Businesses › Members
The list of accesses for the staff: business, person, role, when they were invited, when they accepted and their
last access, with a search by business or by email and a filter by role; it is only looked up.

## States of each screen

| State | What the person sees |
|---|---|
| Loading | The list and the Entrance show their skeleton; "Create my business" is switched off while the request runs. |
| Empty | Without businesses, the list and the Entrance are the "Create your first business" form ("Free and no card: just the name and the country."). A search without results: "Nothing matches the search" with "Show all". |
| Error | "We could not load your businesses" with "Retry"; a business that could not be prepared: "Not prepared" and "We could not prepare it. We keep retrying; if it keeps failing, contact us.". |
| Preparing | The row says "Preparing" and "We are preparing it. It opens by itself when it is ready."; "Open" waits. |
| Offline | "Reconnecting… what you see may be a few seconds old." while the live connection comes back. |
| No permission | A business of another account does not exist for that person: it is neither listed nor opened. A manager or an employee who reaches the page of their business sees "You do not have permission to manage this business". |

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
| HUBS-F15 | Change the name, the language and the time zone of the business | done |
| HUBS-F16 | Change the web address of the business | done |
| HUBS-F17 | Connect an own domain to the business's website | partial |
| HUBS-F18 | Delete a business | partial |
| HUBS-F19 | Recover a deleted business | done |
| HUBS-F20 | Warn and close a business suspended for an unpaid plan | partial |
| HUBS-F21 | See the status and the usage of a business | partial |
| HUBS-F22 | Collect every night the usage of each business | partial |
| HUBS-F23 | ERPlora's staff acting on a business from the admin | done |
| HUBS-F24 | Invite a person to a business | done |
| HUBS-F25 | Accept or decline an invitation to a business | done |
| HUBS-F26 | Change the role of a person in a business | done |
| HUBS-F27 | Remove a person from a business | done |
| HUBS-F28 | Transfer the ownership of a business | partial |
| HUBS-F29 | See the people of a business | done |
| HUBS-F30 | Look up the accesses of the people in the admin | done |

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

### HUBS-F15 Change the name, the language and the time zone of the business
Status: done
Actor: owner, administrator
Screen: Business settings
Steps:
1. On the business's page, open "Settings": "General" shows the business as it is.
2. Change the "Business name", the "Time zone" or the "Business language" (the "Country" only changes while the business is being prepared) and press "Save changes": "Changes saved" appears.
3. The business receives the new name for its screen and its receipts, without anybody doing anything else.
In: the name, the language and the time zone; the account's session.
Out: the business with what changed, only what changed, and the business told after saving. Records `hubs.business.updated`.
If it fails: an empty name is not saved and the field says so; another country on a business already ready, "The country cannot change once the business is ready: its invoices belong to one country.". A manager or an employee do not change it, and a deleted business neither. Without a connection to the business, the change stays saved and is sent to it again (HUBS-F08). The postal address and the receipts' data are changed inside the business.
Involved: the business (receives the name, the language and the time zone)

### HUBS-F16 Change the web address of the business
Status: done
Actor: owner
Screen: Business settings › Change the web address
Steps:
1. In "Settings", next to the "Web address", the owner presses "Change address".
2. They type the "New address"; under it, "Your business will open at:" with the address it will give, and the dialog says what happens: "Your devices and erplora.com take you to the new address.", "The old address stops opening the business: links and QR codes with it stop working." and "Nobody else can take the old address while it is the last one you had.".
3. They press "Change address": "The business now opens at …" appears and the page shows the new one.
In: the new address; the owner's session.
Out: the business at its new address, which the business receives as soon as it is saved, and the way in from erplora.com and from the installed app towards it; the old one stays reserved for it. Records `hubs.business.address_changed`.
If it fails: a reserved address, "This address is reserved. Choose another one."; one another business has, "This address is taken. Choose another one."; one with capitals, spaces or hyphens at the start or the end, the error on the field. The same address changes nothing. Only the owner changes it; a deleted business does not.
Involved: the business (receives its new address), accounts (the way in at the new address)

### HUBS-F17 Connect an own domain to the business's website
Status: partial — not in phase 1: the own domain stays (as in the market's shops) only for the business's public website and on the plans that include it, and comes with its three pieces at once; today there is none: the check of the domain in erplora.com, its certificate at ERPlora's entrance and the business serving its website on that domain. Until then the panel does not show it.
Actor: owner
Screen: Business settings
Steps:
1. In "Settings", the owner of a business on a plan that includes an own domain types theirs (for example, the business's website on its domain) and erplora.com shows the record to create at their domain provider.
2. When the record points right, erplora.com checks it, asks for the certificate and, once set, the domain is active: the business's public website opens on it.
3. Every hour it looks again; if it stops pointing right three times in a row, it tells the owner and stops serving it until it comes back.
4. To remove it, they remove it from the settings and confirm it.
In: the owner's domain and their provider's record.
Out: the business's public website on its domain, with its certificate.
If it fails: a domain that does not point to ERPlora stays inactive and the missing record is said; a plan that does not include it does not offer it. The app and the way into the business stay at its erplora.com address.
Involved: website (the business's public website), the business (serves the website on its domain)

### HUBS-F18 Delete a business
Status: partial — the deletion email does not carry the link to download the business's data yet: that copy comes with each business's own database (phase 2); until then the email and the panel say until when it can be recovered.
Actor: owner, integration
Screen: Business settings › Danger zone
Steps:
1. In "Settings", in the "Danger zone", the owner presses "Delete business"; the dialog "Delete …" says "It stops working right now for everyone. You can recover it for 90 days; after that it is erased for good." and "Its plan is cancelled now: if you recover it, it comes back on Free.".
2. They type the business's name in "Type the name of the business to confirm" and press "Delete business": "Business deleted: …. You can recover it until ….".
3. The page says "It will be erased for good on …" with "Recover business", and the owner gets the email with that date.
4. An integration with the account's session does the same, with the name typed; an API key does not delete.
In: the name typed again; the owner's session.
Out: the business deleted, which stops opening at once for everyone and is erased for good after 90 days; its plan goes back to Free and what Stripe was charging is cancelled in the next pass; the business receives the deletion after saving. Records `hubs.business.deleted`.
If it fails: a name that does not match deletes nothing (case and spaces around do not matter); deleting it twice, "This business was deleted.". Only the owner deletes it. To stop paying without deleting it, the plan is cancelled from Billing (BILLING-F13).
Involved: billing (cancels what was being charged), the business (stops opening and keeps it 90 days)

### HUBS-F19 Recover a deleted business
Status: done
Actor: owner
Screen: Businesses, Business summary
Steps:
1. In **Businesses** (the row says until when it can be recovered) or on the deleted business's page, the owner presses "Recover business".
2. "Business recovered: …" appears and the business opens again as it was, on the Free plan; to go back to a paid plan, it is changed in the Store (BILLING-F08).
In: the business deleted less than 90 days ago; the owner's session.
Out: the business active again (or being prepared, if it never got ready), on Free, and the business told after saving. Records `hubs.business.restored`.
If it fails: after the 90 days, "This business was erased for good and cannot be recovered."; a business that is not deleted, "This business is not deleted.". If the account already has its free business, it does not come back: first the other one moves to a paid plan. Only the owner recovers it.
Involved: the business (opens it again)

### HUBS-F20 Warn and close a business suspended for an unpaid plan
Status: partial — the deletion of day 180 is HUBS-F18's and does not carry the link to download the data yet either (it comes with each business's own database, phase 2).
Actor: system
Screen: none
Steps:
1. A business whose plan could not be charged is suspended after its days of grace, and whoever pays gets the suspension email (BILLING-F16): from that moment its countdown runs.
2. Every hour, erplora.com looks at the suspended businesses. At 30 days, the owner gets "… is still suspended" with the date it will be deleted if it is not paid and the way to pay it; at 150, "Last notice: … will be deleted on …". Each notice goes out only once.
3. At 180 days, already warned for the last time, the business is deleted as its owner deletes it (HUBS-F18): 90 more days to recover it, on Free, and the deletion email, which says why.
4. If the invoice is paid meanwhile, the business works again at once and the countdown is forgotten with its notices.
In: the businesses suspended for an unpaid plan and the date they were suspended.
Out: the two notices to the owner and, at the end, the business deleted. Records `hubs.business.deleted`.
If it fails: a notice that could not leave is sent again on the next pass, and without it nothing is deleted; a business that fails does not stop the others and the pass ends with an error; a suspended business without a date is never deleted and is noted for a person to look at.
Involved: billing (suspends, tells of the suspension and runs the pass), the business (stops opening)

### HUBS-F21 See the status and the usage of a business
Status: partial — the business does not measure its usage every night yet (HUBS-F22): its space is that of its own database, which comes in phase 2; so on a real business the "Usage" card says "No data yet. The figures arrive every night, from the first one after the business is created."; the status, the plan and the seats are already the real ones.
Actor: owner, administrator
Screen: Business summary
Steps:
1. On the business's page, the header says its status ("Active", "Preparing", "Payment due", "Suspended" or deleted) and the Summary, its plan with the devices and the people against the seats.
2. The "Usage" card ("How your business is doing in ERPlora") shows the "Storage" used of its plan's space, with a warning when it nears the limit, and the people "Active yesterday" and over the "Last 30 days", with "Yesterday's data: updated every night.".
In: the business and what it measured last night.
Out: nothing is saved; the page changes by itself when a new night arrives.
If it fails: without any night measured, "No data yet. The figures arrive every night, from the first one after the business is created."; with data of a day before yesterday, "Data from …: updated every night.". A manager or an employee do not see the business's page, only "Open".
Involved: the business (measures its usage)

### HUBS-F22 Collect every night the usage of each business
Status: partial — erplora.com already asks for it every night, but the businesses' service does not serve its measurement yet: a business's space is that of its own database, which comes in phase 2; until it does, the pass ends with an error and nothing is saved.
Actor: system
Screen: none
Steps:
1. Every night, erplora.com asks the businesses' service what it measured of each one the day before: the space of its files, that of its database and the people who came in that day and over the last 30.
2. It keeps one day per business; if it collects a day already kept again, it replaces the figures only if they changed, and tells that business's page.
3. A day that was missed is collected later, asking for it by its date.
In: the night's measurement, page by page.
Out: the usage of each business and day. Records `hubs.business.usage_collected`.
If it fails: if the service does not answer or refuses, the pass ends with an error and alerts; a broken row does not stop the others; a business erplora.com did not sell is noted without an error. Two passes at once do not step on each other.
Involved: the business (measures its usage)

### HUBS-F23 ERPlora's staff acting on a business from the admin
Status: done
Actor: ERPlora's staff
Screen: admin › Businesses
Steps:
1. The staff enter erplora.com's admin and look for the business by its address or its name; they see its record with its members, its plan, who pays, its usage and what the business still has to receive.
2. They choose the business and an action: "Send the latest state to the Hub", "Retry what the Hub still owes" or, in the record of the session ends, "End the sessions in the Hub now"; the admin says how many are up to date and how many are still owed.
3. Each action stays in that business's history: who did it, when and which.
In: the staff account with its second factor.
Out: what the action sends to the business and the line of the history.
If it fails: the admin does not create, change or delete businesses, members or paid plans: only their own screens do, so nobody of the staff makes themselves owner of a business or deletes it without its deletion. Support staff see everything and run no action. For the data inside the business there is the businesses' admin (in the businesses' service).
Involved: the business (receives what is sent again), accounts (the staff account)

### HUBS-F24 Invite a person to a business
Status: done
Actor: owner, administrator, integration
Screen: Members › Invite
Steps:
1. In the business's "Members" tab, "Invite" opens "Invite to …" with "Email", "Role" (Employee to start with; only the roles below one's own: the owner also hands out Admin) and "Message (optional)"; below, how many places of the plan are left.
2. They press "Send invitation": "Invitation sent to …" shows and the person appears in the list as a pending invitation, with "Resend" and "Cancel invitation".
3. The person receives an email with who invites them, to which business, with which role, until when it is valid and the link to accept it; if they have no account yet, also how to get in (with Google or by setting their password).
4. "Resend" sends the email again and gives it 7 more days; "Cancel invitation" withdraws it and its link no longer lets anyone in. An integration does the same with the account's session.
In: the email, the role, the message and the business; the session of whoever invites.
Out: the invitation, valid for 7 days, which holds a place of the plan; the account of that address if it did not exist, without a password. The business does not receive the person until they accept. Records `hubs.member.invited` (when resent, `hubs.member.invitation_resent`; when cancelled, `hubs.member.invitation_cancelled`).
If it fails: somebody already in the business, "… is already on this business."; with an invitation still valid, "… already has an invitation waiting. Resend it instead." (an expired one is renewed by inviting again). A role equal to or above one's own, "You cannot hand out a role equal to or above yours.". Without places, the dialog says "The plan has no free places left: change the plan or remove someone to invite more people." and sends nothing. An address of ERPlora's staff, "This address belongs to ERPlora's staff and cannot join a business.". An account that never proved that address is released before being invited: it loses its password, its second factor, its Google and its sessions, and only whoever opens that mailbox gets in. A manager or an employee invites nobody; a deleted business takes no invitations; a business of another account does not exist for whoever invites. If the email does not leave, the invitation stays.
Involved: accounts (the invited person's account and, if it never proved its address, its release), the business (receives the person when they accept)

### HUBS-F25 Accept or decline an invitation to a business
Status: done
Actor: administrator, manager, employee
Screen: You have been invited, Businesses
Steps:
1. The invited person enters erplora.com with the invitation's email (or follows its link): "You have been invited" shows one card per business with "… invites you · …"; in **Businesses** and in the Entrance the same invitation shows above the list.
2. They press "Accept and enter": they go into the business without typing the password again, with the role the invitation says, and the business is now in their list.
3. Or they press "Decline" and confirm it in "Decline the invitation": "Invitation declined" shows and whoever invited them would have to invite them again.
In: the account's invitations waiting for an answer and still within their 7 days.
Out: on accepting, the person inside the business and the business told, with the list of people up to date; on declining, the invitation deleted. Records `hubs.invitation.accepted` or `hubs.invitation.declined`. The owner and the administrators see the change in "Members" at once.
If it fails: an expired invitation, "This invitation expired. Ask whoever invited you to send it again."; one already answered, withdrawn or someone else's cannot be answered ("This invitation is no longer valid"). Without the email confirmed, "Confirm your email address before accepting the invitation.". If the plan has no room left, "This business has no seat left on its plan. Ask whoever invited you to free one or to change the plan.". Accepting twice gives nothing more, and it never touches the person's other businesses.
Involved: accounts (the session and the jump into the business), the business (receives the person)

### HUBS-F26 Change the role of a person in a business
Status: done
Actor: owner, administrator, integration
Screen: Members › Change role
Steps:
1. In "Members", in the person's row, "Change role" opens "Change the role of …" with the roles that can be given to them.
2. They pick the new one and press "Change role": "… is now …" shows and the row shows the new role.
3. The business receives the list of people with the new role and ends that person's session there at that moment: the next thing they do asks them to sign in again, and they come back with the new role.
In: the person and the new role; the session of whoever changes it, who has to rank above the person and above the role given.
Out: the new role and the notice to the business, with the end of that person's session there; the role of an unanswered invitation changes without telling the business. Records `hubs.member.role_changed`.
If it fails: one's own role, "You cannot change your own membership."; somebody of an equal or higher rank, "You cannot manage a member whose role is equal to or above yours."; a role equal to or above one's own, "You cannot hand out a role equal to or above yours.". The ownership is not given from here (HUBS-F28). A manager or an employee changes no roles; a person of a business of another account does not exist for whoever asks.
Involved: the business (BASE-F13: receives the new role and ends the session), accounts (the session)

### HUBS-F27 Remove a person from a business
Status: done
Actor: owner, administrator, integration
Screen: Members › Remove
Steps:
1. In "Members", in the person's row, "Remove" opens "Remove …" ("… loses access to … at once. Their account and their other businesses stay.").
2. They press "Remove from the business": "… was removed from the business" shows and the row goes.
3. The business receives the list of people without them and ends their sessions in that business at that moment, only in that one: if they come back, erplora.com tells them "You don't have access to this hub".
In: the person; the session of whoever removes them, who has to rank above them.
Out: the person out of that business (their account and their other businesses stay), an ownership offer pending to them withdrawn, the notice to the business and the end of their sessions there, retried if the business does not answer. Records `hubs.member.removed`.
If it fails: oneself, "You cannot change your own membership."; somebody of an equal or higher rank (never the owner), "You cannot manage a member whose role is equal to or above yours.". An unanswered invitation is cancelled, not removed: "This person has not answered yet: cancel the invitation.". Whoever still pays for the business (the previous owner after a transfer) is not removed: "… still pays for this business. Say who pays from now on first: your billing details are asked when you pay a plan or a module here." or, if the plan is still on their card, "This business's plan is still paid with …'s card: contact support to move it to you first.".
Involved: the business (BASE-F13: receives the list without them and ends their sessions), billing (who pays for the business)

### HUBS-F28 Transfer the ownership of a business
Status: partial — a paid plan keeps being charged to the previous owner's card until support moves it to the new owner's name, and there is no way to do it yet.
Actor: owner
Screen: Members › Transfer the ownership, Businesses
Steps:
1. The owner, in "Members", opens the row menu of a person already in the business and chooses "Transfer ownership".
2. In "Transfer …" they read that the person has 7 days to accept it and that the invoices keep going to the same payer, type the business's name and press "Offer the ownership": "Offer sent to …: they have 7 days to accept it" shows and, above the list, "Ownership offered to …" with "Withdraw the offer".
3. The person receives an email with the link to **Businesses**, where they see "… offers you …" with "Accept the ownership" and "Decline".
4. On accepting, "You are now the owner of …" shows: they become the owner and the previous one stays as administrator; the previous one receives an email that tells them where to see what they still pay.
In: the chosen person, who has to be in the business already; the owner's session and, when answering, that person's.
Out: the offer, valid for 7 days; on accepting, both roles changed at once (always a single owner), the business told and both people's sessions there ended. Who pays does not change: the new owner gives their own billing details when paying a plan or a module. Records `hubs.ownership.requested` and, on the answer, `hubs.ownership.accepted`, `hubs.ownership.declined` or `hubs.ownership.cancelled`.
If it fails: to somebody not in the business yet, "Invite this person to the business first: it can only go to somebody already on it."; to oneself, "You already own this business."; with another offer waiting, "There is already a transfer of this business waiting for an answer.". When answering: "This transfer was already answered.", "This transfer expired. Ask the owner to send it again.", "You are no longer on this business." or "This business already changed hands: ask its current owner to transfer it.". A free business is not accepted if the person already has theirs: "You already have a free business. Change its plan to create another one.". Only the owner offers; only the chosen person accepts or declines, and only the owner withdraws the offer.
Involved: billing (who pays for the business), the business (BASE-F13: receives the new roles and ends both people's sessions)

### HUBS-F29 See the people of a business
Status: done
Actor: owner, administrator, integration
Screen: Members
Steps:
1. On the business's page, the "Members" tab shows the "Team" table: the owner first and each person with their email, their role, their status (inside, pending invitation or expired) and their last access; one's own row carries "You".
2. Each row offers only what the person may do with it (HUBS-F24 to HUBS-F28); on a phone they are cards and, with many people, it goes page by page.
3. Below it says how many places of the plan are used and "What can each one do?"; the list changes by itself when somebody accepts, changes role or leaves.
In: the account's session and the business.
Out: nothing stored.
If it fails: "We could not load the members" with "Retry". A manager or an employee sees "You do not have permission to manage this business"; a business of another account does not exist for whoever asks. An unanswered invitation has no joining date.
Involved: accounts (the session), billing (the places of the plan)

### HUBS-F30 Look up the accesses of the people in the admin
Status: done
Actor: ERPlora's staff
Screen: admin › Businesses › Members
Steps:
1. The staff enter erplora.com's admin and open the list of members; they search by the business or by the person's email and filter by role.
2. They see, per access, the business, the person, their role, when they were invited, when they accepted and their last access; each business's record also shows its members.
In: the staff account with its second factor.
Out: nothing stored.
If it fails: the admin invites, changes and removes nobody: only the owner and the administrators do it, in "Members", so nobody of the staff gives themselves access to a business. Support staff look it up too.
Involved: accounts (the staff account)
