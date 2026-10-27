<!-- generated from WORKBOOK.md sha256:d4d5f57149992fcf2ba5ecbc3173f938b363a56d5cc3fdebe20d975b35092d45 -->

## What it is for and who it is for

The public web is ERPlora's shop window and the door to signing up. It explains the product with live data (the
plans and their prices come from the same plans that are charged; the apps, from the published catalogue) and leads
to the sign-in screen, where the account is also created.

- Everything it promises the product does today: if something does not exist, the web does not name it.
- The price it shows is the one charged, without VAT, with the tax note next to it.
- It reads in English or in Spanish; the language is chosen by itself (browser) or from the footer of any page.

Who uses it:

- **Any visitor**, without an account: reads, compares, changes the language and starts free.
- **Search engines and assistants**: read the sitemap, the crawling rules, the summary for assistants and the
  structured data of each page.
- **ERPlora's staff** maintain the plans (and with them the web's prices) from the admin.

## Reference adopted

- **Shopify, Square and Lightspeed**: a home page with a single main call ("Start free") leading to sign-up, plans
  with the monthly price and the annual saving worked out, and the tax note next to the price
  (https://www.shopify.com/pricing, https://squareup.com/us/en/pricing).
- **Stripe, Shopify and Square**: the language switcher in the footer of every page, each language written in its
  own tongue (https://stripe.com, https://www.shopify.com).
- **Odoo and Microsoft Dynamics 365 Business Central**: the list of countries with what the product complies with in
  each, released with the product and not edited by hand
  (https://www.odoo.com/documentation/19.0/applications/finance/fiscal_localizations.html,
  https://learn.microsoft.com/en-us/dynamics365/business-central/dev-itpro/compliance/apptest-countries-and-translations).
- **Lightspeed, Holded, fiskaly and Mollie**: the compliance page names each country's actual fiscal system and what
  is left out (VeriFactu versus TicketBAI in Spain)
  (https://k-series-support.lightspeedhq.com/hc/en-us/articles/53394509875099-Understanding-Spanish-fiscal-compliance,
  https://www.holded.com/es/programa-contabilidad/cumplimiento-fiscal,
  https://www.fiskaly.com/fiscalisation,
  https://help.mollie.com/hc/en-us/articles/26810769614226-How-do-fiscalisation-regulations-work-with-Mollie-Point-of-Sale).
- **llmstxt.org and schema.org**: the summary for assistants and the structured data of organisation, application
  and frequently asked questions (https://llmstxt.org, https://schema.org/SoftwareApplication).

- **AEPD, ICO and CNIL; GitHub**: technical cookies need no consent, so the notice only shows when the web
  measures visits or advertises (https://www.aepd.es/guias/guia-cookies.pdf,
  https://ico.org.uk/for-organisations/direct-marketing-and-privacy-and-electronic-communications/guide-to-pecr/cookies-and-similar-technologies/,
  https://www.cnil.fr/fr/cookies-et-autres-traceurs/regles/cookies-solutions-pour-les-outils-de-mesure-daudience,
  https://github.blog/news-insights/company-news/no-cookie-for-you/).
- **Intercom, HubSpot and Zendesk**: the contact form's message is answered to whoever wrote it, arrives with the
  topic of the page it comes from and what was typed is not lost if something fails
  (https://www.hubspot.com/products/marketing/forms, https://www.zendesk.com/service/messaging/).
- **Shopify POS, Square POS; Safari View Controller and Custom Tabs**: inside an app, a legal text opens in a viewer
  with only the text and a way back, without the rest of the web
  (https://developer.apple.com/documentation/safariservices/sfsafariviewcontroller,
  https://developer.chrome.com/docs/android/custom-tabs).
- **Shopify App Store and Odoo Apps**: the store by sections with search, and each app's page with what it needs
  and its documentation (https://apps.shopify.com, https://apps.odoo.com).
- **Odoo and Dolibarr**: a real demo, with no account and no card, that opens in the browser, lasts a limited time and
  is deleted with everything inside it; whoever wants to keep their work creates their own account
  (https://demo.odoo.com, https://www.dolibarr.org/onlinedemo).

## Before you start

- The web is served from erplora.com; in development, from the SaaS's port 8001.
- The industries come from the taxonomy seeded on every deploy; without it, the list of industries says they are
  still being configured.
- The hub creates the demo: without the hub running, the demo screen says it is not available.

## Screens

### Home
The headline "One ERP. Infinite configurations. Yours." with "Start free", "Try the demo" and "Downloads"; below, the
strip "Made for small businesses", what a typical set of tools costs against ERPlora, the platform, the apps, the
counter app, the plans, a comparison, the closing call and the contact.

### Plans and prices
"Start free. Scale when you need it." with one card per plan on sale, the table of what each plan includes, the
comparisons with other ERPs and the frequently asked questions.

### Plan detail
The name, the description, the monthly price per hub with the VAT note, "What's included", the button to get started
and "Other plans".

### Industries
"ERPlora for your business." with the business types by sector and, on opening one, its page: the question one would
type into a search engine, the apps it comes with, the frequently asked questions and the links to pricing, apps,
product and compliance.

### Features, Security and Updates
Three product pages: what the platform does, how it protects the data (with "Contact Security Team") and the update
policy (with "Read section 7").

### Compliance
"EU compliance.": three figures, the countries "Ready for real operations." with their fiscal system and the grid
"Other EU countries." with "Not connected yet".

### About us, Collaborate and the "coming soon" pages
ERPlora's mission, the collaborator programme with the free year valued at the price of a year of the plan, and
Blog, Careers and Press, which only announce what is coming.

### Footer
The Product, Company and Support columns, the legal links and the language switcher "English · Español".

### Help center and Support
"Help center." with one folded guide per topic and its search; Support, with the three routes to ask for help and
what to tell in the message.

### Contact
"Get in Touch" with the form, "Contact Information" (the support address and "Chat with us") and "Response time";
the same form closes the home page.

### Cookie notice and Cookie preferences
The notice, only when the web measures visits, and "Cookie preferences" with one category per block and its switch.

### Legal texts and Responsible declaration
Legal notice, Privacy, Terms and the cookie policy, each on its own page; the responsible declaration in force with
its signed copy and the archive of versions.

### App store and App page
The apps by section with the search and the filters; the app's page with "Overview", "Required apps" and, if it has
one, "Documentation".

### Downloads and The ERPlora app
"Two free ways to try ERPlora." with the cloud hub and the counter app per platform, and the installed app's page.

### Demo
"Try ERPlora without signing up." with a card that changes with the moment: what the demo brings and "Try the demo";
the running demo, how long it has left and "Back to my demo"; or why it cannot be had now (switched off, full, too
many from the connection, not available, ended) with what can be done. There is always a way to "Start free".

## States of each screen

| State | What the person sees |
|---|---|
| Loading | The pages arrive whole from the server: no skeleton and no wait. |
| Empty | Without plans on sale, Plans and prices says there are none and paints no tables, and the home leaves out the plans block; without published apps, the home leaves out the apps blocks; without industries, "No business types yet". |
| Error | An address that does not exist shows "Page not found" with the web's menu; a server failure, "Something went wrong on our side", without depending on the database. The demo says on its own screen why it cannot be had now and what to do (PUBLIC-F29 to PUBLIC-F33). |
| No permission | Does not apply: everything is public. The private pages are not in the sitemap and cannot be crawled. |

## Flows

| ID | Flow | Status |
|---|---|---|
| PUBLIC-F01 | See the home page | done |
| PUBLIC-F02 | See the plans and the prices | done |
| PUBLIC-F03 | See the detail of a plan | done |
| PUBLIC-F04 | The price painted is the price charged | done |
| PUBLIC-F05 | See the industries and the page of a business type | done |
| PUBLIC-F06 | Read Features, Security and Updates | done |
| PUBLIC-F07 | Read only what the product does | done |
| PUBLIC-F08 | Read what the web says about security, data and availability | done |
| PUBLIC-F09 | See compliance by country | done |
| PUBLIC-F10 | Get to know the company: About us and Collaborate | done |
| PUBLIC-F11 | Start free from any page | done |
| PUBLIC-F12 | Reach a "coming soon" page or a retired address | done |
| PUBLIC-F13 | Change the language | done |
| PUBLIC-F14 | Search engines and assistants read the web | done |
| PUBLIC-F15 | Read the help and the support page | done |
| PUBLIC-F16 | Write to the team from the contact form | done |
| PUBLIC-F17 | Reach the form from other pages | done |
| PUBLIC-F18 | See the channels and the reply time | done |
| PUBLIC-F19 | Decide about cookies | done |
| PUBLIC-F20 | Read the legal texts | done |
| PUBLIC-F21 | Check the responsible declaration of the invoicing system | done |
| PUBLIC-F22 | Browse the app store | done |
| PUBLIC-F23 | See an app's page | done |
| PUBLIC-F24 | Get the installed app | done |
| PUBLIC-F25 | Know which version of the app is published | done |
| PUBLIC-F26 | Open a public page from the installed app | done |
| PUBLIC-F27 | Reach the demo | done |
| PUBLIC-F28 | Create the demo and go into it | done |
| PUBLIC-F29 | A demo that could not be opened | done |
| PUBLIC-F30 | The demo is switched off | done |
| PUBLIC-F31 | Every demo is taken | done |
| PUBLIC-F32 | Limit of demos per connection | done |
| PUBLIC-F33 | The demo ended | done |
| PUBLIC-F34 | Retire the demos that run out | partial |
| PUBLIC-F35 | From the demo to a real account | done |
| PUBLIC-F36 | Ask for a demo from another application | discarded |
| PUBLIC-F37 | The demo does not count as a business | done |

### PUBLIC-F01 See the home page
Status: done
Actor: visitor
Screen: Home
Steps:
1. The person opens erplora.com and sees "One ERP. Infinite configurations. Yours." with three buttons: "Start free", "Try the demo" and "Downloads".
2. Scrolling down they find what they would pay separately for invoicing, inventory, customers and sales (with the total added up from those rows) against ERPlora's cheapest plan, the platform, the featured apps, the counter app, the ecosystem, the plans, a comparison, more apps, the closing call and the contact form.
3. The six featured apps and the twelve of the "build to fit" block are the first of the published catalogue by section and name; the plan cards are the plans on sale, the free one first.
In: the published app catalogue and the plans on sale.
Out: nothing saved; the structured data of the organisation and of the application (PUBLIC-F14).
If it fails: without published apps the apps blocks are left out; without plans on sale, the plans block. The cards state the price without VAT with its note, never a total with VAT. The home's figures are not typed by hand: the number of apps, the prices and the table's total come from the data.
Involved: hubs (the plans), apps (the catalogue), accounts (the entrance)

### PUBLIC-F02 See the plans and the prices
Status: done
Actor: visitor
Screen: Plans and prices
Steps:
1. The person opens "Pricing" and sees "Start free. Scale when you need it.", that every plan includes all the apps, and one card per plan one can start with (Free, Starter and Standard), with the monthly price per hub, its features, how many apps can be turned on at once ("Up to 20 apps turned on at once"; with no cap, "All the apps turned on at once") and the assistant and WhatsApp messages a month.
2. If the plan has an annual price, the card states the year's price and the months it saves ("≈ €299.90/year · 2 months free"), worked out from the two prices; if every paid plan saves the same, the header says it once ("Pay for the year and get 2 months free.").
3. Further down, "More capacity": the upgrade plans (today Pro, Enterprise and Max), each with its monthly and annual price, its description and its features, and "Available once you are on Starter" instead of the sign-up button; one button, "Start free and upgrade whenever you want", leads to the sign-in screen.
4. Then the table of what each plan includes (the upgrade plans too), with the apps each one can have turned on at once, the same cap the Hub applies ("Unlimited" with no cap); the comparisons with other ERPs and the frequently asked questions, where the one on switching plans explains that moving down turns no app off: with more apps turned on than the new cap, they stay on and no more can be turned on until under it. Nothing is offered by contact.
In: the plans on sale, the upgrade plans too (active and not internal), in the order staff give them.
Out: nothing saved; the structured data of the frequently asked questions, taken from the same list as the accordion.
If it fails: without plans on sale, the page says so and paints neither tables nor "More capacity"; without upgrade plans, there is no "More capacity". If the annual price saves no whole month, the card states only the year's price, without "months free". A plan without assistant or WhatsApp messages does not name them.
Involved: hubs (the plans), billing (the charge, PUBLIC-F04)

### PUBLIC-F03 See the detail of a plan
Status: done
Actor: visitor
Screen: Plan detail
Steps:
1. The person reaches the page of a plan (by its address or from "Other plans" of another plan).
2. They see the name, the description, the monthly price per hub with the VAT note and "What's included", with the apps that can be turned on at once.
3. They press "Get Started" and reach the sign-in screen, where the account is also created (PUBLIC-F11); "Other plans" leads to the other plans on sale.
In: the plan by its identifier.
Out: nothing saved.
If it fails: an internal, retired, upgrade or non-existent plan gives "Page not found". "What's included" is the plan's list without the inherited separators.
Involved: hubs (the plans), accounts (the entrance)

### PUBLIC-F04 The price painted is the price charged
Status: done
Actor: system
Screen: none
Steps:
1. A plan's price (monthly and annual) lives in a single place, without VAT; the home, Plans and prices, the plan detail and Collaborate read it from there.
2. Charging a plan uses that same amount and the Stripe price pasted on the plan; staff cannot save a Stripe price that charges another amount, in another currency or with VAT included.
3. VAT is worked out at checkout, from the buyer's tax ID or VAT number, and the web says so next to every price.
In: each plan's monthly and annual price and its Stripe prices.
Out: nothing saved.
If it fails: a Stripe price that does not match the plan's is refused when saving it in the admin, with the reason; if Stripe does not answer, it is not taken as valid. So the web cannot show one price and the payment charge another.
Involved: hubs (the plans), billing (the charge and the price check)

### PUBLIC-F05 See the industries and the page of a business type
Status: done
Actor: visitor
Screen: Industries
Steps:
1. The person opens "Industries" and sees "ERPlora for your business." with the business types, which they can filter by sector.
2. They open one and see the headline with the question they would type into a search engine ("POS and ERP software for your hair salon"), an opening with the entry price and how many apps there are, the apps that business type comes with and its frequently asked questions.
3. At the bottom they have the links to pricing, the app store, the product and compliance, and "Get started free" and "Browse apps".
In: the active sectors and business types and the published apps of their sector.
Out: nothing saved; the structured data of the application and of the frequently asked questions.
If it fails: a business type that does not exist or is inactive gives "Page not found"; a retired code leads for good to the current one. Without apps for that business type the apps block is not painted. The page names no country's laws: compliance has its own page (PUBLIC-F09).
Involved: hubs (the taxonomy and the plans), apps (the catalogue)

### PUBLIC-F06 Read Features, Security and Updates
Status: done
Actor: visitor
Screen: Features, Security and Updates
Steps:
1. In "Features" they read what the platform does: the point of sale, the catalogue, the assistant and the counter app.
2. In "Security" they read four blocks (access, data, infrastructure and compliance) and "Contact Security Team" takes them to the contact form.
3. In "Updates" they read why ERPlora updates without asking, what it commits to in return, when it warns and how to leave; "Read section 7" opens the terms.
In: nothing; the pages' text.
Out: nothing saved.
If it fails: the three pages say what the platform gives, never what technology it is built with. What they promise about security is guarded by PUBLIC-F08.
Involved: none

### PUBLIC-F07 Read only what the product does
Status: done
Actor: visitor
Screen: Home, Plans and prices, Features, Collaborate
Steps:
1. The person reads the home, Plans and prices, the product pages and Collaborate to get an idea of what ERPlora does.
2. Everything named exists today in the apps: point of sale, invoicing with VeriFactu, inventory, customers, appointments and bookings, staff and time tracking, kitchen and tables.
3. The table of what one would pay separately lists only functions the apps cover and its total is the sum of its rows.
In: nothing; the pages' text, checked against the product's apps.
Out: nothing saved.
If it fails: accounting, payroll, support tickets, TicketBAI, the 303, 390 and 347 tax returns, warehouses with lots and expiry dates and bank reconciliation are not advertised, because no app does them; the industries strip names the businesses served today (hospitality, retail, hair and beauty, professional services). The comparisons with other products may name what those do.
Involved: none

### PUBLIC-F08 Read what the web says about security, data and availability
Status: done
Actor: visitor
Screen: Security, Plans and prices, Home, About us
Steps:
1. The person reads what Security, the pricing FAQ, the home and About us say about access, data and availability.
2. They read what works today: server sessions in secure cookies, a one-time code to enter the business, sign-in with Google, salted password hashing, encryption in transit and at rest, HTTPS only with TLS 1.2 or 1.3, AWS in Ireland with its web firewall, continuous backups recoverable to any moment of the last 14 days and high availability.
3. To "Where is my data stored?" the answer is the European Union, with the exceptions of the assistant: its voice and its search, such as transcribing a voice dictation, and its backup provider if the European one is unavailable; and the link "Read the privacy policy". The home says that the assistant's language model is served from the European Union, not the whole assistant.
In: nothing; the pages' text, checked against the infrastructure and the privacy policy.
Out: nothing saved.
If it fails: no availability agreement with a percentage, 24/7 support, regular audits, penetration test reports, end-to-end encryption or sign-in with GitHub is promised, and never "your data never leaves the EU", which would contradict the privacy policy.
Involved: none

### PUBLIC-F09 See compliance by country
Status: done
Actor: visitor
Screen: Compliance
Steps:
1. The person opens "Compliance" from the footer of any page (or from the page of a business type) and sees "EU compliance." with three figures: the EU countries where they can sell, those connected to their fiscal system and those not yet.
2. Under "Ready for real operations." they see Spain, "Connected", with VeriFactu: every invoice and receipt is recorded in an unalterable chain, carries its QR code and is sent to the AEAT; and what is left out: the Basque Country (TicketBAI) and Navarre have their own systems, which ERPlora does not connect to yet. "Read our responsible declaration" opens the declaration.
3. Under "Other EU countries." they see the rest, each with "Not connected yet": they can create their business and sell, and should check with their adviser what their country requires before using the point of sale there.
In: the countries where a business can be created and the fiscal systems the apps connect to.
Out: nothing saved.
If it fails: a country only shows as connected when an app really connects to its system; no regulations of other countries that nobody has checked are named. Spain comes first and the rest in alphabetical order in the reading language.
Involved: hubs (the sign-up countries), the business's verifactu (the connection to the AEAT)

### PUBLIC-F10 Get to know the company: About us and Collaborate
Status: done
Actor: visitor
Screen: About us, Collaborate
Steps:
1. "About Us" tells the mission, how each business's data is kept and that every app is ERPlora's.
2. "Collaborate" explains the programme in four steps and offers a full business free for a year, valued at what a year of the cheapest paid plan costs (its annual price), with the sectors and business types there are today; "Apply Now" leads to the contact with the programme's subject.
3. The company's old address leads for good to "About Us"; Blog, Careers and Press are "coming soon" pages (PUBLIC-F12).
In: the plans on sale and the taxonomy (active sectors and business types).
Out: nothing saved; the application arrives as a message of the contact form.
If it fails: without a paid plan on sale, Collaborate does not invent a value; without a taxonomy, it states no figures. There is no developers page: there are no third-party apps.
Involved: hubs (the plans and the taxonomy)

### PUBLIC-F11 Start free from any page
Status: done
Actor: visitor
Screen: Home, Plans and prices, Plan detail, Industries, Features, Compliance
Steps:
1. The person presses "Start free" (header, home, industries, features), "Get started" (paid plan cards) or "Get Started" (plan detail) on any page.
2. They reach erplora.com's sign-in screen, where the account is also created.
3. They create the account and their business, which is born on the Free plan; the paid plan is chosen afterwards, from the panel.
In: nothing: the button carries no parameters.
Out: nothing on the web; the account and the business are created by the sign-up.
If it fails: the free plan's card says "Start free" and a paid plan's "Get started", because every business starts on Free. Choosing a plan or an industry on the web does not preselect it at sign-up.
Involved: accounts (the entrance and the sign-up), hubs (the business on Free)

### PUBLIC-F12 Reach a "coming soon" page or a retired address
Status: done
Actor: visitor
Screen: Coming soon
Steps:
1. Blog, Careers and Press show their headline and what will come; they are not indexed and no menu links them.
2. An old address of the store (the marketplace, the solutions or the modules) leads for good to the app store; the company's, to "About Us".
3. The developers page and the local bridge page no longer exist: they give "Page not found".
In: nothing.
Out: nothing saved.
If it fails: a retired address never shows the panel's application in its place: it either leads to its successor or gives "Page not found".
Involved: apps (the store)

### PUBLIC-F13 Change the language
Status: done
Actor: visitor
Screen: Footer
Steps:
1. The web decides the language by itself: the one the person chose before, otherwise their browser's and, if none applies, English.
2. In the footer of any page they press "Español" (or "English"); the same page comes back in that language, with the active language marked.
3. The rest of the pages read in the chosen language while the choice lasts (a year).
In: the chosen language and the page to go back to.
Out: the language choice in the browser; an account's preference is not touched (it belongs to the panel).
If it fails: a language not on the list changes nothing; a page to go back to that is not erplora.com's is ignored and the home is shown.
Involved: none

### PUBLIC-F14 Search engines and assistants read the web
Status: done
Actor: system
Screen: none
Steps:
1. The crawling rules give each known search engine and assistant its own group, which keeps the private parts out and lets them into the public web; outside production, nothing may be crawled.
2. The sitemap lists the public pages (Compliance and Collaborate included), each active business type and the page of each published app; the summary for assistants tells what ERPlora is, links the pages that answer what a buyer asks and lists the apps of the live catalogue.
3. The home, pricing, the industries and each app carry their structured data, with the entry plan's price and the systems it runs on: web, Windows, Linux and Android.
4. Every day, in production, the search engines that take notices (Bing, which ChatGPT search leans on) are told about the sitemap's pages, so they read them that same day; outside production, none is told.
In: the published catalogue, the plans on sale, the taxonomy and the request's address; for the daily notice, the web's public address.
Out: nothing saved; the daily notice to the search engines.
If it fails: the private pages never appear in the sitemap, the summary or the notice, and carry the no-index mark; the "coming soon" pages, the help and the support page are not indexed either. If the search engine rejects the day's notice or does not answer, the submission ends in an error and the ERPlora team's alarm goes off; with no notice key configured (the normal case in development) nobody is told and it is not an error. The web's texts are translated with the language catalogues (English as the source and its Spanish).
Involved: apps (the catalogue), hubs (the plans and the taxonomy)

### PUBLIC-F15 Read the help and the support page
Status: done
Actor: visitor
Screen: Help center and Support
Steps:
1. From the footer, "Help Center" opens "Help center." with one guide per topic (getting started, installation, users and roles, settings and frequent questions), each folded; opening one shows it whole.
2. The page's search keeps only the guides that contain what was typed; if none does, it says "No guides found".
3. "Support" offers three routes: "Search the Help Center", "Contact support" (the form) and "Email the team" (the support address), and explains what to tell so the team can reproduce the problem and what never to send (passwords, PINs, recovery codes).
4. The old documentation page leads to the help center for good; each app's documentation is on its page in the store.
In: the guides published with the web, in English and in Spanish.
Out: nothing saved.
If it fails: a guide not yet translated is read in English, and so is a language without guides; nothing that is not a guide is ever shown. The help and the support page are not indexed.
Involved: none

### PUBLIC-F16 Write to the team from the contact form
Status: done
Actor: visitor
Screen: Contact
Steps:
1. On "Get in Touch" (or at the end of the home page) the person writes first name, last name, email, the phone if they want and what they need, and presses "Get in touch".
2. Before sending, the page marks the empty required fields and a mistyped email, and moves to the first one.
3. Once sent, the same page comes back with "Thanks! We received your message and will reply within 4 business hours."; the team gets it in the support mailbox and, when answering it, the answer goes to the person.
In: what was written in the form.
Out: an email to the support mailbox that is answered to the person; the web does not keep the message.
If it fails: an empty required field, an invalid email, too many messages in a row from the same network or a failure sending the email come back to the form with their reason ("Enter a valid email address.", "Too many messages from your network. Please try again in a little while.", "Sorry, something went wrong sending your message. Please try again.") and with what was typed in place, once; nothing is sent.
Involved: none

### PUBLIC-F17 Reach the form from other pages
Status: done
Actor: visitor
Screen: Contact
Steps:
1. "Contact" in the menu and the footer, "Contact support" on Support and the contact buttons of Plans and prices and of Industries open the form.
2. From Collaborate, "Join the Program" and "Apply Now" open it on the collaborator programme's topic; from Security, "Contact Security Team" opens it on the security topic.
3. The topic travels with the message: the team reads it in the email's subject.
In: the page the person comes from.
Out: the topic in the subject of the email to the team.
If it fails: a topic the web does not know is ignored and the message goes without a topic.
Involved: none

### PUBLIC-F18 See the channels and the reply time
Status: done
Actor: visitor
Screen: Contact
Steps:
1. On "Get in Touch", "Contact Information" shows the support address and "Chat with us" (WhatsApp); "Response time" says "Within 4 business hours".
2. The footer, Support, the home page's contact block, the error pages and the sign-in's error screen give the same support address, and the form, the sent notice and the home page ("4 h") give the same reply time.
In: nothing.
Out: nothing saved.
If it fails: no page promises round-the-clock attention or another reply time; the support address, the chat and the reply time are written in one place, so they cannot contradict each other.
Involved: none

### PUBLIC-F19 Decide about cookies
Status: done
Actor: visitor
Screen: Cookie notice and Cookie preferences
Steps:
1. While the web does not measure visits, it only sets the technical cookies (the session, the forms' protection, the language, the theme and the cookie choice) and shows no notice: there is nothing to consent to.
2. If measuring visits is turned on, every page shows the notice until the person chooses "Accept All", "Decline" or "Customize".
3. "Cookies" in the footer opens "Cookie preferences": the "Essential cookies", "Always active", and each optional category ("Analytical cookies", "Marketing cookies") with its cookies and its switch; the choice lasts a year.
4. Without accepting the analytical ones no measurement loads, and on the password and code screens it never does.
In: the person's choice.
Out: the choice, kept in the browser; the cookies of a declined category are deleted.
If it fails: the essential cookies are never deleted (they would sign the person out); if the server's fast memory does not answer, the page goes out anyway and the cleaning happens on the next one.
Involved: accounts (the sign-in screens)

### PUBLIC-F20 Read the legal texts
Status: done
Actor: visitor
Screen: Legal texts
Steps:
1. In the footer, "Legal Notice", "Privacy" and "Terms" open each text on its own page; the cookie policy opens from the privacy policy.
2. The privacy policy names who the data is entrusted to: Amazon Web Services in the Ireland region for hosting and email, the assistant's language model in Frankfurt, without training on it, and OpenAI for the assistant's voice and search: it transcribes the audio of a dictation, which neither the hub nor ERPlora keeps, and may process it outside the European Economic Area.
3. The terms give the numbers the product keeps: the days of the exit package, the days a suspended business waits before it is deleted and the trial of the plans on sale (none if none has one).
In: the plans on sale (the terms).
Out: nothing saved.
If it fails: no text names a provider no longer used or another hosting, nor keeps quiet about where the audio of a dictation goes, nor promises EU residency or a retention period for it, nor a consent or a switch for the assistant that the hub does not have (the assistant is used when someone in the hub writes or dictates to it, with the messages the plan gives), and no link between texts leads to a page that does not exist.
Involved: hubs (the plans)

### PUBLIC-F21 Check the responsible declaration of the invoicing system
Status: done
Actor: visitor
Screen: Responsible declaration
Steps:
1. "Responsible declaration" in the footer (and the updates clause of the terms) opens the version in force, with its version, its mode and whether it is signed.
2. If it is signed, it offers to open the signed copy and to download it, and explains that the signature is only checked by downloading it and opening it with a validator.
3. Below, the archive of every version: the current one marked in force and the earlier ones superseded; each opens at its own address.
In: the versions of the declaration published with the web.
Out: nothing saved.
If it fails: a version that does not exist, or the copy of a version not signed yet, gives "Page not found": never a broken file.
Involved: none

### PUBLIC-F22 Browse the app store
Status: done
Actor: visitor
Screen: App store
Steps:
1. "Apps" in the menu opens the store: the published apps grouped by section (sales, catalogue, people, restaurant, organisation), each with its icon, its summary and "Included in every plan".
2. "Search apps" searches the name and the summary; the section filters (with how many apps each has) combine with the search.
3. The old addresses of the marketplace, the solutions and the modules lead to the store for good.
In: the published catalogue.
Out: nothing saved.
If it fails: without published apps it says "No apps published yet." and is not indexed; if nothing matches, "No app matches your search.", with the way to clear the filters. No app has a price of its own: every plan includes all the apps.
Involved: apps (the catalogue)

### PUBLIC-F23 See an app's page
Status: done
Actor: visitor
Screen: App page
Steps:
1. Pressing an app opens its page on "Overview", with its description and, if it needs others, "Required apps", each linked to its page and with its access.
2. If the app has documentation, the "Documentation" tab shows it with its diagrams; if it only exists in Spanish, it says so with "This documentation is only available in Spanish.".
3. "Start free" leads to the sign-in; someone who already has an account goes to their dashboard.
In: the app of the catalogue and its documentation.
Out: nothing saved.
If it fails: an app that does not exist or is not published gives "Page not found"; an app without documentation has no such tab.
Involved: apps (the catalogue), accounts (the sign-in)

### PUBLIC-F24 Get the installed app
Status: done
Actor: visitor
Screen: Downloads and The ERPlora app
Steps:
1. "Downloads" in the footer opens "Two free ways to try ERPlora.": "Create your free hub in the cloud", with the devices and users of the Free plan, or "Install the ERPlora app" on the device at the counter.
2. Each platform button leads to its store when its listing is published (Microsoft Store, Google Play) and, if not, to the latest installer (Windows and Linux); Android is only installed from Google Play.
3. The app's page tells what it does at the counter and that a hub comes first: "You need a hub before you need the app.".
In: the Free plan on sale and the stores' listings.
Out: nothing saved.
If it fails: without a Free plan on sale, the card states no limit; a platform without a published version (macOS) is not offered, and the old local bridge no longer exists and gives "Page not found".
Involved: hubs (the Free plan)

### PUBLIC-F25 Know which version of the app is published
Status: done
Actor: system
Screen: none
Steps:
1. Each installed app asks erplora.com which version is published.
2. The answer is the version the last release left next to the installers.
In: the version note each release writes.
Out: nothing saved.
If it fails: if that note cannot be read or carries no version, the answer is that it is not known, never an invented number, and the app treats it as could not check.
Involved: none

### PUBLIC-F26 Open a public page from the installed app
Status: done
Actor: visitor
Screen: Legal texts
Steps:
1. In the installed app (and in the account the app opens in the browser), the sign-in screen and the email check screen link the terms and the privacy policy.
2. Pressing one opens the text as an app's viewer does: only the text and "Back", without the web's menu, footer or sign-up buttons.
3. The texts that one links open the same way while the app's session lasts; "Back" leads to the app screen that opened it, or to its start if the text was opened alone.
In: which part of the app opens it.
Out: the app mark in that window's session.
If it fails: inside the app the cookie notice does not show and no measurement loads, even if they were accepted on the web; a mark the web does not know is treated as the web.
Involved: hubs (the app's sign-in), accounts (the email check)

### PUBLIC-F27 Reach the demo
Status: done
Actor: visitor
Screen: Demo
Steps:
1. The person presses "Try the demo" on the home page (at the top or in the final call) or in the menu of someone who has not signed in, or opens the demo link they were given: the usual address and the short one open the same screen.
2. They see "Try ERPlora without signing up." and the card "Your own demo hub", with "No account and no card", "A real hub in your browser, nothing to install" and "It ends by itself after 60 minutes".
3. Below are the "Try the demo" button and "Want to keep what you do? Start free: it takes the same minute.".
In: nothing.
Out: nothing saved: opening the screen creates no demo, whether a person, a search engine or a reload opens it.
If it fails: if that browser already has a running demo, the screen offers no other: it says "Your demo is running", how long it has left and "Back to my demo" (PUBLIC-F28).
Involved: none

### PUBLIC-F28 Create the demo and go into it
Status: done
Actor: visitor, system
Screen: Demo
Steps:
1. The person presses "Try the demo".
2. An empty hub is created for that browser, with its own random address starting with "demo-", and it lasts 60 minutes from that moment. It is ready at once: there is no wait.
3. The screen says "Opening your demo…" and the browser goes into the demo by itself, as the user "Demo", with no account, password or PIN; without JavaScript, the "Continue" button does the same.
4. If they come back to the demo screen while it lasts, they see "Your demo is running", "It ends in 12 minutes." (whatever is left) and "Back to my demo", which takes them back to the same demo.
5. Pressing again, reloading or opening another tab of the same browser gives back the same demo, and signing in to their erplora.com account afterwards does not lose it.
In: the visitor's language, which the demo opens in.
Out: an empty demo hub with its user "Demo", and in that browser which demo is its own and when it ends.
If it fails: only the browser that asked for it gets in: a demo's link opened in another browser goes back to the demo screen, which offers it one of its own. If the demo cannot be created or opened: PUBLIC-F29, PUBLIC-F31 and PUBLIC-F32.
Involved: the Hub (its registry of hubs creates the demo and opens its session)

### PUBLIC-F29 A demo that could not be opened
Status: done
Actor: visitor
Screen: Demo
Steps:
1. If the hub does not answer or refuses the request, the person comes back to the demo screen and sees "The demo is not available right now." with "Try again".
2. If the demo was created but going in did not work, they see "We could not open your demo. Try again." and "Back to my demo", which takes them to the same demo while it lasts.
3. In both cases they also have "Start free".
In: nothing.
Out: nothing: a failed try does not stay as that browser's demo, so "Try again" asks for it again.
If it fails: the failure stays in the service's log; the person only sees the message, never a technical error.
Involved: the Hub (its registry of hubs)

### PUBLIC-F30 The demo is switched off
Status: done
Actor: visitor, system
Screen: Demo
Steps:
1. With the demo switched off, whoever opens the demo screen sees "The demo is closed for now. You can start free instead: it takes a minute.".
2. There is only one button, "Start free".
3. Switching it off closes every door at once: pressing the button of a screen opened before, or going back into a demo, creates or opens nothing and leads to this screen.
In: the demo's switch, which the team sets in the deployment.
Out: nothing.
If it fails: switching it off tears nothing down: whoever is already inside their demo carries on until it ends.
Involved: none

### PUBLIC-F31 Every demo is taken
Status: done
Actor: visitor
Screen: Demo
Steps:
1. When as many demos are running as the platform admits, the person sees "The demo is full right now. Try again in a few minutes.".
2. They have "Try again" and "Want to keep what you do? Start free: it takes the same minute.".
In: how many demos are running.
Out: nothing: the try spends no place.
If it fails: places free up as the demos end (PUBLIC-F34).
Involved: the Hub (its registry of hubs counts the running demos)

### PUBLIC-F32 Limit of demos per connection
Status: done
Actor: visitor, system
Screen: Demo
Steps:
1. Every new demo asked for from one connection counts: at most 3 an hour, far below the platform's total, so that nobody can leave the demo full for everyone else.
2. Whoever already has a running demo spends nothing: pressing again, reloading or another tab give them back theirs.
3. Past the limit, the person sees "Too many demos from your network. Please try again in a little while." and only "Start free", with no button to try again.
In: the connection it is asked from.
Out: the count of demos of that connection during the hour.
If it fails: the demos they already started stay theirs until they end.
Involved: none

### PUBLIC-F33 The demo ended
Status: done
Actor: visitor
Screen: Demo
Steps:
1. Whoever comes back to the demo screen when theirs has ended sees, once, "This demo has ended. Start another one.".
2. Whoever goes to the address of an ended demo sees "This demo has ended" with "Create another demo", which brings them to this same screen.
3. The screen does not start by itself: "Start another demo" asks for a new one (with the demo switched off it creates nothing, PUBLIC-F30), and "Start free" leads to sign-up.
In: when that browser's demo ends.
Out: the browser forgets its ended demo: the next visit sees the usual screen.
If it fails: a demo may end before its hour (the team retires it); "Back to my demo" finds it out and brings them here.
Involved: the Hub (the page of the ended demo)

### PUBLIC-F34 Retire the demos that run out
Status: partial — what the person created inside the demo is not deleted when it is retired: until phase 2 the demos share the apps' data with the others (round 2026-10-17, PLAN-SAAS §3.5 and PLAN-DB §6); each demo's own database, deleted with it, comes with the tenancy
Actor: system
Screen: none
Steps:
1. As soon as its hour has passed, the demo's address answers "This demo has ended", even if nobody has retired it yet.
2. Every minute, the hub retires the demos that ran out: it deletes their entry codes, their user "Demo" and their access, and marks them retired; a failure in one does not stop the others.
3. After a few days, the retired address stops existing altogether.
In: the demos whose hour has passed.
Out: the retired demo, with no user and no way in.
If it fails: if retiring one fails, it is tried again on the next round; meanwhile its address already says it has ended.
Involved: the Hub (its registry of hubs and its background process)

### PUBLIC-F35 From the demo to a real account
Status: done
Actor: visitor
Screen: Demo
Steps:
1. In any state of the demo screen the person has "Start free".
2. They reach the same erplora.com entrance as the other "Start free" buttons (PUBLIC-F11), where the account and its business are created like anybody's.
In: nothing.
Out: nothing of the demo goes to the account: the business is born empty, as the screen warns: "The demo hub is yours for 60 minutes; no account, no card. Everything you type disappears when it ends.".
If it fails: their demo keeps running until it ends, even once they have an account.
Involved: accounts (the entrance), hubs (the business sign-up)

### PUBLIC-F36 Ask for a demo from another application
Status: discarded — today's demo is created and opened in the same browser that asks for it, with a one-time code tied to it, so a door without a screen could not open it; no ERPlora application called it, and round 2026-10-17 (PLAN-SAAS §3.5) left the screen as the only door
Actor: system
Screen: none
Steps:
1. Whoever wants a demo asks for it from the demo screen (PUBLIC-F28).
2. The refusals show on that screen (PUBLIC-F29 to PUBLIC-F32).
In: nothing.
Out: nothing.
If it fails: does not apply.
Involved: none

### PUBLIC-F37 The demo does not count as a business
Status: done
Actor: system
Screen: none
Steps:
1. A demo is nobody's business: erplora.com keeps none, so it does not show in the list of businesses, nor in the plans, billing, invoices or usage.
2. Its address prefix, "demo-", is reserved: no customer may call their business that, and a name such as "Demo Bar" proposes "demobar".
3. A demo never connects to the real tax agency.
In: nothing.
Out: nothing.
If it fails: choosing by hand an address that starts with "demo-" is refused with "This address is reserved. Choose another one.".
Involved: hubs (the business's address), the Hub (VERIFACTU, the demo always in testing)
