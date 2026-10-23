<!-- generated from WORKBOOK.md sha256:427a42803d20b13ad76f24cafb4dcfedf981345e7c60152454cf2cf6238c00ac -->

## What it is for and who it is for

The fiscal gateway is the door through which **every** VeriFactu record reaches the AEAT. The Hub of each
business builds, chains and validates its records; the gateway only presents them and returns the AEAT's answer
as it came, keeping nothing. There are two ways:

- **With ERPlora's seal**: ERPlora presents on behalf of the business thanks to the authorisation the business
  signs (Anexo I of Agreement 17, the "grant of direct representation") and that a person of ERPlora reviews.
  Without an approved authorisation, the seal is not used for that business.
- **With the business's own certificate**: the certificate lives in the database of its Hub and only passes
  through the gateway during each submission; ERPlora does not keep it.

Who uses it:

- The **Hub of each business** (VeriFactu app) sends, queries and tests the connection.
- ERPlora's **platform business** presents the invoices ERPlora issues to its customers.
- **ERPlora's staff** change the seal when it expires, get the notice of every authorisation waiting for review
  and decide in the admin.
- The **owner and the admins** of the business get a mail at every step of their authorisation.

## Reference adopted

- **The AEAT's social collaborator** (Agreement 17 and its Anexo I): the software presents on behalf of its
  customer with its own seal, after receiving and keeping the signed authorisation, as invoicing programs and
  adhered accounting firms do.
- **Stripe's and Square's identity verification**: the person uploads their documents, a person of the team
  reviews them, and every step (received, approved, returned with its reason) arrives by mail; the team gets
  notice of what waits, with no documents in the mail.
- **Cloud providers' certificate rotation**: two slots (the current one and the next), automatic switch before
  expiry and an alarm with margin.

## Before you start

- In development and in the test environment, the gateway only presents to the AEAT's test environment; the real
  environment is only reached from the production deployment.
- ERPlora's seal certificate, which it presents with, is not uploaded on any screen: the team puts it in the
  deployment's secrets. The image of the stamp and signature the authorisation model carries is uploaded, in
  "Representative's stamp".
- Without an address of its own for the review desk, its notices go to the support mailbox.

## Screens

### Admin › Signed authorisations › Review

The queue of authorisations with their business, version, status and date; each one opens in "Review the signed
authorisation", with its documents and the buttons "Approve", "Return to the customer" and "Withdraw the
approval". It is the page the notice to the review desk leads to. While no representative's stamp is uploaded,
the queue says so on top and links to "Representative's stamp".

### Admin › Signed authorisations › Representative's stamp

ERPlora's stamp and signature that every authorisation model carries: when and by whom it was uploaded, its size
and its preview, the link "Download the model a business receives", the button "Upload" (or "Replace the stamp" if
there is one already) and "Remove the stamp", which asks to tick the confirmation box.

### Mails

Not a screen: the notices of every step of the authorisation arrive by mail to the review desk and to the
business, each in its language.

## States of each screen

| State | What the person sees |
|---|---|
| Loading | The admin loads the queue like any list of the admin. |
| Empty | The queue without authorisations says there is none. |
| Error | A step that cannot be taken (approving one that no longer waits, returning without a reason) is explained at the top of the page and changes nothing. |
| No permission | Whoever is not on the team with the permission to review does not see the queue nor can decide; whoever has no permission over the stamp does not see "Representative's stamp", and whoever may only see it cannot upload nor remove it. |
| No stamp | The queue and "Representative's stamp" warn that the model customers download goes without ERPlora's stamp and signature; also if the stamp kept cannot be read with the current key. |

## Flows

| ID | Flow | Status |
|---|---|---|
| FISCAL-F01 | Change the ERPlora seal it presents with | done |
| FISCAL-F02 | Present a business's records to the AEAT | done |
| FISCAL-F03 | Keep the authorisation's documents encrypted | done |
| FISCAL-F04 | Tell the team before the seal expires | done |
| FISCAL-F05 | Tell the review desk and the business of every step of the authorisation | done |
| FISCAL-F06 | Put ERPlora's seal and signature on the authorisation model | done |
| FISCAL-F07 | Watch the customers' powers of attorney (ZP01) | discarded |

### FISCAL-F01 Change the ERPlora seal it presents with
<!-- origen: fi:saas/django-admin#admin-verifactuconfig-singleton-vistas-operador fi:saas/support/billing-fiscal#modelo-verifactuconfig fi:saas/support/billing-fiscal#serializer-form-verifactuconfigform-load_pkcs12 -->
Status: done
Actor: ERPlora's staff
Screen: none
Steps:
1. A person of the team puts ERPlora's new seal, with its password, in the "next" slot of the deployment's secrets; the "current" slot keeps the one in use.
2. On start, the gateway opens each slot with its password and checks it is a certificate with its key that may connect to the AEAT; one that does not open, does not allow it or has expired is not used, and the log says which slot failed, never what it holds.
3. The gateway presents with the "current" one until 7 days before it expires; from then on, with the "next" one if it is valid. Without a "next" one, it goes on with the "current" one while it has not expired.
4. With the switch done, the person moves the new seal to the "current" slot and leaves the "next" one empty for the next time.
In: ERPlora's seal and its password, in the deployment's secrets.
Out: the seal each submission through ERPlora is presented with; the Hub's connection test says which one and until when it is valid.
If it fails: without any usable seal, every submission through ERPlora is refused before touching the AEAT because there is no seal and the Hub keeps it to retry; it never presents with an expired seal.
Involved: the Hub (VERIFACTU-F10 tests the connection and sees the seal), FISCAL-F04 (warns before expiry)

### FISCAL-F02 Present a business's records to the AEAT
<!-- origen: fi:saas/support/billing-fiscal#service-aeatclient -->
Status: done
Actor: system (the business's Hub)
Screen: none
Steps:
1. The Hub sends the gateway the envelope already signed and validated, with the business, its tax ID, the environment (test or production) and the way: ERPlora's seal or the business's own certificate, which travels in that submission only.
2. Before touching the AEAT, the gateway checks that the business exists, that the envelope only names that taxpayer, that the production environment is only asked from the production deployment and, through ERPlora, that the business has its approved authorisation and that it is of the same tax ID.
3. It presents the envelope to the AEAT door that applies (the one for entity seals or the holder's) with a secure connection with the certificate, and returns the AEAT's answer as it came.
4. With the same door, the Hub queries what the AEAT already has, or tests whether it could present now and with which certificate, without sending anything.
In: the Hub's envelope, the business, the tax ID, the environment, the way and, through its own way, the business's certificate with its password.
Out: the AEAT's answer as it came (the Hub interprets it); in the connection test, whether it is ready and with which certificate.
If it fails: every refusal says why and comes before touching the AEAT: unknown business, tax ID that does not match, authorisation not approved, no seal, no certificate, invalid or expired certificate, or production from a deployment that is not. The gateway waits at most 5 s to connect to the AEAT and 30 s for its answer, and never more than 41 s in all, less than the Hub waits for it, so the Hub always hears from the gateway before giving up; without an answer from the AEAT, the Hub knows whether the submission may have arrived or not so as not to repeat it blindly; with too many submissions at once, it asks it to retry. The business's certificate is never kept nor appears in a log or in an error.
Involved: the Hub (VERIFACTU-F15 sends, VERIFACTU-F27 queries, VERIFACTU-F10 tests the connection), FISCAL-F01 (the seal), FISCAL-F05 (the approved authorisation)

### FISCAL-F03 Keep the authorisation's documents encrypted
<!-- origen: fi:saas/support/billing-fiscal#service-fields-encryptedcharfield-encrypt_bytes-decrypt_bytes -->
Status: done
Actor: system
Screen: Admin › Signed authorisations › Review
Steps:
1. When the Hub sends a business's signed authorisation, the signed model, the copy of the identity document and, if there are any, the signature sample and the proof of representation are encrypted before they are kept.
2. Only the page "Review the signed authorisation" decrypts them, for the person of the team who decides; neither the queue, nor the business's panel, nor the notices nor what is sent to the Hub carry a document.
3. The encryption key is its own and mandatory in production: without it the deployment does not start, and the application's general key is never taken in its place.
In: the documents the business uploads from its Hub.
Out: the documents kept encrypted; the database and its backups never hold them in the clear, nor does the server's disk while they arrive: they are received in memory.
If it fails: a key that cannot encrypt is said on start and the deployment stops; a document kept with another key does not open and the review page says so instead of showing it.
Involved: FISCAL-F05 (the review), the Hub (VERIFACTU-F05 uploads the authorisation)

### FISCAL-F04 Tell the team before the seal expires
<!-- origen: fi:saas/support/billing-fiscal#task-check_certificate_expiry -->
Status: done
Actor: system
Screen: none
Steps:
1. Every day, a scheduled task opens the two slots of the seal and publishes how many days are left to the one that expires first (negative if it already expired).
2. With less than 30 days, the team's alarm goes off, and the team puts the new seal in the "next" slot (FISCAL-F01).
In: the two slots of the seal.
Out: the days left to the seal, in the platform's metrics, and the alarm with less than 30.
If it fails: a slot that does not open makes the task fail, which also warns the team, never saying what it holds; with both slots empty it publishes nothing. The businesses' own certificates live in their Hub, which warns of their expiry.
Involved: FISCAL-F01

### FISCAL-F05 Tell the review desk and the business of every step of the authorisation
<!-- origen: old-saas:SAAS_DASHBOARD-F159 gh:saas#2051 -->
Status: done
Actor: system
Screen: Admin › Signed authorisations › Review
Steps:
1. When a business sends its signed authorisation from its Hub, the review desk gets a mail with the business, the version and the link to "Review the signed authorisation", with no documents, tax IDs nor names of people.
2. At the same time, the owner and the admins of the business get, in their language, that ERPlora has received it and that they will get the answer by mail.
3. When a person of the team presses "Approve", they get that the authorisation is now in force and that ERPlora may now send their invoices to the tax agency with its seal.
4. If they press "Return to the customer" or "Withdraw the approval", they get it with the reason that was written and that they should send it again from the VeriFactu app of the business.
In: every step of the authorisation: sent, approved, returned or withdrawn.
Out: a mail to the review desk for every authorisation that waits and one to every owner or admin for every step; in the panel, the status at once (`fiscal.representation.changed`).
If it fails: the mails leave once the step is saved, never before; a mail that does not leave stays in the log with the authorisation and does not undo the step, and the authorisation stays in the admin's queue. A version a newer one replaced tells nobody: the new one tells. These notices arrive even if the person turned the business notices off, because they decide whether ERPlora may send their invoices.
Involved: the Hub (VERIFACTU-F05 and VERIFACTU-F06 send the authorisation), FISCAL-F03 (the documents)

### FISCAL-F06 Put ERPlora's seal and signature on the authorisation model
<!-- origen: old-saas:SAAS_DASHBOARD-F160 -->
Status: done
Actor: ERPlora's staff
Screen: Admin › Signed authorisations › Representative's stamp
Steps:
1. In "Representative's stamp", a person of the team with the permission over the stamp chooses a PNG of ERPlora's stamp and signature, of 2 MB at most and with a transparent background, and presses "Upload": "Stamp uploaded: every model downloaded from now on carries it." shows on top and the page shows its preview. A new one replaces the one there was.
2. With "Download the model a business receives" they check how it comes out: the official model of the Anexo I with ERPlora written as representative (name and tax ID), the stamp and signature in the representative's box and a second page with the data protection information (article 13 of the GDPR) the model obliges to give.
3. When the business downloads the model from the VeriFactu app of its Hub to sign it, it gets it like this; if the Hub sends the business's details (tax ID, name and address), they come written in the block of the natural person or in that of the entity according to its tax ID, and if not, those blanks are left to fill in by hand.
4. To remove it, they tick "Yes, remove it: the models go without it until another is uploaded." and press "Remove the stamp".
In: the PNG of ERPlora's stamp and signature, kept encrypted; ERPlora's details as a company; the business's details, if the Hub sends them.
Out: the authorisation model with ERPlora, its stamp and its signature and the data protection sheet; the change is recorded (`fiscal.stamp.changed`).
If it fails: a file that is not a PNG, that is damaged or that is over 2 MB is refused with its reason ("The stamp must be a PNG image.") and nothing changes. Without a stamp uploaded, or with one the current key cannot read, the model goes without it and the queue and "Representative's stamp" warn so that someone uploads it. A business detail the model cannot write or a tax ID that is not Spanish is refused and the Hub says it could not download it.
Involved: the Hub (VERIFACTU-F05 downloads the model), FISCAL-F05 (the review of the signed authorisation)

### FISCAL-F07 Watch the customers' powers of attorney (ZP01)
<!-- origen: old-saas:SAAS_DASHBOARD-F162 -->
Status: discarded — ERPlora presents through the social collaboration of Agreement 17 with the signed authorisation of the Anexo I, which the team reviews and withdraws (FISCAL-F05), not through powers of attorney before the AEAT; there is no register of powers of attorney to watch
Actor: system
Screen: none
Steps:
1. Each business's authorisation is reviewed, approved, returned or withdrawn in the admin, and the Hub sees it at every change.
2. There is no separate register of powers of attorney nor a daily query to the AEAT.
In: nothing.
Out: nothing.
If it fails: does not apply.
Involved: FISCAL-F05
