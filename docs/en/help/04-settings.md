# Settings, devices and data

Open **Settings** in the side menu. At the bottom it has four tabs: "General", "Business", "Printing" and "Data and backups". What affects the whole business is only changed by the owner and the admins; everybody else sees those controls switched off and who can change them.

Your personal preferences are not in Settings but in **My profile** ("Profile", in the user menu): the language, the theme, the palette and the interface size, which follow you on any device.

## General

- **"This device"**: whether the device you are on is "Shared — a till or tablet several people use" (it asks for a PIN to enter and forgets it at the end of the shift) or "Personal — a device only you use" (the session stays open and it never asks for a PIN). Each device is decided separately, from the device itself.
- **"PIN pad"**: "Show PIN pad" decides for the whole business whether the tills ask who is there. "Ask again after inactivity" closes the session of a till nobody touches for 1, 5, 10, 15 or 30 minutes, or leaves it open "Until signing out". "PIN digits" chooses "4 digits" or "6 digits"; the PINs already in use keep working until their owners change them.
- **"Devices"** (only for whoever runs the business): the devices someone has entered on, with their mode and when they were last used. "Name it" gives one a name ("Bar", "Kitchen") and "Remove this device" closes its session at once: to use it again, somebody has to sign in on it with their account.
- **"API documentation"**: the "Show the API documentation" switch adds the API page and the "API" entry of the side menu, for whoever connects another system. It starts off. The API keys are created in **Employees › API keys**.

## Business

The "Your business" card shows "Business name", "Country", "Time zone", "Currency" and "Business language". They are not edited here: the name, the time zone and the language are changed on erplora.com with "Change on erplora.com"; the currency is the country's, and the country does not change once the business is ready.

"Fiscal data" opens the issuer of the Invoicing app, where the legal name, the tax ID and the address the invoices use are written. Without that app, the tab says "Install the Invoicing app to write the fiscal data".

In a business in Spain, sending the invoices to the AEAT is set up in the VeriFactu app, in **VeriFactu › Configuration**: either ERPlora files them on the business's behalf ("ERPlora files for you"), or the business uses its own certificate ("My certificate"), which has to carry the same tax ID as the Invoicing issuer.

## Printing

The tab has a single row, "Printers and ticket", which opens the Printing app: that is where the printers and the devices that print are added and where you decide what prints when charging. If the app is not there, it says "Install the Printing app to add your printer and set up the ticket" and takes you to **Apps**.

## Data and backups

At the top, a selector with "Import", "Export" and "Reset". All of this is only for the owner and the admins.

- **Import**: under "Choose what to load", use a template of the catalog with "Use template" or tap "Upload from file" and choose a .blueprint.zip (a backup or a template another business exported, 20 MB at most). Before anything is loaded, "Review what it brings" shows what each app brings and lets you untick the ones you do not want; at the end the "Import report" shows. What the business already had is neither duplicated nor overwritten.
- **Export**: write the file's name and language, answer "What is this file for?" ("Backup of this business", which also carries the customers, or "Template to share", which never does) and tick, app by app, "App" and "Data". No file ever carries people, PINs or fiscal data.
- **Reset**: "Undo an import" removes only what that import brought. "Reset the business" deletes for good the sections you tick, after you type the business's name to confirm; sales, invoices, fiscal records, people, files and the business's settings are never deleted.

Before anything is emptied, a full copy of the business's data is made and kept for 90 days in "Copies of the data", with its "Download". If in doubt, export a copy first.
