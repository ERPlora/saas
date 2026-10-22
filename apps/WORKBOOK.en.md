<!-- generated from WORKBOOK.md sha256:9e6662c20feeff4e9b7f0b534bbcfe647cf6e9b83884b3c45194af50d2d82285 -->

## What it is for and who it is for

ERPlora's apps (Invoices, Appointments, Inventory, WhatsApp…) live in the Hub, which registers them on
erplora.com with every version it deploys: their name, summary, description, icon, section, whether they are
paid, the business types they are meant for and their user manual. With that, erplora.com shows the app
store to anyone, with or without an account, in Spanish or in English.

Of the paid apps, erplora.com also keeps what it sells: the lowest plan that includes them and their net
monthly and annual price, with their Stripe prices. A free app has nothing to sell: it comes with any
business.

- Only the Hub writes the catalog: erplora.com reads it and never changes it.
- An app is never deleted: it is taken out of the store or off sale, and whoever has it keeps it.
- Nothing is bought inside a business: everything is bought in the erplora.com Store.

Who uses it:

- Any **visitor**, without an account, browses the public app store and reads its documentation.
- The **owner** of a business buys the paid apps in the panel's **Store**.
- **ERPlora staff** put the paid apps on sale, price them and withdraw them, from the admin.

## Reference adopted

- **Shopify App Store and Apple App Store**: anyone browses the store without an account, grouped by
  categories and with a search box; a withdrawn app is no longer offered to anyone new, but whoever has it
  keeps it (https://shopify.dev/docs/apps/launch/app-store-review/delist-app).
- **Odoo Apps**: every app brings its page and its manual, written by whoever makes it, and the store
  publishes them as they are in the reader's language, with English as the fallback
  (https://apps.odoo.com/apps).
- **Stripe Billing**: one product per paid app with a monthly and an annual price, both net, which the
  business's subscription adds as one more line (https://docs.stripe.com/products-prices/overview).

## Before you start

- The catalog appears when the Hub starts: in development, the Hub on the same machine registers it when
  its background process starts. Without a Hub, the store is empty.
- Paid apps are put on sale in the erplora.com admin, with an ERPlora staff account.
- Stripe always runs in test mode outside production.

## Screens

### Admin › Apps
Read-only list of the apps the Hub registered: label, name, section, whether it is paid, whether it is in
the store, the Hub version that registered it and the date. Filters by section, paid and in the store, and a
search box by label and name. Nothing can be added, changed or deleted: the Hub writes it.

### Admin › App documentation
Read-only list with one row per app and language of the user manual the Hub registered, with its
fingerprint and its date.

### Admin › Modules
List of the paid apps on sale: app, tier, monthly price, annual price, whether it is active and the last
change, with filters by tier and active and a search box. Each module's page: "App", "Tier", "Monthly price
(cents)", "Annual price (cents)", "Stripe product", "Stripe monthly price", "Stripe annual price" and
"Active".

## States of each screen

| State | What the person sees |
|---|---|
| Empty | The three lists say there are zero rows; Apps and App documentation stay empty until a Hub starts. |
| Error | A module that cannot be saved says why under its field and nothing is saved. |
| No permission | Without an ERPlora staff account, the admin asks to sign in; in Apps and App documentation there are no add, change or delete buttons for anyone. |
| Deletion refused | When deleting a module some business has, the admin names each business and deletes nothing. |

## Flows

| ID | Flow | Status |
|---|---|---|
| APPS-F01 | Browse the app catalog | done |
| APPS-F02 | Read an app's documentation | done |
| APPS-F03 | Put a paid app on sale | done |
| APPS-F04 | Link a paid app to its Stripe product and prices | partial |
| APPS-F05 | Take an app out of the store or off sale | done |
| APPS-F06 | Classify an app by section and business type | done |
| APPS-F07 | Buy a paid app always on erplora.com, never inside the business | partial |

### APPS-F01 Browse the app catalog
<!-- origen: old-saas:SAAS_PUBLIC-F12 old-saas:SAAS_PUBLIC-F13 fi:saas/support/public-core-config#serializer-modulelistserializer-moduledetailserializer -->
Status: done
Actor: visitor, system
Screen: none (the public app store and the panel's Store show it)
Steps:
1. Anyone, with or without an account, asks erplora.com for the list of apps: the public store, the panel's Store or an integration.
2. erplora.com returns the apps that are in the store, grouped by section (sales, catalog, people, restaurant and organization) and, inside each section, by name, ignoring case and accents.
3. Each app carries its name, summary, icon, section, whether it is paid and the business types it is meant for, in the language of whoever asks: in Spanish if their browser or their preference is Spanish, and in English in any other language.
4. It can be filtered by text (in the name and in the summary), by section, by whether it is paid and by business type; a filter that is not understood is ignored and the whole list comes back.
5. An app's page adds its description, the apps it needs (with their name, and linked only if they are in the store) and whether it has documentation.
In: the language of whoever asks and, if any, the filters or the app.
Out: nothing saved; the answer says which language it is in, and a shared cache never gives one person the answer in another person's language.
If it fails: an app that does not exist, or that ERPlora took out of the store, answers that there is no app with that label in the catalog; an icon that cannot be painted is replaced by the generic apps icon and noted for the team; a section this version of erplora.com does not know yet goes last, without a section. Asking for the list costs the same with three apps as with thirty.
Involved: the Hub (registers its apps with every version), public (the public app store), billing (the panel's Store)

### APPS-F02 Read an app's documentation
<!-- origen: old-saas:SAAS_PUBLIC-F31 fi:saas/support/public-core-config#service-module_readme_api-api-py fi:saas/support/public-core-config#service-render_markdown-services-rendering-py fi:saas/support/public-core-config#service-s3_docs-services-s3_docs-py -->
Status: done
Actor: visitor, system
Screen: none (the documentation tab of the public store's app page shows it)
Steps:
1. Someone asks for the documentation of an app in the store: the user manual the Hub registers with every version, in Spanish and in English.
2. erplora.com returns it ready to paint and cleaned of everything that is not text, headings, tables, lists, links, the app's own images and diagrams.
3. It comes in the language of whoever asks; if the app does not have the manual in that language yet, the Spanish one comes, saying it is the original.
4. The images come from the app's own files in the Hub; an image from anywhere else is removed.
In: the app and the language of whoever asks.
Out: nothing saved in the app; the painted page is kept for a day and is redone by itself as soon as the Hub registers a new manual.
If it fails: an app that does not exist, or that is out of the store, answers that it is not in the catalog; an app without a manual answers that it has no documentation yet.
Involved: the Hub (registers the manual), public (the documentation tab and the sitemap)

### APPS-F03 Put a paid app on sale
<!-- origen: fi:saas/django-admin#admin-module fi:saas/support/public-core-config#modelo-module old-saas:SAAS_PUBLIC-F27 -->
Status: done
Actor: ERPlora staff
Screen: Admin › Modules
Steps:
1. An app the Hub registered as paid shows in **Admin › Apps**, but it is not sold until it has its module.
2. In **Admin › Modules**, the staff tap "Add module" and type in "App" the app's label, as Admin › Apps shows it.
3. They choose the "Tier", which is the lowest plan that includes it without paying it separately, and type its "Monthly price (cents)" and its "Annual price (cents)", without VAT (an annual price of 0 = no annual option).
4. They save: from then on the app is on sale in the panel's Store at that price, and the businesses whose plan reaches its tier have it included.
In: the label of a paid app of the catalog, its tier and its prices.
Out: the module on sale.
If it fails: a label that is not in the catalog is not saved and says the Hub registers its apps when it starts; a free app is not saved either, because only a paid app is sold; a negative or decimal price is not accepted. A module whose app is no longer in the catalog (written some other way than the admin) is reported by the check that runs on every deployment.
Involved: billing (the Store and the charge), hubs (which apps each plan includes)

### APPS-F04 Link a paid app to its Stripe product and prices
<!-- origen: fi:saas/support/public-core-config#service-modulestripeservice-services-stripe-py -->
Status: partial — the Stripe prices pasted on a module are not checked on saving: one that charges another amount, in another currency or with the VAT inside is saved all the same
Actor: ERPlora staff
Screen: Admin › Modules
Steps:
1. Someone at ERPlora creates in Stripe the app's product and its monthly and annual prices, without VAT included.
2. In **Admin › Modules**, on the app's module, they paste "Stripe product", "Stripe monthly price" and "Stripe annual price", and save.
3. From then on the app is charged at those prices inside the subscription of each business that buys it.
In: the app's Stripe product and prices.
Out: the module with its Stripe prices.
If it fails: without the price for the business's billing period, the Store does not charge it and says it cannot be bought right now and to contact support.
Involved: billing (the charge in the Store)

### APPS-F05 Take an app out of the store or off sale
<!-- origen: old-saas:SAAS_PUBLIC-F22 -->
Status: done
Actor: ERPlora staff
Screen: Admin › Modules
Steps:
1. To stop selling a paid app, the staff untick "Active" on its module and save: no new business can buy it.
2. The businesses that already have it keep it and keep paying it; their Store shows it as no longer sold, and they can cancel it whenever they want.
3. To take an app out of the store completely, paid or free, ERPlora marks it in the Hub as out of the store: with the next version it no longer shows in the catalog, in the public store or in the sitemap, and its page stops existing.
4. Neither is deleted: the businesses that have it keep using it, and their Store still calls it by its name.
5. A module some business has cannot be deleted: the admin names those businesses and says to take it off sale instead.
In: the module's "Active"; the out-of-the-store mark, in the Hub.
Out: the app off sale or out of the store; nothing is deleted.
If it fails: deleting a module some business has, also from the action that deletes several, is refused with the name of each business.
Involved: billing (the Store and the subscriptions), the Hub (marks the app out of the store), public (the public store and the sitemap)

### APPS-F06 Classify an app by section and business type
<!-- origen: old-saas:SAAS_PUBLIC-F26 -->
Status: done
Actor: system
Screen: none
Steps:
1. Each app of the Hub declares its section (sales, catalog, people, restaurant or organization) and the business types it is meant for (hair salon, restaurant…; none = it serves all), and the Hub registers them with every version.
2. erplora.com groups the store by those sections, filters it by business type and shows on each sector's page the apps of its business types.
3. In the admin, a business type of the sign-up can only be tied to a type some app of the catalog declares.
In: each app's section and business types, as the Hub registers them.
Out: the store by sections and by business type; nothing is saved here.
If it fails: a section this version of erplora.com does not know yet goes last, without a section, and is noted for the team; a business type no app declares is not saved.
Involved: the Hub (declares the classification), hubs (the business types of the sign-up), public (each sector's page)

### APPS-F07 Buy a paid app always on erplora.com, never inside the business
<!-- origen: old-saas:SAAS_PUBLIC-F21 -->
Status: partial — the Hub's part is missing: its apps page does not yet offer a paid app without entitlement with the link to the erplora.com Store
Actor: owner, system
Screen: Store
Steps:
1. Nothing is bought inside the business: a paid app the business does not have is offered with a link to the erplora.com Store.
2. The link opens **Store › Modules** with that business already chosen at the top, and there it is bought like any other (BILLING-F32).
3. From the installed app (Android, Windows) the Store does not sell: it says "The store is not in the app" and "To change your plan or add modules, go to erplora.com in your browser.", without a link.
In: the business the link carries.
Out: what is bought, as in BILLING-F32; nothing is charged outside the Store.
If it fails: only the businesses one owns can be chosen at the top. erplora.com has no door through which a business buys on its own.
Involved: the Hub (its apps page), billing (the Store)
