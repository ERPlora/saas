<!-- generated from WORKBOOK.md sha256:6db81734b40d52add99914ce298d8fbc311a55d8e5445e085bd629ebd5437b0b -->

## What it is for and who it is for

An erplora.com account is the person who signs in: with it the businesses are created and used, ERPlora is
paid and each business is entered from the entrance screen. One signs in with the email and a password
(plus a code that arrives by email) or with Google, and the account keeps which terms it accepted and when.

- One account per email: an address that looks like another (with other capitals or with full-width
  letters) is the same account, never a second one.
- Nobody uses the panel with an unconfirmed email: the code that arrives by email proves it.
- The entrance screen never says which emails have an account: an unknown email answers like a wrong
  password, and a sign-up with an email already registered answers like a new one.

Who uses it:

- **Anyone** creates their account, signs in and out, and recovers their password.
- **The person with an account** changes their password, turns on the authenticator app and sees and
  closes their sessions from **Account › Security**; changes their profile, downloads their data and deletes
  their account from **Account › Profile**, and chooses their language, theme and notices from **Account ›
  Preferences** (the theme, also from the **User menu**).
- **ERPlora staff** see and manage the accounts from the admin, without being able to change what an
  account accepted; in an incident they close every session of an account and, with two-step verification
  switched on, they only get into the admin with their authenticator app.

## Reference adopted

- **Shopify, Square and Stripe**: a single entrance screen with "Sign in" and "Create account", an email and
  a password with the eye to see it (without repeating it), and a one-time code by email to
  confirm it (https://help.shopify.com/en/manual/your-account/account-security).
- **Google and Microsoft**: the code by email as the second step of every sign-in with a password, and a
  new password is never the current one.
- **OWASP (Authentication and Forgot Password Cheat Sheets)**: the same answer whether the account exists or
  not, a reset link that expires and works once, and a throttle per account and per network address that
  does not lock the owner out with the right password
  (https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html).
- **Stripe (`tos_acceptance`)**: the acceptance of the terms is kept with its date and the version
  accepted, and continuing after a change accepts the new one.
- **Odoo and Shopify**: signing out only ends that browser's session; changing the password ends the
  others.
- **Google and GitHub**: the authenticator app is set up by scanning a QR code (or typing its key) and
  leaves recovery codes that are shown once and downloaded; generating others voids the previous ones.
- **Google ("Don't ask again on this computer", "Revoke all") and Microsoft**: trusting a browser is offered
  unticked next to the code, holds only in that browser, and every browser stops being trusted at once.
- **Google ("Your devices") and GitHub ("Sessions")**: the list of the open sessions with the device, the
  browser, the address and the last use, this browser's first, and closing one or all the others.
- **GitHub (organizations that require two-step verification)**: the admin console only lets its people in
  with the second factor on, and sends them to turn it on.
- **Deleting the account** (8 references): whoever owns something others use hands it over or closes it before
  leaving, and the screen says what holds them. GitHub does not delete the sole owner of an organization
  (https://docs.github.com/en/enterprise-server@3.11/account-and-profile/setting-up-and-managing-your-personal-account-on-github/managing-your-personal-account/deleting-your-personal-account);
  Slack asks to transfer the primary ownership (https://slack.com/help/articles/203953146); Shopify, to transfer
  the store before closing it (https://community.shopify.com/t/brand-assets-and-store-closure-concerns/400728); Zoom
  and Square, to cancel what is paid before deleting, with the password or a code to confirm
  (https://www.ionos.com/digitalguide/online-marketing/social-media/how-to-delete-your-zoom-account,
  https://community.squareup.com/t5/Your-Square-Account-Information/Re-Negative-Balance-Close-Account/m-p/701366);
  Odoo deletes the account from its portal and warns it cannot be recovered
  (https://www.odoo.com/documentation/18.0/administration/odoo_accounts.html); Stripe keeps what the law requires it
  to keep (https://support.stripe.com/questions/i-would-like-to-delete-the-information-stripe-has-collected-from-me).
  Notion deletes its workspaces with the account (https://supademo.com/tutorials/notion/how-to-delete-your-notion-account):
  not here, because deleting a business cancels its plan and switches its till off, and that is its own flow.
- **The payer details when the account is deleted** (8 references): the issued invoices keep their own copy of
  the payer and the rest goes with the account; only what can still be charged holds those details, and with a
  date. Stripe advises, for a deletion request, to leave issued invoices alone, void the subscription invoices
  still open and delete the customer (https://docs.stripe.com/privacy/deletion-requests); Atlassian deletes the
  personal data within 30 days and keeps only the purchase records accounting requires
  (https://support.atlassian.com/atlassian-account/docs/delete-your-atlassian-account/); Odoo deletes except what
  the law makes it keep for billing and tax (https://www.odoo.com/privacy); Holded deletes or anonymises once the
  legal periods end (https://www.holded.com/es/politica-de-privacidad); Shopify and Square do not close with an
  invoice outstanding (https://community.shopify.com/t/to-close-your-store-all-outstanding-invoices-must-be-paid/244113,
  https://community.squareup.com/t5/Payments-Troubleshooting/Negative-Balance-Close-Account/m-p/698891); GitHub
  stops billing when the account is deleted (https://docs.github.com/en/articles/deleting-your-user-account); Zoho
  asks to cancel the subscriptions and deletes everything on closing
  (https://help.zoho.com/portal/en/kb/accounts/manage-your-zoho-account/articles/close-your-zoho-account). Here an
  invoice outstanding for a business already deleted, which stops being billed when it is deleted, does not block:
  it is waited for until paid or cancelled, 90 days at most (the days a deleted business is kept), because the
  invoice must name whom it is issued to (GDPR art. 17.3.b; Commercial Code art. 30, General Tax Law art. 66).
- **GitHub ("Export account data")**: downloading the account's data sits next to deleting it, on the same page.
- **Store review account** (13 references, saas#132): the stores ask for an access the reviewer can use at
  any time, without a one-time code, and the market solves it by exempting that one account from the second
  step, from the administration and without touching the others. Google Play asks for reusable credentials that
  bypass two-step verification or the one-time password (https://support.google.com/googleplay/android-developer/answer/15748846);
  Apple, an active demo account with full access (https://developer.apple.com/app-store/review/guidelines/),
  and rejects one that asks for a code (https://developer.apple.com/forums/thread/762367,
  https://developer.apple.com/forums/thread/750326). Auth0 exempts one specific account
  (https://support.auth0.com/center/s/article/bypass-multi-factor-authentication-for-a-specific-user-in-auth0);
  Microsoft Entra, which Business Central signs in with, excludes accounts from the policy that requires it of everyone
  (https://learn.microsoft.com/en-us/entra/identity/conditional-access/policy-all-users-mfa-strength); Google Workspace,
  with an exception group, never an administrator
  (https://knowledge.workspace.google.com/admin/security/avoid-account-lockouts-when-2-step-verification-is-enforced-by-your-organization);
  Odoo requires it of employees or of everyone (https://www.odoo.com/documentation/19.0/applications/general/users/2fa.html),
  and WooCommerce's plugins exclude accounts or roles
  (https://melapress.com/support/kb/wp-2fa-configure-2fa-policies-enforce/). The fixed code belongs to products without
  a password: Firebase (https://docs.cloud.google.com/identity-platform/docs/test-phone-numbers), Authgear
  (https://docs.authgear.com/strategies/passwordless-demo-user-for-apple-app-review) and Clerk, which discourages it in
  production (https://clerk.com/docs/guides/development/testing/test-emails-and-phones); here there is a password, and
  a fixed code would only be a second password. Turning the code off for everyone, like Square's single switch
  (https://squareup.com/help/us/en/article/5593), would take the security away from every account for one.

## Before you start

- One signs in at erplora.com. In development, the panel is on port 8001 and every email (the codes and the
  links) stays in the local mail folder instead of being sent.
- "Continue with Google" only appears with the Google credentials configured; without them the button is not
  shown.
- Two-step verification (the authenticator app, its recovery codes and the trusted browsers) is off in
  phase 1: its row in **Account › Security** is not shown, no sign-in asks for the app's code and the staff
  get into the admin without it. Switching it on is a phase decision of the platform; the open sessions and
  the code by email always work.

## Screens

### Entrance
The first screen of erplora.com without a session: the logo, "ERPlora Cloud · Global panel" and a card with
two tabs, **Sign in** (the usual one) and **Create account**. Each asks for "Email" and "Password" (with the
eye to see it); "Sign in" also carries "Forgot your password?". Below, "First time here? Create your
account" or "Already have an account? Sign in", "or" and "Continue with Google". At the foot, "By continuing
you agree to our Terms & Privacy Policy".

### Check your email
"Check your email" with "We emailed a code to …", the "Verification code" field, "Verify", "Send a new code"
(only to confirm an email) and "Use a different email". For the code of every sign-in, instead of resending:
"The code lasts 3 minutes. Didn't get it? Sign in again and we will email you a new one."

### Reset your password
"Reset your password" with the email and "Send Reset Link"; once sent, "We've sent password reset
instructions to your email address…", "Back to Login" and "Didn't get the email? Try again".

### Set a new password
The screen of the email's link: "New Password" with the eye, the hint "At least 8 characters; better long,
and without your email." (and, while typing, how strong it looks) and "Change Password". With an expired or
used link, "This password reset link has expired or is not valid.", "Request New Link" and "Back to Login".

### Two-step verification
"Enter the 6-digit code from your authenticator app, or one of your recovery codes.", the code, the "Trust
this browser for 14 days" box (unticked, with "You will not be asked for a code from your app here again for
14 days. Not on a shared computer."), "Verify" and "Back to sign in".

### Two-step verification settings
Opened from **Account › Security**. Three blocks: "Authenticator app" ("On" or "Off", with "Set up
authenticator app" or "Turn off"), "Recovery codes" (how many are left unused, "View" and "Generate new")
and, with the app on, "Trusted browsers" (whether this one is, and "Stop trusting all browsers"). Each action
opens its step in the same card: "Set up your authenticator app" with the QR code and the key, "Recovery
codes" with "Download", "Generate new recovery codes?" and "Turn off the authenticator app?". At the foot,
"Back to settings"; when coming from the admin, "Continue".

### Account › Security › Change your password
The "Password" row with "Change password" opens the "Change your password" dialog: "Current password", "New
password" with its hint, "Cancel" and "Change password". An account that only signs in with Google sees
"Create a password" instead. In the same "Sign-in" block, the "Two-step verification" row says whether it is
on, with "Set up" or "Manage".

### Account › Security › Active sessions
A full-height table with "Device", "Browser", "IP address" and "Last used"; this browser's goes first,
marked "This session", and each other one carries "Close session". On top, "Close other sessions"; below,
"Closing a session also closes it in your businesses.". On a phone, "Load more" instead of pages.

### admin › Accounts › Users and User sessions
The list of accounts carries the action "Close all their sessions", which also ends the trust of their
browsers; **User sessions** shows who signed in where ("Account", "Signed in", "Last used", "IP address" and
"Browser", in the staff's language), read only, with "Close the selected sessions". Only a superuser sees both
actions. An account's page carries under "Permissions" the mark "Store review account" (ACCOUNTS-F49): a superuser
sets and removes it; the rest of the staff only see it.

### Account › Profile
"Your details" (the photo or the initials with "Change photo", "First name", "Last name", the "Email you sign in
with" with "Change" and "Save changes"), "Export your data" to download ("Download my data") and the red card "Delete
your account". At the bottom, the tabs of **Account**: "Profile", "Security", "Preferences" and "API keys".

### Account › Preferences
Three cards that save on their own: "Appearance" ("System", "Light", "Dark"), "Language" ("English",
"Español") and "Email notices" ("Security, invoices and payments", always on, and "Business notices").

### User menu
The name and the email at the top of the side menu (on a phone, inside the menu): "Account", "Help", the
theme and "Sign out".

### Sign out of erplora.com
Where a business's "Sign out" leads on a device without the PIN pad, with the logo and "ERPlora Cloud · Global
panel" of the **Entrance**: "Sign out of erplora.com?", "You are still signed in to erplora.com in this browser as
…", "Sign out" and "Stay signed in".

### Panel menu
"Businesses", "Store", "Billing" and "Account", with the one of the open page marked; at the top, the person's card
(the **User menu**) and at the bottom, ERPlora's logo. On a wide screen it is always in sight; on a tablet or a phone
it opens with the menu button of the top bar.

### Error page
On the public web, with its menu and its footer: "Page not found" and "The page you are looking for does not exist or
has moved.", or "Something went wrong" and "Something went wrong on our side. Please try again in a few minutes.", with
"Back to the home page". In the private part (the account and the entrance): "We couldn't find this page" or
"Something went wrong on our end", with "Home" and "Contact Support".

### Maintenance page
"503 · Maintenance", "We will be back soon", "We are improving ERPlora. Come back in a few minutes; your data is
safe." (or the message the staff wrote, in the visitor's language), "Retry" and "Contact Support".

### admin › Site settings
A single record, "Site settings", without "Add" or "Delete": the "maintenance mode" box, the "message in English" and
the "message in Spanish" (empty, Spanish visitors read the English one), and the date of the last change.

## States of each screen

| State | What the person sees |
|---|---|
| Loading | The submit button is off while the request is on its way, and so is "Download my data" while it prepares the file; the profile and the preferences, their cards loading; the email's link says "Checking your link…"; the two-step verification settings, "Loading…"; the sessions, the table loading. |
| Empty | Without a session, every page of the panel leads to the **Entrance**, which goes back to it after signing in. With this session alone, "Close other sessions" is off; without recovery codes, "Without them, losing your authenticator locks you out of your account." with "Generate recovery codes". |
| Error | Each error appears under its field, with the words of the rule that fails ("Your new password must be different from the current one."); a network failure, "We could not sign you in. Please try again." or "Something went wrong. Please try again.". Settings that do not load, "We could not load your security settings. Please try again." with "Try again"; the sessions, "We could not load your sessions" with "Try again"; the profile, "We could not load your account", and the preferences, "We could not load your preferences", with "Try again". A change of preferences that is not saved goes back to how it was. |
| Throttle | "Too many failed login attempts. Try again later." or "Too many attempts. Please wait a few minutes and try again.", the same whether the account exists or not; if Google does not see a person, "We could not check that you are a person. Try again.". |
| Expired link | "This password reset link has expired or is not valid." with "Request New Link". |
| Expired code | The entrance says "Your code expired or was typed wrong too many times. Sign in again and we will email you a new one." |
| Maintenance | Whoever is not staff sees the **Maintenance page** on any page of erplora.com; the staff with its session open keeps using everything. |
| No permission | An account without the staff mark that opens the admin goes back to the **Entrance**; with a session, the admin refuses it. With two-step verification switched on, staff without the app go to its settings with "Turn on the authenticator app to continue.". |

## Flows

| ID | Flow | Status |
|---|---|---|
| ACCOUNTS-F01 | Create the account | done |
| ACCOUNTS-F02 | Confirm the email with the code | done |
| ACCOUNTS-F03 | Confirm the email before using the panel | done |
| ACCOUNTS-F04 | Sign in with the email and the password | done |
| ACCOUNTS-F05 | Sign in with the authenticator app's code or a recovery one | done |
| ACCOUNTS-F06 | Sign in or create the account with Google | partial |
| ACCOUNTS-F07 | Recover a forgotten password | done |
| ACCOUNTS-F08 | Change the password and end the other sessions with it | done |
| ACCOUNTS-F09 | Sign out | done |
| ACCOUNTS-F10 | Accept the terms and the privacy policy | done |
| ACCOUNTS-F11 | Stop whoever tries passwords, codes or links | done |
| ACCOUNTS-F12 | Know who has signed in | done |
| ACCOUNTS-F13 | Manage the accounts from the admin | done |
| ACCOUNTS-F14 | Turn on the authenticator app and keep the recovery codes | done |
| ACCOUNTS-F15 | See whether two-step verification is on | done |
| ACCOUNTS-F16 | Turn off the authenticator app or generate new codes | done |
| ACCOUNTS-F17 | See whether this browser is trusted and stop trusting them all | done |
| ACCOUNTS-F18 | See and close the open sessions | done |
| ACCOUNTS-F19 | Close an account's sessions from the admin | done |
| ACCOUNTS-F20 | Require the authenticator app from the staff in the admin | done |
| ACCOUNTS-F21 | See and change my profile | done |
| ACCOUNTS-F22 | Choose the language and the appearance | done |
| ACCOUNTS-F23 | Choose which email notices to get | done |
| ACCOUNTS-F24 | Change the theme from the user menu | done |
| ACCOUNTS-F25 | Open the user menu | done |
| ACCOUNTS-F26 | Download my data | done |
| ACCOUNTS-F27 | Delete my account | done |
| ACCOUNTS-F28 | Enter my business from erplora.com | done |
| ACCOUNTS-F29 | Go back to erplora.com from my business | done |
| ACCOUNTS-F30 | Open my account on its own from the app | done |
| ACCOUNTS-F31 | Create an API key | done |
| ACCOUNTS-F32 | Use an API key: what it opens and what it does not | done |
| ACCOUNTS-F33 | Revoke an API key | done |
| ACCOUNTS-F34 | Read the API documentation | done |
| ACCOUNTS-F35 | Erase the accounts unused for two years | done |
| ACCOUNTS-F36 | See who changed an account | done |
| ACCOUNTS-F37 | Erase the audit log older than 90 days | done |
| ACCOUNTS-F38 | Report a problem to support | done |
| ACCOUNTS-F39 | Let each page load only what is erplora.com's | done |
| ACCOUNTS-F40 | Keep in the log what happens, without personal data or secrets | done |
| ACCOUNTS-F41 | Start erplora.com and serve each request | done |
| ACCOUNTS-F42 | Show an error page | done |
| ACCOUNTS-F43 | Put erplora.com in maintenance | done |
| ACCOUNTS-F44 | Clean the expired sessions and codes every day | done |
| ACCOUNTS-F45 | Brake too many requests | done |
| ACCOUNTS-F46 | Send erplora.com's emails | done |
| ACCOUNTS-F47 | Move around the panel | done |
| ACCOUNTS-F48 | Pass erplora.com's master QA | partial |
| ACCOUNTS-F49 | Sign in as a store review account without the email code | done |

### ACCOUNTS-F01 Create the account
Status: done
Actor: anyone
Screen: Entrance › "Create account"
Steps:
1. The person taps "Start free" on the website or opens the **Entrance** and chooses "Create account" (the old sign-up addresses lead to this tab and keep where they were going). They see "Enter your email and choose a password. We'll email you a code to confirm it.".
2. They type their email and a password (with the eye to check it) and tap "Create account".
3. erplora.com checks the password: at least 8 characters, not like their email, not a common password and not only numbers. It creates the account and sends them a six-digit code.
4. The screen moves to **Check your email** (ACCOUNTS-F02); with the right code they are signed in and reach "Create your business".
In: the email (without spaces, in lower case and with full-width letters turned into the usual ones, so that an address that looks like another does not create a second account; the same when inviting it to a business, which invites that account), the password and where they were going (only pages of erplora.com).
Out: the account, active, with its email not confirmed yet and the terms accepted (ACCOUNTS-F10). No business is created. The application that draws this screen is the same door as any other program: the same rules apply to all.
If it fails: a password that does not pass the rules appears under the password and nothing is created; an invalid email (also with full-width letters before the at sign), under the email. An email that already has an account answers just like a new one and its mailbox receives "an account using that email address already exists" with the link to set a password, without a code: this is also how the invited person, whose account has no password yet, sets theirs, and nobody takes over someone else's account. More than 10 sign-ups in an hour from the same network address: "Too many attempts. Please wait a few minutes and try again.".
Involved: hubs (the **Entrance** and "Create your business")

### ACCOUNTS-F02 Confirm the email with the code
Status: done
Actor: anyone
Screen: Check your email
Steps:
1. After creating the account (or when signing in with an email that was never confirmed, ACCOUNTS-F03) the screen says "Check your email" and "We emailed a code to …".
2. The person types the six digits and taps "Verify".
3. If it did not arrive, they tap "Send a new code" (a few seconds after the previous one); if they got the address wrong, "Use a different email" goes back to the **Entrance** with nothing of the wrong address.
4. With the right code the email is confirmed and they are in, without typing the password again: they go where they were going or to the **Entrance** with their session.
In: the six-digit code.
Out: the email confirmed and the session open.
If it fails: a wrong code appears under the field and can be typed again; after 3 failures or once its time is up, the code stops working and the **Entrance** says "Your code expired or was typed wrong too many times…"; a new code asked for too soon is held back.
Involved: none

### ACCOUNTS-F03 Confirm the email before using the panel
Status: done
Actor: system
Screen: Check your email
Steps:
1. A person whose email was never confirmed opens a page of the panel: without a session, they go to the **Entrance**, which keeps where they were going.
2. They type their email and their password: instead of signing in, the screen moves to **Check your email** with a new code.
3. With the right code, the email is confirmed and the person reaches the page they were going to.
In: the account and its email.
Out: no session until the email is confirmed: without one the panel does not open, neither its pages nor its API, and no API keys can be created.
If it fails: without the code there is no session, not even for the store review account (ACCOUNTS-F49), whose mark only removes the code of each sign-in. An account created by an invitation proves its email when setting its password with the email's link (ACCOUNTS-F07).
Involved: hubs (invitations only work for confirmed emails)

### ACCOUNTS-F04 Sign in with the email and the password
Status: done
Actor: any person with an account
Screen: Entrance › "Sign in", Check your email
Steps:
1. On the **Entrance**, the person types their email and their password and taps "Sign in".
2. erplora.com sends a six-digit code to the account's email and the screen moves to **Check your email**.
3. They type the code and tap "Verify".
4. Once in, they go where they were going (a page of erplora.com or the jump to a business) or to the **Entrance** with their session, which shows their businesses.
In: email, password, the code and where they were going (only pages of erplora.com).
Out: that browser's session, which lasts even if the browser is closed; their name and their email in the user menu. Every account gets the code by email at each sign-in with a password, without turning it on and without being able to turn it off (the only exception, the store review account that staff mark, ACCOUNTS-F49); with the authenticator app, the app's code is asked after the email's (ACCOUNTS-F05).
If it fails: an email or a password that do not match, "The email address and/or password you specified are not correct." under the password, whether the account exists or not, with "First time here? Create your account". A wrong code, under the code. With a session already open, the **Entrance** shows the businesses.
Involved: hubs (the **Entrance** with the businesses and the jump to a business)

### ACCOUNTS-F05 Sign in with the authenticator app's code or a recovery one
Status: done
Actor: any person with an account and an authenticator app
Screen: Two-step verification
Steps:
1. After the password and the email's code, an account with an authenticator app moves to **Two-step verification**.
2. They type the 6-digit code from their app, or one of their recovery codes; if the browser is theirs and not shared, they tick "Trust this browser for 14 days" (it comes unticked).
3. They tap "Verify". Once in, they go where they were going.
4. With the box ticked, the next sign-ins in that browser ask only for the password and the email's code for 14 days; any other browser still asks for the app's code.
In: the app's code or a recovery one, and the answer to "Trust this browser for 14 days".
Out: the session open; a recovery code used stops working; with the box, this browser stays trusted for 14 days, only on erplora.com. On the jump to a business, the sign-in counts as done with the app.
If it fails: a wrong code appears under the field and the sign-in keeps waiting; "Back to sign in" abandons the half-done sign-in. If after a right code the answer to the box gets lost (the page is reloaded), the screen says "Your code is right. Do you want to trust this browser?" with "Continue", without asking for the code again. Changing the password or "Stop trusting all browsers" (ACCOUNTS-F17) ends the trust of every browser.
Involved: hubs (the jump to a business)

### ACCOUNTS-F06 Sign in or create the account with Google
Status: partial — the end-to-end test needs the real Google (the test environment does not have its credentials and the button is not shown); the way there and back is tested with Google's answers simulated
Actor: anyone
Screen: Entrance
Steps:
1. On the **Entrance**, the person taps "Continue with Google".
2. They choose their Google account and accept.
3. If there is already an erplora.com account with that email, they sign in to it, Google stays linked and its email receives the notice "third-party account linked"; if there is none, the account is created with the email already confirmed and without a form.
4. Once in, they go where they were going or to the **Entrance** with their session; with the authenticator app, they first go through **Two-step verification**.
In: what Google confirms (email, first and last name) and where they were going.
Out: the Google account linked and, if new, the account, without a password (set with "Forgot your password?"). Google does not ask for the email's code: it already proves it.
If it fails: "Cancel" at Google goes back to the **Entrance**; a Google error or an email Google does not confirm leads to the sign-in's error page, without creating or linking anything. Linking Google to an open session without signing in with it is not allowed: it says that Google is only linked by signing in with the Google account of the email.
Involved: none

### ACCOUNTS-F07 Recover a forgotten password
Status: done
Actor: any person with an account
Screen: Reset your password, Set a new password, Entrance
Steps:
1. On the **Entrance**, the person taps "Forgot your password?", types their email in "Reset your password" and taps "Send Reset Link".
2. The screen says "We've sent password reset instructions to your email address…", with "Back to Login" and "Didn't get the email? Try again".
3. They open the email's link: **Set a new password**, with the hint "At least 8 characters; better long, and without your email." and how strong it looks while typing; they tap "Change Password".
4. They go back to the **Entrance** with "Your password has been changed successfully." and sign in with it (ACCOUNTS-F04).
In: the email; the link, which expires after three days and stops working once used; the new password.
Out: the new password, with everything a password change ends (ACCOUNTS-F08), and the account's email confirmed. It is also the way to set the first password of an account that signed in with Google or was born from an invitation.
If it fails: the screen and the email sent are the same whether the account exists or not (an email without an account receives the invitation to create it). An expired or used link, "This password reset link has expired or is not valid." with "Request New Link". The current password or one that does not pass the rules appears under the field ("Your new password must be different from the current one."). More than 5 requests a minute for one email, held back (ACCOUNTS-F11).
Involved: hubs (the businesses end the account's sessions)

### ACCOUNTS-F08 Change the password and end the other sessions with it
Status: done
Actor: any person with an account
Screen: Account › Security › Change your password
Steps:
1. In **Account › Security**, "Password" row, the person taps "Change password".
2. They type the "Current password" and the "New password", which passes the same rules as at sign-up; the hint says how strong it looks.
3. They tap "Change password": "Password changed. Your businesses will ask you to sign in again."; they stay signed in on this browser.
4. The other browsers with their account are signed out: their open tabs go back to the **Entrance** by themselves. erplora.com asks each of their businesses to end the sessions open with it.
In: the current password and the new one.
Out: the new password; the other erplora.com sessions ended, this browser signed in; the notice to their businesses. The same happens when resetting it (ACCOUNTS-F07).
If it fails: a wrong current password, under its field, and the new one is not saved; the new one equal to the current one, "Your new password must be different from the current one."; one that does not pass the rules, its warnings. The warnings appear in the account's language. More than 5 attempts a minute, "Too many attempts…" without looking at the password, not even the right one: someone else's open session is no way to guess it. An account without a password (it signed in with Google) sees "Create a password", which sends it the link of ACCOUNTS-F07. Today the businesses do not act on the notice yet (it comes in phase 2): a session open in a business goes on until it expires.
Involved: hubs (each business ends the account's sessions)

### ACCOUNTS-F09 Sign out
Status: done
Actor: any person with an account
Screen: User menu, Entrance, Sign out of erplora.com
Steps:
1. In the panel, the person opens the **User menu** (on a phone, inside the menu) and taps "Sign out"; on the **Entrance** with a session, "Sign out" is under their account, and in the Android app it always stays above the system bar.
2. That browser's session ends and the **Entrance** comes back, ready to sign in; the other tabs open with that session go back to the **Entrance** by themselves.
3. A page of the panel opened afterwards leads to the **Entrance**.
4. From a business, on a device without the PIN pad, its "Sign out" ends the business's and opens **Sign out of erplora.com**: "Sign out" ends this one too, as in step 2; "Stay signed in" leaves it open and the **Entrance** comes back with the account's businesses. Without a session, it leads to the **Entrance**.
In: the browser's session.
Out: that browser's session ended. The other sessions, the API keys and the businesses are not touched: to end others there is **Account › Security**.
If it fails: if it could not be ended, "Could not sign out. Try again." and they stay signed in. A loose link ends no session: opening **Sign out of erplora.com** only asks.
Involved: none

### ACCOUNTS-F10 Accept the terms and the privacy policy
Status: done
Actor: anyone
Screen: Entrance, Check your email, admin › the account's page
Steps:
1. At the foot of the **Entrance** (on both tabs and under "Continue with Google") and of **Check your email** one reads "By continuing you agree to our Terms & Privacy Policy", with a link to each text. In the Android app that foot always stays above the system bar, never under it.
2. Creating the account (with a password or with Google) or signing in accepts the versions in force: the account keeps when and which version of each text (the "Last updated" date of each page).
3. When a text changes, the next sign-in accepts the new version and keeps its date; while it does not change, the date of the first acceptance stays.
4. The staff see it in the admin, on the account's page, "Terms and privacy", without being able to change it.
In: creating the account or signing in under the notice.
Out: in the account, the date of the acceptance and the version of the terms and of the privacy policy.
If it fails: a wrong password accepts nothing. An account created by an invitation or by the staff has accepted nothing until its first sign-in, and its page says so.
Involved: public (the pages of the terms and of the privacy policy)

### ACCOUNTS-F11 Stop whoever tries passwords, codes or links
Status: done
Actor: system
Screen: Entrance, Check your email, Reset your password, Set a new password, Two-step verification
Steps:
1. Before anything else, if Google's check is switched on, Google checks without being seen (no checkbox, no puzzle) that whoever sends the form is a person: signing in, creating the account, asking for the reset link, the link's new password, the email's code and "Send a new code", each sign-in's code and the authenticator app's. Under each one, "This site is protected by reCAPTCHA and the Google Privacy Policy and Terms of Service apply.". Since 2026-10-23 it is switched off by default (the network's firewall stops suspicious traffic before it arrives): the forms load nothing of Google and do not show that notice, and the throttles below stay the same. "Continue with Google" does not go through here: Google checks it.
2. Each wrong password spends from its account's budget and from the network address's (5 in 5 minutes each); once spent, not even the right one gets in until the time is up. A right sign-in gives its attempt back: the owner spends no budget.
3. Before looking at the password, each network address has 30 sign-ins a minute.
4. The email's codes allow 3 attempts; the sign-in one lasts 3 minutes. On top of that, each network address has 10 refused codes in 5 minutes, from the email or from the authenticator app; a right one spends nothing.
5. Reset links, 10 an hour per network address and 5 an hour per account; the link's form, 20 submissions a minute per address; a new code, one every 10 seconds per account; sign-ups, 10 an hour per address; the password change, 5 a minute per account.
In: the email being tried, the network address of the caller and, with the check switched on, Google's approval.
Out: the throttle's answer, the same whether the account exists or not and after the same number of attempts: "Too many failed login attempts. Try again later." on the **Entrance** or "Too many attempts. Please wait a few minutes and try again."; with the check switched on, if Google does not see a person, "We could not check that you are a person. Try again." and nothing is done.
If it fails: if the shared memory of the counters does not answer, the throttle opens (the door stays usable) and a warning is left in the log. With the check switched on, if Google does not answer, signing in, the sign-in's code and the authenticator app's go on (the password, the code and the throttles already guard them) and an error is left in the log; the other forms are refused with the message above.
Involved: none

### ACCOUNTS-F12 Know who has signed in
Status: done
Actor: any person with an account
Screen: User menu, Account › Profile
Steps:
1. Once signed in, the panel draws the account: its name (or its email, if it has no name) and its email in the **User menu**, in its language and with its theme.
2. **Account › Profile** shows its email, whether it is confirmed, its first and last name and its photo.
3. When entering a business, erplora.com tells the business who is entering: their identifier, their email, their name, their language and their role in it.
In: the session.
Out: nothing saved.
If it fails: without a session, the panel leads to the **Entrance**.
Involved: hubs (the jump to a business)

### ACCOUNTS-F13 Manage the accounts from the admin
Status: done
Actor: ERPlora staff
Screen: admin › Accounts › Users
Steps:
1. The staff search for an account by email or name, or filter by active, staff and language.
2. Its page shows the email, the password (only "Reset password"), the personal details and the language, the permissions and groups, the dates, "Terms and privacy" (read only), the preferences and the photo if it changed them (read only) and its businesses.
3. "Add user" creates an account with its email and a password (or without one, which is set with the email's link).
In: what the staff type.
Out: the account, identified by its email (in lower case and unique) and with its own identifier.
If it fails: an email that already has an account is not saved. Support see the accounts without being able to add, change or delete; an account without the staff mark does not get into the admin.
Involved: hubs (the account's businesses)

### ACCOUNTS-F14 Turn on the authenticator app and keep the recovery codes
Status: done
Actor: any person with an account
Screen: Account › Security, Two-step verification settings
Steps:
1. In **Account › Security**, the "Two-step verification" row says "Off"; the person taps "Set up".
2. In **Two-step verification settings** they tap "Set up authenticator app": "Set up your authenticator app" shows a QR code and, under "Can't scan? Enter this key by hand:", the key.
3. They scan it with their app (Google Authenticator, 1Password…), type the number it shows and tap "Turn on". If their last sign-in is not recent, they first confirm it is them with their password, and the same number still works.
4. They see their ten "Recovery codes" once ("10 of 10 unused"), keep them with "Download" and tap "Back": the app is "On".
In: the app's number and, if needed, the password.
Out: the account's authenticator app and ten single-use recovery codes; from the next sign-in the app's code is asked (ACCOUNTS-F05). The codes are downloaded as a text file made in the browser itself.
If it fails: a wrong number appears under the field and the app is not turned on; "Cancel" goes back without turning anything on; a network failure, "Something went wrong. Please try again.".
Involved: none

### ACCOUNTS-F15 See whether two-step verification is on
Status: done
Actor: any person with an account
Screen: Account › Security, Two-step verification settings
Steps:
1. In **Account › Security**, "Sign-in" block, the "Two-step verification" row says "On" ("After your password, a code from your authenticator app. Keep your recovery codes safe.") or "Off".
2. "Manage" (or "Set up") leads to **Two-step verification settings**, which says the same of the app and how many recovery codes are left unused.
In: the session.
Out: nothing kept.
If it fails: if it cannot be read, the row says neither on nor off and still leads to the settings. With two-step verification switched off on the platform, the row is not shown.
Involved: none

### ACCOUNTS-F16 Turn off the authenticator app or generate new codes
Status: done
Actor: any person with an account and an authenticator app
Screen: Two-step verification settings
Steps:
1. In **Two-step verification settings**, "Recovery codes" says how many are left unused; "View" shows them and "Generate new" asks "Generate new recovery codes?" with "This replaces your 10 unused codes.".
2. "Generate" shows the new ones, to download them again; the previous ones stop working.
3. To remove the app, "Turn off" asks "Turn off the authenticator app?" with "You will sign in with your password and the code we email you."; "Turn off" removes it and "Keep it on" goes back without touching anything.
4. If their last sign-in is not recent, before generating or turning off they confirm it is them with their app's code.
In: the confirmation and, if needed, the app's code.
Out: new recovery codes, or the app removed: the sign-in is the password and the email's code again, which is never turned off.
If it fails: a network failure, "Something went wrong. Please try again." and nothing changes. Without unused codes, "You have used all your recovery codes. Generate a new set now." with "Generate new codes".
Involved: none

### ACCOUNTS-F17 See whether this browser is trusted and stop trusting them all
Status: done
Actor: any person with an account and an authenticator app
Screen: Two-step verification settings
Steps:
1. In **Two-step verification settings**, with the app on, "Trusted browsers" says "Browsers you trust skip the code from your app for 14 days." and whether this one is: "This browser is trusted until …" or "This browser is not trusted.".
2. If they lost a device or signed in on someone else's computer, the person taps "Stop trusting all browsers".
3. The screen says "No browser is trusted now: each one will ask for the code from your app at its next sign-in." and "This browser is not trusted.".
In: the session.
Out: no browser of the account is trusted; the app and the recovery codes keep working without setting anything up, and this session stays in. Event `accounts.browser_trust.revoked`.
If it fails: if this browser cannot be checked, "We could not check this browser."; a failure to stop trusting, "Something went wrong. Please try again." and nothing changes. Changing the password also ends the trust of every browser.
Involved: none

### ACCOUNTS-F18 See and close the open sessions
Status: done
Actor: any person with an account
Screen: Account › Security › Active sessions
Steps:
1. In **Account › Security**, "Active sessions" lists each open session with its "Device", "Browser", "IP address" and "Last used"; this browser's goes first, marked "This session".
2. "Close session" on a row closes it at once and says "Session closed on …"; if it is the ERPlora app, it first asks "Close the app on …", because it may be charging at a till.
3. "Close other sessions" says how many will be closed, the apps too, and once confirmed closes all but this one: "Sessions closed: 2".
In: the session picked, or "the others".
Out: those sessions closed, here and in the account's businesses; this one stays in and the list refreshes by itself. Event `accounts.session.closed`.
If it fails: a list that does not load says "We could not load your sessions" with "Try again"; a refused close appears in a notice and the session stays on the list. A session of another account is not found. Today the businesses do not act on the notice yet (it comes in phase 2): a session open in a business stays until it expires.
Involved: hubs (each business ends the account's sessions)

### ACCOUNTS-F19 Close an account's sessions from the admin
Status: done
Actor: ERPlora staff
Screen: admin › Accounts › Users and User sessions
Steps:
1. In an incident, a superuser looks for the account in **admin › Accounts › Users**, ticks it and picks "Close all their sessions".
2. The admin says "Sessions closed: 1.": the account is out of all its browsers and each one will ask for its app's code next time.
3. In **User sessions** they see who signed in where (account, address, browser and dates); a superuser ticks some and picks "Close the selected sessions".
In: the accounts or the sessions ticked.
Out: those sessions closed, also in the account's businesses; with the account's action, besides, no browser of it is trusted (its app and its recovery codes keep working). The account's own list of sessions refreshes by itself, and the log keeps who did it. Event `accounts.session.closed`.
If it fails: support see the sessions without being able to close them; nobody changes or deletes a session by hand, because deleting the row would not end it. An account that no longer exists is not found. Today the businesses do not act on the notice yet (it comes in phase 2): a session open in a business stays until it expires.
Involved: hubs (each business ends the account's sessions)

### ACCOUNTS-F20 Require the authenticator app from the staff in the admin
Status: done
Actor: ERPlora staff
Screen: admin, Two-step verification settings
Steps:
1. With two-step verification switched on on the platform, a staff person (support too) without an authenticator app opens the admin.
2. Instead of the admin they reach **Two-step verification settings**, with "Turn on the authenticator app to continue.".
3. They turn the app on (ACCOUNTS-F14) and tap "Continue": they go back to the admin page they were opening.
4. From then on each sign-in asks for the app's code (or a trusted browser skips it) and the admin lets them in.
In: the staff account and where they were going (only pages of erplora.com).
Out: the staff get into the admin, and jump to the businesses' admin, only with their authenticator app; with two-step verification off, as until now.
If it fails: recovery codes alone are not enough; an account without the staff mark does not get into the admin even with the app; "Continue" never leads outside erplora.com.
Involved: hubs (the jump to the businesses' admin)

### ACCOUNTS-F21 See and change my profile
Status: done
Actor: any person with an account
Screen: Account › Profile
Steps:
1. From the **User menu**, "Account" opens **Account › Profile**: "Your details" with the photo (or the initials), "First name", "Last name" and the "Email you sign in with".
2. The person changes their first or last name: "Save changes" turns on when something changes ("It turns on when you change something.").
3. They tap "Save changes": "Changes saved", and the user menu and the businesses they enter call them that.
4. "Change photo" uploads a photo (JPEG, PNG or WebP), kept clean of the camera's hidden data; "Remove photo" goes back to the initials.
5. The email changes with "Change": a code arrives at the new address and, once typed, that one becomes the one to sign in with; the old one gets a notice of the change.
In: first and last name, the photo, or the new email and its code.
Out: the profile changed, in the panel and in every business entered afterwards. Every account has its profile from the start, with nothing to fill in. The same is read and saved from any program with the person's session.
If it fails: an empty first name is not saved ("Write your first name."); a photo that is no image or is too big says why and keeps the one there was; a network failure, "We could not reach ERPlora…" and nothing changes. The billing details are not here: they belong to **Billing**.
Involved: hubs (the businesses get the name at sign-in)

### ACCOUNTS-F22 Choose the language and the appearance
Status: done
Actor: any person with an account
Screen: Account › Preferences
Steps:
1. In **Account › Preferences**, "Appearance" offers "System", "Light" and "Dark" ("System" follows the mode of their device).
2. The person picks one: the panel is painted that way at once and "Preferences saved" appears; there is no save button.
3. In "Language" they pick "English" or "Español": the panel changes language at once, and so do the mails we send them.
4. In another browser or after reloading, the panel opens with the account's appearance and language.
In: the appearance and the language.
Out: the account's appearance and language, the same on all its devices; the language is also the one of its mails and the one its businesses get at sign-in. In the panel the account's language rules; the public website follows the one chosen on it or the browser's.
If it fails: if it cannot be saved, the control goes back to what it was and a notice says why; if the preferences do not load, "We could not load your preferences" with "Try again". No currency is chosen: ERPlora charges in euros.
Involved: hubs (the language when entering a business)

### ACCOUNTS-F23 Choose which email notices to get
Status: done
Actor: any person with an account
Screen: Account › Preferences
Steps:
1. In **Account › Preferences**, "Email notices" shows "Security, invoices and payments", always on ("Always on: sign-in codes, security notices, invoices, payments and anything that needs you to act.").
2. Below, "Business notices" ("When a business of yours is ready to open."), on from the start.
3. The person turns it off: "Preferences saved", and the next business they create no longer mails them that it is ready.
4. They turn it on again and the mail comes back.
In: "Business notices".
Out: with it off, the mail that a business is ready is not sent; the business opens all the same and the panel says so. The other mails are always sent: the codes and the security notices, the invoices and the failed payments, the deleted business with its date to recover it, and anything that asks them to act, such as connecting WhatsApp again.
If it fails: if it cannot be saved, the switch goes back to how it was and a notice says why.
Involved: hubs (the mail of a ready business), billing (the invoices and the payments, always)

### ACCOUNTS-F24 Change the theme from the user menu
Status: done
Actor: any person with an account
Screen: User menu
Steps:
1. The person opens the **User menu** (on a phone, inside the menu) and sees "Theme" with three buttons: light, dark and system, with the current one marked.
2. They tap one: the panel is painted that way at once.
3. The theme stays in their account: it is the same as **Account › Preferences › Appearance** and the panel opens with it on any device, without showing the other one first.
4. The pages of the public website are painted with the account's theme while the session is open; without a session, they follow the device's mode.
In: the theme chosen.
Out: the account's theme.
If it fails: if it cannot be saved, the panel keeps the chosen theme and a notice says "Couldn't save the appearance to your account.".
Involved: none

### ACCOUNTS-F25 Open the user menu
Status: done
Actor: any person with an account
Screen: User menu
Steps:
1. At the top of the side menu (on a phone, inside the menu) is the person's card: their initials, their name and their email.
2. Tapping it opens the **User menu**: "Account", "Report a problem", "Help", "Theme" and "Sign out".
3. "Account" leads to **Account › Profile**, from where **Security**, **Preferences** and **API keys** are reached; "Report a problem", to ACCOUNTS-F38; "Help", to the help; "Theme", to ACCOUNTS-F24; "Sign out", to ACCOUNTS-F09.
In: the session.
Out: nothing saved.
If it fails: without a session there is no menu: the panel leads to the **Entrance**.
Involved: none

### ACCOUNTS-F26 Download my data
Status: done
Actor: any person with an account
Screen: Account › Profile
Steps:
1. In **Account › Profile**, the "Export your data" card says "A copy of your account, your businesses and your ERPlora invoices, in a file other apps can read.".
2. The person taps "Download my data": the button is off while it is prepared.
3. The browser saves the file "erplora-data-" with the day's date.
In: the session.
Out: a file with their data: the account (email, name, language, sign-up, last sign-in and the terms accepted), their appearance and notices, their photo, their email addresses, their linked Google account, their open sessions, their API keys (without the key), the businesses they belong to with their role in each one, and the ERPlora invoices they see, each with its lines and its recipient as issued. Nothing of another account.
If it fails: if it cannot be prepared, a notice says why and the button comes back; without a connection, "We could not reach ERPlora…". Nothing is saved half-done.
Involved: hubs (their businesses), billing (their ERPlora invoices)

### ACCOUNTS-F27 Delete my account
Status: done
Actor: any person with an account
Screen: Account › Profile
Steps:
1. In **Account › Profile**, the "Delete your account" card says up front whether something holds it: if they own a business, "You own 1 business: transfer or delete it before deleting your account." with the business's name, which leads to its settings; if they pay for someone else's business (with their payment details, or because after a hand-over its plan is still charged to their card), that its owner enter their own payment details. Meanwhile "Delete account" is off.
2. With nothing holding it, they tap "Delete account": the dialog says what goes (the account, the photo, the preferences and the API keys, and every session, also in the apps and in their businesses), that it cannot be undone and that "Your ERPlora invoices are kept for as long as the law requires.".
3. They type their email to confirm and tap "Delete account". If their last sign-in is not recent, first they confirm it is them: with their password or, if they only sign in with Google, by signing in with Google again.
4. The session ends and they reach the public website.
In: the email typed and, if needed, the password or Google.
Out: the account deleted, with its photo, its preferences, its keys and all its sessions, here and in its businesses; it stops being a member of other people's businesses. Its ERPlora invoices stay, with the recipient of their issue date and no link to the account. Its payer details (legal name, tax ID, address and billing email) and its payment customer are erased at once if nothing is left to charge; if an ERPlora invoice is still unpaid, they are kept until it is paid or cancelled and 90 days at most, and on that day the unpaid invoice is cancelled and they are erased. Event `accounts.profile.deleted`.
If it fails: an owned or paid business holds it (the dialog says so too if it changed meanwhile); whoever pays for a business cannot be removed from it either, so there is no way to stop seeing it and keep paying for it; a deleted business, in its 90 days to be recovered, no longer holds it. More than 10 passwords in a minute when confirming are stopped, not even the right one gets in: someone else's open session is no way to guess it. A network failure is said in the dialog and nothing is deleted.
Involved: hubs (the businesses that hold it and the ones it leaves), billing (the invoices that are kept and the payer details that are erased)

### ACCOUNTS-F28 Enter my business from erplora.com
Status: done
Actor: any person with an account who is a member of a business
Screen: Entrance, the business, Entrance › sign-in error
Steps:
1. The person opens their business: with "Open" on the **Entrance** or in **Businesses**, or by typing their business's address. The business sends them to erplora.com with a mark of that browser.
2. If they already have a session on erplora.com, erplora.com checks they are a member of that business and sends them back to it with a one-time pass, without showing them anything.
3. If they do not, the **Entrance** asks them to sign in (with their email, their password and the mailed code, or with Google; ACCOUNTS-F04 and ACCOUNTS-F06) and, once in, goes on to the business by itself.
4. The business redeems the pass with erplora.com, opens its own session and the person appears inside, on the page they were going to.
In: the business they are going to, the page they were going to in it and the mark of the browser that started the jump.
Out: a pass valid for one minute, usable once and only for that business; it travels hidden in a form, never in the address, and the page that carries it is neither stored nor told to other websites. The business receives who is entering (ACCOUNTS-F12) and opens its own session, which shares nothing with erplora.com's.
If it fails: if they are not a member of that business, "You don't have access to this hub", naming only the business's address, never its name, with "Back to the hub" and "Contact Support"; a link that leads to no business, "This sign-in link doesn't lead to a hub". More than 20 jumps in 5 minutes, "Too many attempts" with "You have opened your businesses too many times in a few minutes. Wait a few minutes and open your business again.", without a pass. A pass that expired, was used, is for another business or is not redeemed by the business itself opens nothing, and the business does not let in a browser that did not start the jump. With two-step verification on and the authenticator app active, it first asks for the app's code.
Involved: hubs (the person's businesses and "Open")

### ACCOUNTS-F29 Go back to erplora.com from my business
Status: done
Actor: any person with an account
Screen: Entrance, Account, Businesses
Steps:
1. Inside their business, the person taps a link to erplora.com: manage their account, their business or their plan.
2. If that browser has their erplora.com session (the one they used to enter the business), the page opens without asking for anything.
3. If it does not (another browser, the app's, or the session ended), the **Entrance** asks them to sign in and, once in, takes them to that same page.
In: the erplora.com page they are going to (only erplora.com pages).
Out: the page open with their erplora.com session. The business hands no credential to erplora.com: each keeps its own session.
If it fails: an address that is not erplora.com's is not followed after signing in: it leads to the **Entrance** with their session. Signing out of erplora.com does not sign out of the business (ACCOUNTS-F09).
Involved: hubs (the business's links to erplora.com)

### ACCOUNTS-F30 Open my account on its own from the app
Status: done
Actor: any person with an account
Screen: Account › Profile
Steps:
1. In the installed app, the person taps manage their account on erplora.com: the app opens the account's address it already knew, with the mark of the account on its own.
2. erplora.com takes them to **Account › Profile** keeping the mark; the old addresses of the sessions and the preferences lead to **Account › Security** and **Account › Preferences**.
3. Without a session in that browser, the **Entrance** asks them to sign in and then goes back to the account with the mark.
4. The account is drawn without anything that sells: the menu has no "Store". From there they change their profile, their password, their sessions, their preferences and their API keys, and can delete the account.
In: the mark of the account on its own.
Out: the account open without what sells; the mark stays in that browser's session until it ends.
If it fails: without the mark, the same address opens the account of the usual panel, with "Store".
Involved: none

### ACCOUNTS-F31 Create an API key
Status: done
Actor: any person with an account; a superuser of the staff, for a team account
Screen: Account › API keys, admin › Accounts › API keys
Steps:
1. In **Account › API keys**, the person taps "New key": "New API key" asks for the "Name", its "Permissions" ("Businesses · read", "Businesses · write", "Invoices · read") and when it "Expires" ("In 90 days", "In 30 days" or "Never").
2. If their last sign-in is not recent, first they confirm it is them with their password (or by signing in with Google again).
3. They tap "Create key": they see the whole key once, with "Copy the key" and "Copy it now and keep it somewhere safe: you will not see it again."; with "I have saved it", the window closes, says "Key created: «…»" and the key stays on the list with its beginning only.
4. A superuser of the staff creates a key for a team account from the admin, with "Add API key": they choose the account, the name, the permissions and the expiry, and the page shows them the key once, "Copy it now: it will not be shown again.".
In: the name, the permissions, the expiry and, if needed, the password.
Out: the key, which acts as its account and only with its permissions; erplora.com keeps only its fingerprint and its beginning. The account gets the email "New API key in your ERPlora account", without the key. Event `accounts.apikey.created`.
If it fails: without a name, "Give it a name: it is how you will tell your keys apart."; a permission that does not exist, "Unknown permission: …"; with 50 keys that still work, "You already have 50 API keys: revoke one you no longer use.". A key is never shown again, neither on the list nor in the admin. The admin creates none for a customer's account, which creates its own, and support creates none. A key cannot create keys nor manage the account.
Involved: none

### ACCOUNTS-F32 Use an API key: what it opens and what it does not
Status: done
Actor: a program with an account's key
Screen: none (the erplora.com API)
Steps:
1. A program (Postman, an integration, a script) calls the erplora.com API with the key in its header.
2. erplora.com finds the key by its beginning, compares its fingerprint and checks it is neither revoked nor expired and that its account is still active.
3. The call becomes that account's: it sees what its account sees, nothing of others, and only what its permissions open: "Businesses · read" reads its businesses and "Invoices · read", its ERPlora invoices.
4. The rest of the API (the account, its sessions and its keys, and what is not offered to keys) is refused to any key.
In: the key.
Out: the answer, as if its account called; the key's last use is noted at most every 10 minutes.
If it fails: a key that does not exist, revoked, expired or of a deactivated account, "Invalid API key."; without the permission, "This API key is missing the permission this operation needs: …"; on what is not offered to keys, "API keys cannot be used here: this operation is only for signed-in people.". More than 600 calls a minute with one key, or more than 30 wrong keys a minute from the same address, "Too many requests. Try again in a minute.". An empty header is as no key.
Involved: hubs (its businesses), billing (its invoices)

### ACCOUNTS-F33 Revoke an API key
Status: done
Actor: any person with an account; a superuser of the staff
Screen: Account › API keys, admin › Accounts › API keys
Steps:
1. In **Account › API keys**, the person taps "Revoke" on the key's row: "Revoke "…"" says "Whatever uses this key stops working at once. It cannot be undone: you would have to create another one.".
2. They confirm with "Revoke key": "Key revoked: "…"" and the key leaves the list.
3. Facing an incident, a superuser of the staff finds the key in the admin (by its name, its beginning or its account; each row says its "Permissions" in the words of the account, such as "Businesses · read"), marks it and chooses "Revoke the selected keys (they stop working at once)": "Keys revoked: 1.".
In: the chosen key.
Out: the key opens nothing from the next call on; its row stays as the trail, with the date it was revoked, and its account's list refreshes by itself. There is no "rotate": another one is created and the old one revoked. Event `accounts.apikey.revoked`.
If it fails: revoking it twice changes nothing; another account's key is not found ("That API key does not exist."). Revoking does not ask for the password. Support sees the keys without being able to revoke them.
Involved: none

### ACCOUNTS-F34 Read the API documentation
Status: done
Actor: any person with an account
Screen: Account › API keys, API documentation
Steps:
1. In **Account › API keys**, under the list, the person taps "API documentation": it opens in another tab.
2. The documentation shows each part of the API (the account, the businesses, the invoices…), with its calls, what they ask for and what they answer, and a search box. It is in English, like the API itself.
3. To try the API from a program, they download the schema from the documentation itself and open it in Postman with an API key (ACCOUNTS-F31).
In: the session.
Out: nothing saved. The documentation is read only: it makes no calls with the account's data.
If it fails: without a session, the **Entrance** asks them to sign in and then goes back to the documentation; an API key alone does not open it. If the schema does not load, "We could not load the API documentation. Reload the page to try again.". The schema itself is public, as Stripe's and GitHub's are, so that Postman can import it.
Involved: none

### ACCOUNTS-F35 Erase the accounts unused for two years
Status: done
Actor: system
Screen: none (a weekly task of erplora.com)
Steps:
1. Once a week, erplora.com looks for the active accounts that are not staff and have not signed in on erplora.com for two years (or never signed in and were created more than two years ago).
2. It skips those that belong to a business that is not deleted, as owners, payers or members: whoever works in their business every day does not go through erplora.com and would look unused.
3. Each of the others is erased as when its owner deletes the account (ACCOUNTS-F27): with its photo, its preferences, its API keys, its email addresses, its linked Google account and all its sessions, here and in the businesses.
4. ERPlora's invoices stay, with the recipient of their issue date and without a link to the account.
In: the date of each account's last sign-in on erplora.com (or of its creation).
Out: the unused accounts erased, each with its event `accounts.profile.deleted` on its own channel; no other account changes. Just before erasing it, the account is read again: if it signed in meanwhile, it stays.
If it fails: an account that cannot be erased stays in the log (by its identifier, never its email) and the task goes on with the others; at the end, the task ends in error for the team to see, and that account is tried again the next week. If a pass is already running, the second one does nothing. The team can count what would be erased without erasing anything.
Involved: hubs (the businesses that hold the account), billing (the invoices that stay)

### ACCOUNTS-F36 See who changed an account
Status: done
Actor: ERPlora superuser (or a team member allowed to see the log)
Screen: erplora.com's admin › "Audit log"
Steps:
1. Every change to an account (name, email, language, whether it is active, whether it is staff), to its access to a business and to its API keys (creating one, revoking it), every session that opens and every change to what is charged and to the fiscal documentation (a business's subscription and its paid apps, its payer, its invoices and their VeriFactu state, a failed charge, a purchase in progress, a plan change waiting, the prices of the plans and of the apps, the VAT rules, ERPlora's details on the invoices, the promo codes, a business's signed authorisation and its review, and ERPlora's stamp) is written down: what changed, from which value to which, when, who did it and from which address.
2. The superuser opens "Audit log" in the admin, filters by resource type or searches by email, and opens an entry to see its changes.
3. Nobody can create, change or delete an entry by hand: they are only read.
In: the changes to the accounts, to what is charged and to the fiscal documentation, made from the panel, with an API key, from the admin, by erplora.com's tasks or by Stripe when it charges.
Out: one entry per change, naming whoever acted at that moment (the account with the open session or the owner of the API key; nobody in an erplora.com task or after signing out) and the visitor's real address, never the one its browser claims.
If it fails: a secret is never written down (neither the password, nor the API key, nor a session's, nor a Stripe purchase's, nor the link that opens a Stripe invoice, nor an authorisation's documents or the stamp) nor what moves by itself (the last sign-in, a key's last use, the last time a session was seen, the counters, the retries sending an invoice to the AEAT). Writing a change down never changes an invoice or its VeriFactu record. If the account is deleted, its entries keep its email and no link to it until they are erased after 90 days (ACCOUNTS-F37). A team member without the permission cannot open it.
Involved: none

### ACCOUNTS-F37 Erase the audit log older than 90 days
Status: done
Actor: system
Screen: none (a daily task of erplora.com)
Steps:
1. Once a day, erplora.com erases, in batches, the audit log entries (ACCOUNTS-F36) older than 90 days.
2. Those of the last 90 days stay, also those of an account already deleted.
In: the date of each log entry.
Out: the log with only the last 90 days; nothing else changes.
If it fails: if a batch cannot be erased, the task ends with an error so the team sees it; what was erased before stays erased and the next pass goes on from there. If a pass is already running, the second does nothing. The team can count what would be erased without erasing anything, and change how many days are kept.
Involved: none

### ACCOUNTS-F38 Report a problem to support
Status: done
Actor: any person with an account
Screen: Report a problem
Steps:
1. In the **User menu**, "Report a problem" (also in the account opened from the app). The screen says "Tell us what went wrong. We will reply by email.".
2. They write "Subject" and "What happened?" ("Describe the steps and what you expected to happen") and press "Send report", which waits until both are written. Below, the screen warns: "Your account, your businesses, the page you came from and your browser go with your report.".
3. They see "Report sent", with the email support will answer to, and "Back", which leads to the screen they came from.
4. From a business, "Report a problem" in the hub's user menu opens the same in a window, without leaving the business, for whoever entered with their account (never with a PIN): the report arrives the same way, with the business it is sent from (BASE-F108).
In: the subject and what happened.
Out: a mail to the support mailbox with the subject, the text and, below, the account, its businesses, where it comes from (the panel or the hub, and from the hub, the business), the screen they came from and their browser; when answering, support writes straight to the person. Nothing is kept on erplora.com and no ticket is opened.
If it fails: "Add a subject." or "Describe the problem, please." under its field; after five reports in an hour, "Too many attempts. Please try again in a few minutes." (the limit counts the panel's and the hub's together); if the mail cannot leave, a notice with the support address to write to directly. In every case what was written stays and can be sent again.
Involved: the hub (its user menu, BASE-F108)

### ACCOUNTS-F39 Let each page load only what is erplora.com's
Status: done
Actor: system
Screen: none (every page of the panel and of the public web)
Steps:
1. Each page of erplora.com tells the browser what it may load and run on it: the programs, styles, fonts and images of erplora.com itself, and only the programs the page marks as its own when it is served. No libraries from other servers.
2. The panel also allows what its payments with Stripe and the sign-in with Google need, and its forms only post to erplora.com, to Google and to the businesses. No page of the panel can be put inside another website; the public web, only inside erplora.com.
3. erplora.com's admin follows the panel's list, except the rule its own code does not meet, so all its controls work.
4. The installed app keeps talking to its printer and its drawer from any page.
5. If the browser blocks something, it tells erplora.com.
In: the page being served.
Out: nothing kept: the list travels with each page. What the browser blocks stays in erplora.com's log.
If it fails: what is not on the list is neither loaded nor run, even if someone slips it into the page; the reports of one browser are braked at 60 an hour (ACCOUNTS-F45).
Involved: public (the public web)

### ACCOUNTS-F40 Keep in the log what happens, without personal data or secrets
Status: done
Actor: system
Screen: none (erplora.com's log, which the team reads)
Steps:
1. Every line erplora.com writes to its log goes through a filter first.
2. The filter covers emails, phone numbers, the NIF, the NIE and the CIF, the IBAN, card numbers, passwords (also the one inside a connection address) and the API, Stripe, session and access keys, each with a mark that says what was there.
3. The rest stays as it is: the names of erplora.com's events, the identifiers and the figures, so the team can follow what happened.
In: each line of the log.
Out: the line with what is personal and secret covered; nothing else changes. A failed sign-in is logged whole, except the password.
If it fails: no line is dropped for carrying a secret: it is covered and written. A huge line, or one made to choke the filter, is cleaned without stalling the log.
Involved: none

### ACCOUNTS-F41 Start erplora.com and serve each request
Status: done
Actor: system
Screen: none
Steps:
1. erplora.com starts with the settings of its environment (production, pre or the developer's computer): the secrets, the database, the cache and the mail come from the environment, never from the code.
2. It serves each request behind AWS's load balancer, which tells it whether it arrived encrypted; in production the cookies only travel encrypted and the browser stays on the encrypted version.
3. A real-time connection nobody asked for (a WebSocket) is closed cleanly, without leaving an error in the log.
4. It charges in euros: the plans and Stripe use that currency and there is no other to choose.
In: the settings of the deployment's environment.
Out: the service running; nothing kept.
If it fails: without a mandatory key (the fiscal documents' one in production) it does not start and says which one is missing. With the cache down, the brakes let requests through and everything keeps working. With the database down, the liveness check keeps answering and the "ready" one warns.
Involved: none

### ACCOUNTS-F42 Show an error page
Status: done
Actor: anyone
Screen: Error page, erplora.com's admin
Steps:
1. Whoever reaches an address of the public web that does not exist sees "Page not found" and "The page you are looking for does not exist or has moved.", with the web's menu and footer and "Back to the home page".
2. In the private part (the account, the entrance) they see "We couldn't find this page", with "Home" and "Contact Support".
3. If erplora.com fails, the public web shows "Something went wrong" and "Something went wrong on our side. Please try again in a few minutes."; the private part, "Something went wrong on our end". Both in the visitor's language.
4. The staff sees the admin with ERPlora's name: "ERPlora Cloud" at the top and "Administration" on its front page.
In: the address asked for and the visitor's language.
Out: the error page; nothing kept. A program connected through the API gets the error in its format, never the page.
If it fails: the failure page is painted even with the database down: it reads nothing from it.
Involved: public (its error pages)

### ACCOUNTS-F43 Put erplora.com in maintenance
Status: done
Actor: ERPlora superuser; any visitor
Screen: admin › Site settings, Maintenance page
Steps:
1. A superuser opens "Site settings" in the admin (always the same record: there is no other to create or delete), ticks "maintenance mode" and, if they want, writes the "message in English" and the "message in Spanish".
2. On saving, the admin says "Maintenance mode is on: only the ERPlora staff with a session uses erplora.com.".
3. From then on, whoever visits erplora.com sees "We will be back soon" with "We are improving ERPlora. Come back in a few minutes; your data is safe." (or the staff's message, in their language), "Retry" and "Contact Support"; search engines understand the web is back soon.
4. The staff with its session open keeps using everything, and a staff member without one signs in through the **Entrance** on the way to the admin, also with the code of their authenticator app.
5. On unticking it, the admin says "Maintenance mode is off: erplora.com is open to everyone." and everyone gets in again.
In: the switch and the two messages.
Out: the switch saved, which every server of erplora.com applies at once (and, if the notice were lost, within a minute at most). The liveness checks, the admin, the businesses' calls and Stripe's and Meta's notices keep working. A program connected through the API gets "ERPlora is under maintenance. Try again in a few minutes.".
If it fails: if the switch cannot be read (the database down), erplora.com stays open and the log says why. The staff's message is shown as text, never as code. An API key does not count as a staff session, nor does a deactivated staff account.
Involved: hubs (their calls keep working), billing (Stripe's notices keep working), whatsapp (Meta's notices keep working)

### ACCOUNTS-F44 Clean the expired sessions and codes every day
Status: done
Actor: system
Screen: none (a daily task of erplora.com)
Steps:
1. Once a day, erplora.com deletes the expired sessions, the "Active sessions" rows whose session no longer exists (with their address and their browser), the one-time codes of the jump to a business past their 60 seconds and the email changes whose code is past its 15 minutes.
2. What is still valid stays: no open session and no code still valid changes.
3. Like erplora.com's other tasks, the infrastructure's clock runs it at its time; a task that fails leaves its error in sight of the team and runs again on its next turn.
In: the expiry date of each session and of each code.
Out: what expired, deleted; nothing is written to the audit log.
If it fails: if a run is already going, the second does nothing; a failure ends the task with an error and what was deleted before stays deleted. The team can count what would be deleted without deleting anything.
Involved: none

### ACCOUNTS-F45 Brake too many requests
Status: done
Actor: system
Screen: none
Steps:
1. Each door that can be abused carries its own brake, counted per address or per account: the sign-in, the codes and the links (ACCOUNTS-F11), the jump to a business (ACCOUNTS-F28), the API keys (ACCOUNTS-F32), reporting a problem (ACCOUNTS-F38), the web's contact form and the browser's security reports (60 an hour per address).
2. Past the brake, the request is refused without doing anything and the screen says so.
3. The address that counts is the caller's real one, the one the load balancer gives: an address typed by hand into the request does not start a new counter, and one account's or key's brake is not spent by another.
In: the caller's address or account.
Out: the counters, in the cache the servers share; nothing in the database.
If it fails: with the cache down, the brakes let requests through and erplora.com keeps working. A braked security report is not written to the log.
Involved: public (the contact form)

### ACCOUNTS-F46 Send erplora.com's emails
Status: done
Actor: system
Screen: none
Steps:
1. Something in erplora.com has to tell a person: a code, a link, an invitation, an invoice, a change in their business.
2. The email carries ERPlora's brand, the same in all of them: the coloured stripe on top, the logo, the text and the footer "Sent by ERPlora" with the link to erplora.com. A code stands alone, in its box, and the links can be clicked.
3. Each email comes in two versions that say the same, formatted and as text, so it reads in any mail program, and in the language of whoever gets it; the ERPlora team's (reported problems, the contact form, authorisations to review), in the team's.
4. Only the logo is downloaded from the email, from erplora.com: nothing else is asked of another website.
5. The email leaves from ERPlora's address through AWS's mail service.
6. If the service does not answer, erplora.com waits a few seconds, never minutes, and tries once more.
In: the notice, its data, the recipient and their language.
Out: the email sent, formatted and as text. On the developer's computer and in the tests, the email is written to a folder and never leaves.
If it fails: an email that does not leave is handled by whoever asks for it (for example, reporting a problem shows the support address to write to directly) and the screen never hangs waiting.
Involved: billing, fiscal and whatsapp (their emails already carry the brand); hubs (those of a business's people, invitations and roles move to it with their port)

### ACCOUNTS-F47 Move around the panel
Status: done
Actor: any person with an account
Screen: Panel menu
Steps:
1. The panel's menu has "Businesses", "Store", "Billing" and "Account"; at the top, the person's card opens the **User menu** (ACCOUNTS-F25), and at the bottom is ERPlora's logo.
2. On a wide screen the menu is always in sight; on a tablet or a phone it opens with the menu button of the top bar.
3. Each entry opens its page without reloading the panel and is marked as the current one.
4. The pages outside the panel (the entrance, the error pages, the maintenance page) use the person's theme, or their browser's if they have not signed in.
In: the session.
Out: nothing kept.
If it fails: without a session, the **Entrance**, which goes back to the page after signing in.
Involved: hubs ("Businesses"), billing ("Store" and "Billing")

### ACCOUNTS-F48 Pass erplora.com's master QA
Status: partial — what the QA asks for and is still missing is already a partial flow of its app: the exit package when a business is deleted and the measure of its use (hubs), the distance-selling threshold in the EU (billing), deleting what was created inside a demo (public) and opening the drawer on payment (printing, in the Hub); a business's people, invitations and roles come with their port in hubs
Actor: ERPlora's QA team
Screen: all of erplora.com's
Steps:
1. The team goes through erplora.com as a new customer: the public web with its plans (Free as the way in, without a card) and the demo; creating the account and confirming the email; creating the free business with a single question and entering it; moving it to a paid plan with a Stripe test card.
2. It checks in the panel what the customer does with their businesses: seeing them with their status and use, changing plan, retrying a payment, cancelling, deleting a business and restoring it.
3. It checks the billing: the invoices with their VAT (also the reverse charge within the EU), the promo codes that give trial days and the return to Free when the subscription ends.
4. On a real business, it sells and checks that the receipt comes with its QR, signed for the AEAT in its test environment, and that it prints.
In: the pre environment and test accounts.
Out: each point of the QA, with the flow that covers it and its automated test in the browser; what makes no sense on today's platform stays out with its reason (see "For whoever maintains it").
If it fails: a point no flow covers is a QA failure and is noted in the app that owns it.
Involved: hubs, billing, public, apps and fiscal; in the Hub, verifactu, invoice and printing

### ACCOUNTS-F49 Sign in as a store review account without the email code
Status: done
Actor: ERPlora staff and the reviewer of an app store
Screen: admin › Accounts › Users, Entrance › "Sign in"
Steps:
1. Staff create in the admin the account the stores review ERPlora's app with (ACCOUNTS-F13): an account only for that, with a long password and a test business, without real customer data. Its email is confirmed once, like any account's (ACCOUNTS-F03).
2. On that account's page they tick "Store review account" ("Signs in with its password, without the mailed code. Only for the account Google Play and the App Store review the app with.") and save.
3. They give the email and the password to each store, in its access section for the review; before each release on Google Play, the automatic check of ERPlora's app signs in with them.
4. The reviewer opens the **Entrance**, on the web or in the app, types the email and the password and taps "Sign in": without going through **Check your email**, they go where they were going or to the **Entrance** with their session, which shows their business, and enter it (ACCOUNTS-F28).
5. If the account stops being used for the stores or its password leaks, staff remove the mark or reset the password from the same page: from the next sign-in the code is asked again.
In: the mark, which only staff set and remove, and the account's email and password.
Out: that browser's session, as in ACCOUNTS-F04 but without the email code; the session shows among the account's open ones like any other (ACCOUNTS-F18 and ACCOUNTS-F19), and the audit log notes who set or removed the mark, when and from which address (ACCOUNTS-F36).
If it fails: an account without the mark keeps asking for the code at each sign-in with a password (ACCOUNTS-F04). The person neither sees nor changes the mark from their account, support see it in the admin without being able to change it, and a staff account cannot carry it: "A staff account cannot be a store review account.", and it is not saved. The mark skips nothing else: an unconfirmed email asks for its code (ACCOUNTS-F03), the authenticator app, if the account has one, asks for its own (ACCOUNTS-F05), and a wrong password, the attempt limits (ACCOUNTS-F11) and the same answer whether the account exists or not stay as for any other.
Involved: erplora.com's admin (the account's page and the audit log); ERPlora's app (repository ERPlora/app), whose Google Play check signs in with this account before each release; saas#132 and app#7
