<!-- generated from WORKBOOK.md sha256:bc8ac353a2bd38e292ce017e9e56e303eb03b2d7a6126427aabd9a9cd5372331 -->

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
- **GitHub ("Export account data")**: downloading the account's data sits next to deleting it, on the same page.

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
browsers; **User sessions** shows who signed in where, read only, with "Close the selected
sessions". Only a superuser sees both actions.

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

## States of each screen

| State | What the person sees |
|---|---|
| Loading | The submit button is off while the request is on its way, and so is "Download my data" while it prepares the file; the profile and the preferences, their cards loading; the email's link says "Checking your link…"; the two-step verification settings, "Loading…"; the sessions, the table loading. |
| Empty | Without a session, every page of the panel leads to the **Entrance**, which goes back to it after signing in. With this session alone, "Close other sessions" is off; without recovery codes, "Without them, losing your authenticator locks you out of your account." with "Generate recovery codes". |
| Error | Each error appears under its field, with the words of the rule that fails ("Your new password must be different from the current one."); a network failure, "We could not sign you in. Please try again." or "Something went wrong. Please try again.". Settings that do not load, "We could not load your security settings. Please try again." with "Try again"; the sessions, "We could not load your sessions" with "Try again"; the profile, "We could not load your account", and the preferences, "We could not load your preferences", with "Try again". A change of preferences that is not saved goes back to how it was. |
| Throttle | "Too many failed login attempts. Try again later." or "Too many attempts. Please wait a few minutes and try again.", the same whether the account exists or not. |
| Expired link | "This password reset link has expired or is not valid." with "Request New Link". |
| Expired code | The entrance says "Your code expired or was typed wrong too many times. Sign in again and we will email you a new one." |
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
| ACCOUNTS-F27 | Delete my account | partial |

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
If it fails: a password that does not pass the rules appears under the password and nothing is created; an invalid email (also with full-width letters before the at sign), under the email. An email that already has an account answers just like a new one and its mailbox receives "an account with this address already exists" with the link to set a password, without a code: this is also how the invited person, whose account has no password yet, sets theirs, and nobody takes over someone else's account. More than 10 sign-ups in an hour from the same network address: "Too many attempts. Please wait a few minutes and try again.".
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
If it fails: without the code there is no session. An account created by an invitation proves its email when setting its password with the email's link (ACCOUNTS-F07).
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
Out: that browser's session, which lasts even if the browser is closed; their name and their email in the user menu. Every account gets the code by email at each sign-in with a password, without turning it on and without being able to turn it off; with the authenticator app, the app's code is asked after the email's (ACCOUNTS-F05).
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
4. The other browsers with their account are signed out, and erplora.com asks each of their businesses to end the sessions open with it.
In: the current password and the new one.
Out: the new password; the other erplora.com sessions ended, this browser signed in; the notice to their businesses. The same happens when resetting it (ACCOUNTS-F07).
If it fails: a wrong current password, under its field, and the new one is not saved; the new one equal to the current one, "Your new password must be different from the current one."; one that does not pass the rules, its warnings. The warnings appear in the account's language. More than 5 attempts a minute, "Too many attempts…" without looking at the password, not even the right one: someone else's open session is no way to guess it. An account without a password (it signed in with Google) sees "Create a password", which sends it the link of ACCOUNTS-F07.
Involved: hubs (each business ends the account's sessions)

### ACCOUNTS-F09 Sign out
Status: done
Actor: any person with an account
Screen: User menu, Entrance
Steps:
1. In the panel, the person opens the **User menu** (on a phone, inside the menu) and taps "Sign out"; on the **Entrance** with a session, "Sign out" is under their account.
2. That browser's session ends and the **Entrance** comes back, ready to sign in.
3. A page of the panel opened afterwards leads to the **Entrance**.
In: the browser's session.
Out: that browser's session ended. The other sessions, the API keys and the businesses are not touched: to end others there is **Account › Security**.
If it fails: if it could not be ended, "Could not sign out. Try again." and they stay signed in. A loose link ends no session.
Involved: none

### ACCOUNTS-F10 Accept the terms and the privacy policy
Status: done
Actor: anyone
Screen: Entrance, Check your email, admin › the account's page
Steps:
1. At the foot of the **Entrance** (on both tabs and under "Continue with Google") and of **Check your email** one reads "By continuing you agree to our Terms & Privacy Policy", with a link to each text.
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
Screen: Entrance, Check your email, Reset your password
Steps:
1. Each wrong password spends from its account's budget (5 in 5 minutes) and from the network address's (10 a minute); once spent, not even the right one gets in until the time is up. A right sign-in gives its attempt back: the owner spends no budget.
2. Before looking at the password, each network address has 30 sign-ins a minute.
3. The email's codes allow 3 attempts; the sign-in one lasts 3 minutes.
4. Reset links, 5 a minute per email and 20 per network address; sign-ups, 10 an hour per address; the password change, 5 a minute per account.
In: the email being tried and the network address of the caller.
Out: the throttle's answer, the same whether the account exists or not and after the same number of attempts: "Too many failed login attempts. Try again later." on the **Entrance** or "Too many attempts. Please wait a few minutes and try again.".
If it fails: if the shared memory of the counters does not answer, the throttle opens (the door stays usable) and a warning is left in the log.
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
2. Its page shows the email, the password (only "Reset password"), the personal details and the language, the permissions and groups, the dates, "Terms and privacy" (read only), the preferences, the photo and its businesses.
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
2. Tapping it opens the **User menu**: "Account", "Help", "Theme" and "Sign out".
3. "Account" leads to **Account › Profile**, from where **Security**, **Preferences** and **API keys** are reached; "Help", to the help; "Theme", to ACCOUNTS-F24; "Sign out", to ACCOUNTS-F09.
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
Status: partial — the payer details of their businesses (legal name, tax ID and address) stay stored without an owner when the account is deleted; removing them waits until billing guarantees that no further invoice of those businesses arrives
Actor: any person with an account
Screen: Account › Profile
Steps:
1. In **Account › Profile**, the "Delete your account" card says up front whether something holds it: if they own a business, "You own 1 business: transfer or delete it before deleting your account." with the business's name, which leads to its settings; if they pay for someone else's business, that its owner enter their own payment details. Meanwhile "Delete account" is off.
2. With nothing holding it, they tap "Delete account": the dialog says what goes (the account, the photo, the preferences and the API keys, and every session, also in the apps and in their businesses), that it cannot be undone and that "Your ERPlora invoices are kept for as long as the law requires.".
3. They type their email to confirm and tap "Delete account". If their last sign-in is not recent, first they confirm it is them: with their password or, if they only sign in with Google, by signing in with Google again.
4. The session ends and they reach the public website.
In: the email typed and, if needed, the password or Google.
Out: the account deleted, with its photo, its preferences, its keys and all its sessions, here and in its businesses; it stops being a member of other people's businesses. Its ERPlora invoices stay, with the recipient of their issue date and no link to the account. Event `accounts.profile.deleted`.
If it fails: an owned or paid business holds it (the dialog says so too if it changed meanwhile); a deleted business, in its 90 days to be recovered, no longer holds it. More than 10 passwords in a minute when confirming are stopped, not even the right one gets in: someone else's open session is no way to guess it. A network failure is said in the dialog and nothing is deleted.
Involved: hubs (the businesses that hold it and the ones it leaves), billing (the invoices that are kept)
