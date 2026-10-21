<!-- generated from WORKBOOK.md sha256:096c39638e5228738e8e479e5d8bb44bbeb4b559a89c48b8ddc6efbebe73f095 -->

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

## Before you start

- The web is served from erplora.com; in development, from the SaaS's port 8001.
- The industries come from the taxonomy seeded on every deploy; without it, the list of industries says they are
  still being configured.

## Screens

### Home
The headline "One ERP. Infinite configurations. Yours." with "Start free", "Try the demo" and "Downloads"; below, the
strip "Made for small businesses", what a typical set of tools costs against ERPlora, the platform, the apps, the
counter app, the plans, a comparison, the closing call and the contact.

### Plans and prices
"Start free. Scale when you need it." with one card per plan on sale, the dedicated infrastructure offer, the table
of what each plan includes, the comparisons with other ERPs and the frequently asked questions.

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

## States of each screen

| State | What the person sees |
|---|---|
| Loading | The pages arrive whole from the server: no skeleton and no wait. |
| Empty | Without plans on sale, Plans and prices says there are none and paints no tables, and the home leaves out the plans block; without published apps, the home leaves out the apps blocks; without industries, "No business types yet". |
| Error | An address that does not exist shows "Page not found" with the web's menu; a server failure, "Something went wrong on our side", without depending on the database. |
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
1. The person opens "Pricing" and sees "Start free. Scale when you need it." and one card per plan one can start with (Free, Starter and Standard), with the monthly price per hub, its features and the assistant and WhatsApp messages a month.
2. If the plan has an annual price, the card states the year's price and the months it saves ("≈ €299.90/year · 2 months free"), worked out from the two prices; if every paid plan saves the same, the header says it once ("Pay for the year and get 2 months free.").
3. Higher up it offers dedicated infrastructure, by contact; further down, the table of what each plan includes, the comparisons with other ERPs and the frequently asked questions.
In: the plans on sale (the upgrade plans, such as Pro, Enterprise and Max, are not painted).
Out: nothing saved; the structured data of the frequently asked questions, taken from the same list as the accordion.
If it fails: without plans on sale, the page says so and paints no tables. If the annual price saves no whole month, the card states only the year's price, without "months free". A plan without assistant or WhatsApp messages does not name them.
Involved: hubs (the plans), billing (the charge, PUBLIC-F04)

### PUBLIC-F03 See the detail of a plan
Status: done
Actor: visitor
Screen: Plan detail
Steps:
1. The person reaches the page of a plan (by its address or from "Other plans" of another plan).
2. They see the name, the description, the monthly price per hub with the VAT note and "What's included".
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
3. The table "what you would pay separately" lists only functions the apps cover and its total is the sum of its rows.
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
3. To "Where is my data stored?" the answer is the European Union, with the one exception of the assistant if its European provider is unavailable, and the link "Read the privacy policy".
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
In: the published catalogue, the plans on sale, the taxonomy and the request's address.
Out: nothing saved.
If it fails: the private pages never appear in the sitemap or the summary and carry the no-index mark; the "coming soon" pages, the help and the support page are not indexed either. The web's texts are translated with the language catalogues (English as the source and its Spanish).
Involved: apps (the catalogue), hubs (the plans and the taxonomy)
