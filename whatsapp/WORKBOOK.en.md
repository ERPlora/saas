<!-- generated from WORKBOOK.md sha256:7a4dfc3640e2a88e9d72a367a935217176fa753462a702740b0db2672f657a28 -->

## What it is for and who it is for

WhatsApp is erplora.com's half of the Hub's **WhatsApp inbox**. ERPlora has a single app at Meta for every
business: each business's number is connected to it, and that is why what Meta reports (a customer's message, a
message delivered or read, the verdict on a template) reaches erplora.com, which hands it to each business's Hub.
What the business sends also goes out through erplora.com, which holds Meta's permission.

- Each business's Meta permission and its number's PIN are kept encrypted and never shown.
- What a customer writes is kept only until the Hub takes it and the retention period passes (30 days); nothing
  the business sends is kept here, except the key of the send.
- Each plan brings an allowance of messages a month; at the cap, sending stops until the next month or until the
  plan is upgraded. Two sends at once never both get past the cap.

Who uses it:

- The **system**: each business's Hub calls it to connect the number, send, erase a customer's data and register
  or delete templates; Meta sends it its notices.
- The business's **owner** and **admins**, from the inbox settings in the Hub; they receive the "Connect WhatsApp
  again" email when Meta's permission cannot be renewed.
- Anyone in the business opens their customers' photos, voice notes and documents from the inbox.
- **ERPlora staff**, in the admin: they see the numbers, the templates and what is waiting for the Hub, and can
  disconnect a number, hand the Hub now what is waiting and read Meta's templates again.

## Reference adopted

- Meta's **WhatsApp Business Platform (Cloud API)** as the only channel, with Embedded Signup so that the business
  connects its number in a Meta window without leaving the Hub, including coexistence with the WhatsApp Business
  app on the phone (https://developers.facebook.com/docs/whatsapp/embedded-signup).
- **Twilio, WATI, Respond.io, Gupshup and Zoko** as providers that act as intermediaries (one Meta app for many
  businesses): they route notices by number, keep the business's permission encrypted, retry delivery to their
  customer with a growing wait and charge per message within a plan allowance.
- **Odoo WhatsApp** and **Shopify Inbox**: templates are written in the software itself and sent to Meta's review
  from it; Meta's verdict arrives on its own.

## Before you start

- Meta's app ("ERPlora Inbox") is configured per environment with its id, its secret, the notice verification
  token and the Embedded Signup configuration. Without them, erplora.com says WhatsApp is not configured and Meta
  cannot deliver its notices.
- erplora.com's page Meta's window comes back to has to be among the return addresses Meta's app accepts, and be
  secure (https) outside development; otherwise WhatsApp is not configured either.
- Meta's permissions are encrypted with the environment's key; changing it stops opening the stored ones, unless
  the old one is kept as the previous key while numbers are connected again.
- There is no Meta test environment in development: in the tests, Meta's answers come from its documentation.

## Screens

### Meta's window coming back
erplora.com's page Meta takes its window to when it ends. It hands what Meta gave back to the Hub that opened it and
closes itself, without anyone seeing it. If something else opened it, or what it brings is no business's, it stays
open with "This window can be closed now.", in the browser's language.

### "Connect WhatsApp again" email
The business's owner receives it, in their language, when Meta does not let the permission be renewed. Subject
"Action needed: connect WhatsApp again (number)"; it says the permission is about to expire, that until it is
reconnected customers' messages will not reach the Hub, and "It takes a minute: open your Hub, go to WhatsApp and
connect your number again", with the link to the Hub.

### Admin: WhatsApp numbers
erplora.com's admin, only for ERPlora staff. Columns: number, business, the number's id at Meta, WhatsApp Business
account, active, from the WhatsApp Business app, Meta's permission ("Stored", "Expired" or "Missing"), when the
permission expires, needs reconnecting and connection date. Filters by active, WhatsApp Business app and needs
reconnecting; search by number, ids and business. Actions "Disconnect the number" and "Read Meta's templates again".

### Admin: WhatsApp deliveries to the Hub
What was received from Meta for each business: message id, kind ("Message" or "Delivery status"), business,
received, taken by the Hub, attempts, next attempt and last error. Never what the customer wrote nor their number.
Filter by kind and by empty "taken by the Hub"; action "Push to the Hub now".

### Admin: WhatsApp templates, sends and monthly usage
View only: each business's templates with their status and Meta's reason; the keys of the sends with their state
and their month; and what each business used each month.

## States of each screen

| State | What the person sees |
|---|---|
| Loading | In the Hub, the inbox; in the admin, the normal loading of a list. |
| Empty | In the admin, "0 WhatsApp numbers" and the empty list. |
| Error | An email that does not go out is retried in the next renewal; in the admin, each action says what it did and what it did not ("Meta could not be read now: the templates stay as they were"). |
| Not configured | WhatsApp without Meta's app or without its return page: the Hub does not offer to connect and Meta cannot deliver its notices. |
| No permission | The admin does not open without the role; the support group only looks, without actions. An attachment of another business says "not available". |

## Flows

| ID | Flow | Status |
|---|---|---|
| WHATSAPP-F01 | Connect the business's WhatsApp number | done |
| WHATSAPP-F02 | Disconnect the number | done |
| WHATSAPP-F03 | Tell the Hub which number the business has and whether it needs reconnecting | done |
| WHATSAPP-F04 | Keep each business's number with its Meta permission encrypted | done |
| WHATSAPP-F05 | Count the month's messages and stop at the plan's cap | done |
| WHATSAPP-F06 | Send a WhatsApp on behalf of the business | done |
| WHATSAPP-F07 | Receive Meta's notices and hand them to the Hub | done |
| WHATSAPP-F08 | See the WhatsApp numbers in the admin | done |
| WHATSAPP-F09 | Move a number to the business that connects it | done |
| WHATSAPP-F10 | Talk to Meta without exposing the business's permission | done |
| WHATSAPP-F11 | Give the Hub what it needs to open Meta's window | done |
| WHATSAPP-F12 | Renew Meta's permission before it expires and warn if it cannot | done |
| WHATSAPP-F13 | Confirm to Meta that the notices address is ours | done |
| WHATSAPP-F14 | Forget the messages the Hub already took | done |
| WHATSAPP-F15 | Register a new or edited template at Meta | done |
| WHATSAPP-F16 | Upload to Meta the sample of a template's header | partial |
| WHATSAPP-F17 | Delete a template at Meta | done |
| WHATSAPP-F18 | What ERPlora staff can do | done |

### WHATSAPP-F01 Connect the business's WhatsApp number
Status: done
Actor: owner, admin
Screen: WhatsApp inbox › Settings (in the Hub); Meta's window coming back
Steps:
1. In the inbox settings, tap "Connect WhatsApp": Meta's window opens, you sign in with Facebook, choose or type the number and, if the WhatsApp Business app on the phone is already in use, scan the code with the phone.
2. When it ends, the window goes through erplora.com, which hands Meta's one-time code (or its reason for not giving one) back to the Hub and closes itself.
3. The Hub passes erplora.com what Meta gave it; erplora.com gets the business's permission, checks that the chosen number is in that account, subscribes ERPlora's app to the account and registers the number (or, if it comes from the phone app, asks Meta for the contacts and the history without registering it).
4. "Your number" turns "Connected" with the number and the business's name on WhatsApp.
In: what Meta's window gives the Hub: a one-time code, the WhatsApp Business account, the chosen number and the portfolio.
Out: the business's active number with its permission and PIN encrypted; the Hub learns it through its state snapshot (`whatsapp.number.connected`).
If it fails: if Meta gives no code, the Hub receives its reason and nothing is connected; the code only goes back to the business that opened the window: if the window comes with another one, or with none, nothing is handed back and the window says "This window can be closed now.". If Meta refuses a step (the code expired, the PIN does not match, the subscription is not accepted) nothing is saved and Meta's reason is shown; if the chosen number is not in the account, or the account has several and none was chosen, no other one is connected: it asks to choose; if Meta does not answer, "try again"; without Meta's app configured, WhatsApp is not available. A demo cannot connect any number. If Meta does not give the history, the number stays connected anyway.
Involved: the Hub's WhatsApp inbox (settings)

### WHATSAPP-F02 Disconnect the number
Status: done
Actor: owner, admin
Screen: WhatsApp inbox › Settings (in the Hub)
Steps:
1. In the inbox settings, tap "Disconnect" and confirm.
2. erplora.com stops using the number: it forgets Meta's permission, removes ERPlora's app from that account if no other connected number uses it and keeps the PIN to register it again.
3. "Your number" turns "Not connected" at once, with "WhatsApp disconnected."; the Hub's conversations are not touched.
In: the business.
Out: the number inactive, without permission, with the disconnection date; the Hub learns it through its state snapshot (`whatsapp.number.disconnected`).
If it fails: without a connected number nothing changes; if Meta does not answer when removing the app, the number stays disconnected anyway and whatever Meta still reports about it is discarded.
Involved: the Hub's WhatsApp inbox (settings)

### WHATSAPP-F03 Tell the Hub which number the business has and whether it needs reconnecting
Status: done
Actor: system
Screen: WhatsApp inbox › Settings (in the Hub)
Steps:
1. Every time something of the business's WhatsApp changes (the number, its Meta permission, the month's usage, a template or Meta's verdict on it), erplora.com raises the version of the business's state snapshot and sends it to the Hub.
2. The snapshot says whether the number is "Connected", "Not connected" or "Needs reconnecting", the number and the name on WhatsApp, the allowance and what was used this month, and the templates with what Meta says of each one. "Needs reconnecting" shows as soon as Meta refuses the business's permission: when renewing it, sending a message, registering or deleting a template or opening an attachment.
3. The Hub applies it and the settings and the inbox show it without reloading.
In: the business's active number, its plan, what was used this month and its templates.
Out: the WhatsApp part of the business's state snapshot, with a version that only grows.
If it fails: if the Hub is away, the snapshot is retried by each business's reconciliation; a snapshot older than the stored one is not applied.
Involved: the Hub's WhatsApp inbox, businesses (the state snapshot)

### WHATSAPP-F04 Keep each business's number with its Meta permission encrypted
Status: done
Actor: system
Screen: Admin: WhatsApp numbers
Steps:
1. On connecting, erplora.com keeps the business's number with Meta's ids, the name on WhatsApp, whether it comes from the phone app and when the permission expires.
2. Meta's permission and the PIN are kept encrypted with the environment's key; whoever looks at the database only sees encrypted text.
3. A business has a single active number; connecting another disconnects the previous one.
In: what the connection gives.
Out: the business's number, used by sending, receiving and the templates.
If it fails: a permission that can no longer be decrypted (the key changed) reads as missing and the number is treated as "not connected"; it is written as an error for the team.
Involved: none

### WHATSAPP-F05 Count the month's messages and stop at the plan's cap
Status: done
Actor: system
Screen: WhatsApp inbox (in the Hub)
Steps:
1. Each send the Hub asks for takes a place in the monthly allowance of the business's plan before going out to Meta.
2. If Meta refuses it or it does not get to go out, the place is freed; if it went out, it counts.
3. At the cap, sending stops and the Hub says the month's cap was reached, until the next month or until the plan is upgraded. The Free plan brings 30, Starter 150 and Standard 300; a plan without WhatsApp sends none.
In: the business's plan and what was used this month.
Out: the month's usage, which the Hub shows in its settings (`whatsapp.message.recorded`).
If it fails: two sends at once with a single free place: one goes out and the other stops; the same send repeated (the Hub retries) does not use another place.
Involved: businesses (each business's plan)

### WHATSAPP-F06 Send a WhatsApp on behalf of the business
Status: done
Actor: system
Screen: WhatsApp inbox (in the Hub)
Steps:
1. In the inbox, someone replies to a customer or sends them an approved template; the Hub passes it to erplora.com with its own key for the send.
2. erplora.com reserves the allowance place, sends it to Meta with the business's permission and returns the WhatsApp message id.
3. What Meta says afterwards (delivered, read, failed) reaches the inbox as its status.
In: to whom, the text or the template with its variables, and the key of the send.
Out: the message sent through WhatsApp; the key noted so it is never sent twice (`whatsapp.message.recorded`).
If it fails: outside the 24 hours since the customer's last message, "only a template can be sent"; a customer who blocked the business, a template not approved or a number not connected say their reason and use no allowance; if Meta's permission expired or the business withdrew it in Meta, nothing goes out nor uses allowance, it says the number has to be connected again (not that it is not connected) and the number shows "Needs reconnecting" in the Hub; if Meta does not answer, it is unknown whether it went out: the Hub retries with the same key and erplora.com never sends it twice.
Involved: the Hub's WhatsApp inbox

### WHATSAPP-F07 Receive Meta's notices and hand them to the Hub
Status: done
Actor: system
Screen: WhatsApp inbox (in the Hub)
Steps:
1. A customer writes to the business's number (or the owner replies from the phone, or the history arrives on connecting): Meta reports it to erplora.com, which checks the notice is Meta's and keeps it for the business of that number.
2. erplora.com hands it to the Hub at once; if the Hub is away or does not have the inbox switched on, it tries again with a wait that grows up to one hour, every minute while something is left.
3. A photo, a voice note or a document arrive as an erplora.com link that only a person of the business opens with their session; the file comes from Meta at that moment and is not kept.
4. The status of a message of the business ("Delivered", "Read", "Not delivered") reaches the inbox: that of one sent from the Hub, once erplora.com knows which it is; that of a reply of the owner from the phone, after that reply.
In: Meta's notices: messages, echoes from the phone, history, delivery statuses and template verdicts.
Out: the message or the status in the Hub's inbox (`whatsapp.webhook.ingested`, `whatsapp.delivery.recorded`).
If it fails: a notice without Meta's signature is refused and not kept; one of a number nobody has connected is discarded; the status of a message the Hub does not have is waited for ten minutes and discarded; if the Hub says the message is not valid, it is not retried and stays visible to staff; an attachment of another business, or one Meta no longer has, says "not available".
Involved: the Hub's WhatsApp inbox

### WHATSAPP-F08 See the WhatsApp numbers in the admin
Status: done
Actor: ERPlora staff
Screen: Admin: WhatsApp numbers
Steps:
1. Open "WhatsApp numbers" in erplora.com's admin.
2. See each number with its business, its Meta ids, whether it is active, whether it comes from the phone app, whether its permission is "Stored", "Expired" or "Missing", when it expires and whether it needs reconnecting; filter by "needs reconnecting" or search by number or business.
3. Open one to see it whole; nothing is written by hand.
In: the staff account with its role.
Out: nothing; it is only looked at.
If it fails: without the role, the admin does not open; Meta's permission and the PIN never show, not even on the record.
Involved: none

### WHATSAPP-F09 Move a number to the business that connects it
Status: done
Actor: system
Screen: WhatsApp inbox › Settings (in the Hub)
Steps:
1. A number has a single owner in the whole platform: if another business connects it (for example, after the premises change hands), it moves to that business.
2. erplora.com tells both Hubs with their state snapshot: the new one sees it "Connected" and the previous one "Not connected".
3. Connecting the same number again in the same business only renews its permission and closes the "Needs reconnecting" warning.
In: the connection of the number from the other business.
Out: the number in its new business; where it came from is written down (`whatsapp.number.connected`).
If it fails: if the connection fails, the number stays where it was.
Involved: the Hub's WhatsApp inbox

### WHATSAPP-F10 Talk to Meta without exposing the business's permission
Status: done
Actor: system
Screen: none
Steps:
1. Every call to Meta carries the business's permission in the header, never in the address, and follows no redirects.
2. The answer is classified: Meta accepted, Meta refused (with its code and its reason for the person), Meta asks to wait, or Meta did not answer (without knowing whether it arrived).
3. The permission, the one-time code and the app's secret appear in no log.
In: what each flow asks of Meta.
Out: Meta's answer, or the reason there is none.
If it fails: an attachment whose link is not Meta's or is not encrypted is not downloaded.
Involved: none

### WHATSAPP-F11 Give the Hub what it needs to open Meta's window
Status: done
Actor: system
Screen: WhatsApp inbox › Settings (in the Hub)
Steps:
1. When painting "Your number", the Hub asks erplora.com.
2. erplora.com answers whether WhatsApp is configured and, if it is, the id of Meta's app, the id of the Embedded Signup configuration, the Meta version it uses and its page Meta brings the code back to; it later exchanges the code with that very page.
3. Without the app configured, or without a valid return page, it answers "not configured" with the ids empty, and the Hub does not show "Connect WhatsApp".
In: the business.
Out: the app's public ids; the secret and the verification token never go out.
If it fails: a business erplora.com does not know, or a demo, receives nothing.
Involved: the Hub's WhatsApp inbox (settings)

### WHATSAPP-F12 Renew Meta's permission before it expires and warn if it cannot
Status: done
Actor: system
Screen: "Connect WhatsApp again" email
Steps:
1. Once a day, erplora.com looks at the connected numbers whose permission expires in 14 days or less, of businesses that are still active.
2. It asks Meta for a new one in exchange for the current one; if it gets it, it notes the new expiry and closes the "Needs reconnecting" warning.
3. If Meta refuses it, or does not answer and 3 days or less are left, it marks the number "Needs reconnecting" (the Hub shows it) and sends an email, in their language, to the business's owner, one per incident.
In: the connected numbers and their permissions.
Out: the permission renewed or the "Needs reconnecting" mark with the email (`whatsapp.number.reconnect_needed`).
If it fails: if Meta does not answer and there is time left, it is retried the next day; an email that does not go out is retried in the next round; a number that fails does not stop the others; without Meta's app configured, the task ends with an error for the team.
Involved: businesses (the owner), the Hub's WhatsApp inbox

### WHATSAPP-F13 Confirm to Meta that the notices address is ours
Status: done
Actor: system
Screen: none
Steps:
1. When the notices address is set up in Meta's app, Meta calls erplora.com with the verification token and a challenge.
2. If the token matches the environment's, erplora.com returns the challenge and Meta accepts the address.
3. From then on, every Meta notice arrives signed with the app's secret and erplora.com checks the signature before reading it.
In: Meta's verification token and challenge.
Out: the notices address confirmed at Meta.
If it fails: a token that does not match is refused; without a token or without a secret configured, erplora.com says it is not available and accepts no notice.
Involved: none

### WHATSAPP-F14 Forget the messages the Hub already took
Status: done
Actor: system
Screen: Admin: WhatsApp deliveries to the Hub
Steps:
1. Once a day, erplora.com deletes what the Hub took more than 30 days ago and the delivery statuses older than 30 days.
2. What the Hub never took in 30 days (a Hub switched off or without the inbox) is deleted too, and how many messages of which business were lost is written down.
3. The keys of the sends and of the template registrations older than 30 days are deleted too.
In: what erplora.com keeps of each business and its dates.
Out: the old data deleted (`whatsapp.retention.purged`).
If it fails: the period can be shortened by hand (1 to 30 days), never lengthened; outside that range nothing is deleted and the task ends with an error.
Involved: none

### WHATSAPP-F15 Register a new or edited template at Meta
Status: done
Actor: owner, admin
Screen: WhatsApp inbox › Settings › Template (in the Hub)
Steps:
1. In the Hub, the template is written (name, language, category, header, text with its variables and an example of each, footer and buttons) and "Save" is tapped.
2. erplora.com checks Meta's rules before calling it: name in lowercase letters, digits and underscores, variables in sequence or named, one example per variable, at most 10 buttons with their limits.
3. It registers it at Meta (or, if Meta already had it, edits Meta's) and the Hub shows it "Under review"; Meta's verdict arrives on its own afterwards.
In: the template as it was written and the key of the save.
Out: the template at Meta and its copy in erplora.com, which travels to the Hub in the state snapshot (`whatsapp.template.registered`).
If it fails: a broken rule says which one; Meta refusing it gives its reason for the person; if Meta does not answer or asks to wait, nothing is saved and it can be retried; the same save repeated is never registered twice.
Involved: the Hub's WhatsApp inbox

### WHATSAPP-F16 Upload to Meta the sample of a template's header
Status: partial — the Hub does not offer headers with a photo, video or document (they are made in WhatsApp Manager), so there is no sample to upload; templates with such a header made in WhatsApp Manager are shown in the Hub
Actor: owner, admin
Screen: WhatsApp inbox › Settings › Template (in the Hub)
Steps:
1. A template with a photo, video or document header is created in Meta's WhatsApp Manager.
2. erplora.com brings it with what Meta says about it and the Hub shows it with its header kind.
In: the template as Meta has it.
Out: its copy in erplora.com and in the Hub.
If it fails: if Meta does not answer, the list stays as it was until the next read.
Involved: the Hub's WhatsApp inbox

### WHATSAPP-F17 Delete a template at Meta
Status: done
Actor: owner, admin
Screen: WhatsApp inbox › Settings (in the Hub)
Steps:
1. In the Hub, a template is deleted in one language.
2. erplora.com deletes it at Meta in that language (not the others with the same name) and removes it from its copy.
3. The Hub takes it as deleted.
In: the template's name, language and Meta id.
Out: the template gone from Meta and from erplora.com's copy (`whatsapp.template.forgotten`).
If it fails: if Meta no longer has it, it counts as deleted; if Meta refuses or does not answer, it stays alive and the Hub asks again.
Involved: the Hub's WhatsApp inbox

### WHATSAPP-F18 What ERPlora staff can do
Status: done
Actor: ERPlora staff
Screen: Admin: WhatsApp numbers, Admin: WhatsApp deliveries to the Hub
Steps:
1. A person from ERPlora enters the admin with their erplora.com account.
2. They see, read only and in their language, the numbers, the templates, what waits for the Hub, the keys of the sends and what was used each month; never the permission, the PIN nor what a customer wrote.
3. If they are a superuser, they can "Disconnect the number", "Read Meta's templates again" and "Push to the Hub now"; each action says what it did.
4. The daily tasks of renewing permissions and forgetting old data, and the one that hands over what is waiting, can also be run by hand.
In: the staff account with its role.
Out: what their actions do; a number's business is never changed nor activated by hand.
If it fails: without the role, the admin does not open; the support group only looks, without actions.
Involved: none
