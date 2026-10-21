<!-- generated from WORKBOOK.md sha256:707ba4c7767a0239d7aace0bb45bb9952a4fa40d6f3423bb44def3e17182e0e9 -->

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
- **The person with an account** changes their password from **Account › Security**.
- **ERPlora staff** see and manage the accounts from the admin, without being able to change what an
  account accepted.

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

## Before you start

- One signs in at erplora.com. In development, the panel is on port 8001 and every email (the codes and the
  links) stays in the local mail folder instead of being sent.
- "Continue with Google" only appears with the Google credentials configured; without them the button is not
  shown.
- The second step with the authenticator app is off in phase 1: nobody sees it today.

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
"Enter the 6-digit code from your authenticator app, or one of your recovery codes.", the code, "Verify" and
"Back to sign in".

### Account › Security › Change your password
The "Password" row with "Change password" opens the "Change your password" dialog: "Current password", "New
password" with its hint, "Cancel" and "Change password". An account that only signs in with Google sees
"Create a password" instead.

### User menu
The name and the email at the top of the side menu (on a phone, inside the menu): "Account", "Help", the
theme and "Sign out".

## States of each screen

| State | What the person sees |
|---|---|
| Loading | The submit button is off while the request is on its way; the email's link says "Checking your link…". |
| Empty | Without a session, every page of the panel leads to the **Entrance**, which goes back to it after signing in. |
| Error | Each error appears under its field, with the words of the rule that fails ("Your new password must be different from the current one."); a network failure, "We could not sign you in. Please try again." or "Something went wrong. Please try again.". |
| Throttle | "Too many failed login attempts. Try again later." or "Too many attempts. Please wait a few minutes and try again.", the same whether the account exists or not. |
| Expired link | "This password reset link has expired or is not valid." with "Request New Link". |
| Expired code | The entrance says "Your code expired or was typed wrong too many times. Sign in again and we will email you a new one." |
| No permission | An account without the staff mark that opens the admin goes back to the **Entrance**; with a session, the admin refuses it. |

## Flows

| ID | Flow | Status |
|---|---|---|
| ACCOUNTS-F01 | Create the account | done |
| ACCOUNTS-F02 | Confirm the email with the code | done |
| ACCOUNTS-F03 | Confirm the email before using the panel | done |
| ACCOUNTS-F04 | Sign in with the email and the password | done |
| ACCOUNTS-F05 | Sign in with the authenticator app's code or a recovery one | partial |
| ACCOUNTS-F06 | Sign in or create the account with Google | partial |
| ACCOUNTS-F07 | Recover a forgotten password | done |
| ACCOUNTS-F08 | Change the password and end the other sessions with it | done |
| ACCOUNTS-F09 | Sign out | done |
| ACCOUNTS-F10 | Accept the terms and the privacy policy | done |
| ACCOUNTS-F11 | Stop whoever tries passwords, codes or links | done |
| ACCOUNTS-F12 | Know who has signed in | done |
| ACCOUNTS-F13 | Manage the accounts from the admin | done |

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
Out: that browser's session, which lasts even if the browser is closed; their name and their email in the user menu.
If it fails: an email or a password that do not match, "The email address and/or password you specified are not correct." under the password, whether the account exists or not, with "First time here? Create your account". A wrong code, under the code. With a session already open, the **Entrance** shows the businesses.
Involved: hubs (the **Entrance** with the businesses and the jump to a business)

### ACCOUNTS-F05 Sign in with the authenticator app's code or a recovery one
Status: partial — the second step is off in phase 1 and nobody sees it yet; its screen and its door are done and tested with it on, and its end-to-end test goes with the second factor
Actor: any person with an account and an authenticator app
Screen: Two-step verification
Steps:
1. After the password and the email's code, an account with an authenticator app moves to **Two-step verification**.
2. They type the 6-digit code from their app, or one of their recovery codes, and tap "Verify".
3. Once in, they go where they were going.
In: the app's code or a recovery one.
Out: the session open; a recovery code used stops working.
If it fails: a wrong code appears under the field; "Back to sign in" abandons the half-done sign-in.
Involved: none

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
