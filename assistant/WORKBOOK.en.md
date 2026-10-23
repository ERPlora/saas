# Workbook — AI assistant (assistant)
Prefijo: ASSISTANT
Alcance MVP: phase 1 (erplora.com's AI gateway: the providers ERPlora pays, their encrypted keys, their models, which model answers and the trial of a model before it answers; the Hub's turn and the voice come with part 2 of the port)
Estado de la app: en construcción

> User manual and specification of the SaaS app `assistant` (erplora.com). It tells what ERPlora's staff do so the AI
> assistant answers: add a model provider and its key, choose its models, decide which model answers and try a model
> first. It is not published in the store: it is the team's and QA's reference. No customer sees these screens; the
> assistant a business uses lives in the Hub.

## What it is for and who uses it

The Hub never talks to the provider of an AI model: it talks to erplora.com, which keeps the provider's key, decides
which model answers and calls it. So the key never leaves erplora.com and the AI spend is controlled in one place.

- Each provider's key is kept encrypted; it is typed once and never shown again: only its last four characters, to
  recognise it.
- One model answers and, if its provider fails, a fallback one.
- Before a model answers it can be tried from the admin, with how long it takes, what it consumes and what it costs.

Who uses it:

- **ERPlora's staff**, in erplora.com's admin, with the AI gateway's permissions. The support group does not have
  them: the keys are ERPlora's spend.
- The **system**: the Hub's assistant turn picks the answering model with this configuration.

## Adopted reference

- **AI gateways** (OpenRouter, Portkey, Cloudflare AI Gateway, Vercel AI Gateway, LiteLLM's router): a primary model
  and a fallback one if the provider fails; the providers' keys in the gateway, never in the client.
- **The providers' consoles** (OpenAI, Anthropic, Google AI Studio, DeepSeek): the key is shown once when created
  and then only its end; the list of models comes from the provider's own API
  (https://platform.openai.com/docs/models, https://docs.anthropic.com/en/docs/about-claude/models).
- **ERPlora's old product** (the SaaS's `apps/assistant`): providers with their key and models on one page, the
  policy of which model answers and the tester with cost and latency.

## Before you start

- erplora.com needs its credentials encryption key in the environment; without it no provider key can be kept and
  the page says so on saving.
- Each provider needs an active readable key for its models to answer or be tried.
- The prices per million tokens of each model are typed by the staff: the providers' APIs do not give them. Without
  a price, the trial says the consumption and a cost of zero.

## Screens

### Admin: AI providers
List of the providers with their API, whether enabled and the state of their key: «…» and the last four characters,
«No key» or «Unreadable: type the key again». Each provider's page has its keys inside: label, the «Key» field (typed
once, never shown; empty keeps the one there was), whether active, when it changed and by whom.

## States of each screen

| State | What the person sees |
|---|---|
| Loading | The normal loading of an admin page. |
| Empty | «0 AI providers» and the empty list; a provider without a key says «No key». |
| Error | The error in red next to the field: «Use an https address: the provider's key travels to it.», «Type the provider's key.», «The key of the credentials is not configured: no provider key can be kept.». |
| No permission | Without the gateway's permissions, the admin answers there is no permission; whoever may only look sees the pages without the «Key» field. |

## Flows

| ID | Flow | Estado |
|---|---|---|
| ASSISTANT-F01 | Add an AI provider | hecho |
| ASSISTANT-F02 | Keep a provider's key without it being seen | hecho |

### ASSISTANT-F01 Add an AI provider
<!-- origen: fi:saas/support/auth-services#modelo-aiprovider, fi:saas/django-admin#admin-aiprovider, old-saas:SAAS_ASSISTANT-F22 -->
Estado: hecho
Actor: ERPlora's staff
Pantalla: Admin: AI providers
Pasos:
1. In «AI providers», click «Add AI provider».
2. Type its name and a short identifier (for example «openai»), choose the API it speaks (OpenAI, Anthropic, Google Gemini or DeepSeek; a provider compatible with OpenAI's is «OpenAI» with its address) and, if it is not the provider's own, its address.
3. Leave it enabled or off and save.
Entra: name, identifier, API, address, enabled, notes.
Sale: the provider in the list, ready for its key and its models.
Si falla: an address that is not https is refused with «Use an https address: the provider's key travels to it.» (only an address of the machine itself is accepted without https); a repeated identifier is refused; without permission, the admin does not let in.
Implicados: none

### ASSISTANT-F02 Keep a provider's key without it being seen
<!-- origen: fi:saas/support/auth-services#modelo-aiprovidercredential, fi:saas/django-admin#admin-aiprovidercredential -->
Estado: hecho
Actor: ERPlora's staff
Pantalla: Admin: AI providers
Pasos:
1. On the provider's page, add a key: label («default» by default), the key in the «Key» field and whether active.
2. Save: the key is kept encrypted and the page and the list only show «…» and its last four characters.
3. To change it, type the new one in «Key» and save: the date of the change and who made it stay. Leaving «Key» empty saves the rest without touching the key.
4. To remove it, tick «Delete» on its row and save.
Entra: label, key, active.
Sale: the encrypted key with its end in sight (`assistant.credential.saved`, with whether the key changed; on removal, `assistant.credential.deleted`). Neither the page, the list, the notices nor the log ever carry the key.
Si falla: a new key row without a key is refused with «Type the provider's key.»; a repeated label in the same provider is refused; without erplora.com's encryption key, «The key of the credentials is not configured: no provider key can be kept.» and nothing is saved; a key that can no longer be read shows as «Unreadable: type the key again» and saving the page without typing another does not touch it; whoever may only look does not see the «Key» field; without permission, the admin does not let in.
Implicados: none

## For whoever maintains it

- Anatomy, data and operations: `assistant/README.md`.
- The key is encrypted with Fernet and `FERNET_KEY` (`assistant/crypto.py`, `assistant/fields.py`); during a rotation
  `FERNET_KEY_PREVIOUS` still reads it. A key neither opens reads as empty and is logged as
  `assistant.crypto.undecryptable`, without the token.
- Writes through `assistant.credential.save|delete` (`services.py`), with the Django model permission that backs
  them (`add|change|delete_aiprovidercredential`); the admin calls them as the member of the staff who clicks.
- Traps of the old product covered: saas#528 (key in the clear in the database: `test_fields.py`), saas#2489 (app
  name untranslated in the admin: `test_apps.py`).

## What it does NOT do, on purpose

- It never shows a stored key, not even to a superuser: it is typed again.
- It has no screen in erplora.com's panel nor in the Hub.
