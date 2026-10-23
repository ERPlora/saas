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
once, never shown; empty keeps the one there was), whether active, when it changed and by whom; and its models, with their input and output price, their context and whether they are available. On top,
«Choose models from the provider».

### Admin: Choose models from the provider
The list of conversation models the provider's API gives, with a «Keep» checkbox (ticked on those it already has),
their name and context, and the «Save the choice» and «Back to the provider» buttons.

### Admin: AI models
Every model of every provider, with its price, its context and whether it is available, to correct them.

## States of each screen

| State | What the person sees |
|---|---|
| Loading | The normal loading of an admin page. |
| Empty | «0 AI providers» and the empty list; a provider without a key says «No key». |
| Error | In «Choose models from the provider», the reason in red: «This provider has no active key: add one on its page and try again.», «The provider did not give its models: …» or «The provider listed no chat models.»; on the pages, the error in red next to the field: «Use an https address: the provider's key travels to it.», «Type the provider's key.», «The key of the credentials is not configured: no provider key can be kept.». |
| No permission | Without the gateway's permissions, the admin answers there is no permission; whoever may only look sees the pages without the «Key» field. |

## Flows

| ID | Flow | Estado |
|---|---|---|
| ASSISTANT-F01 | Add an AI provider | hecho |
| ASSISTANT-F02 | Keep a provider's key without it being seen | hecho |
| ASSISTANT-F03 | Talk to each provider in its own API | hecho |
| ASSISTANT-F04 | Choose a provider's models | hecho |

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

### ASSISTANT-F03 Talk to each provider in its own API
<!-- origen: fi:saas/support/auth-services#service-providers-base-provider-toolspec-turnrequest-providerevent, fi:saas/support/auth-services#service-providers-factory-get_provider, fi:saas/support/auth-services#service-providers-anthropic_provider-anthropicprovider, fi:saas/support/auth-services#service-providers-openai_provider-openaiprovider, fi:saas/support/auth-services#service-providers-gemini_provider-geminiprovider, fi:saas/support/auth-services#service-providers-deepseek_provider-deepseekprovider -->
Estado: hecho
Actor: system
Pantalla: none
Pasos:
1. When a model has to be called (an assistant turn, an admin trial or a provider's list of models), erplora.com prepares the call in the shape the provider's API asks: OpenAI (and those compatible with it), Anthropic, Google Gemini or DeepSeek, with the provider's key and address.
2. It sends the conversation with its instructions, its images, the tools offered (only one per answer) and the output maximum, and receives the answer live, piece by piece.
3. It translates what each provider answers into the same for all: the text as it arrives, each tool the model asks for with its complete data, the input and output consumption and how it ended (normally, because it asked for a tool, for length or by the content filter).
4. For the list of models, it asks the provider for its conversation models, page by page, and leaves out those that do not converse (voice, images, text fingerprints).
Entra: the provider's API, address and key; the model, the conversation, the instructions and the tools.
Sale: the text, the tools asked for, the consumption and the end of the turn, the same whatever the provider; or the list of conversation models.
Si falla: if the provider refuses the key or the request, the turn ends with its reason and is marked as a failure repeating does not fix; if it does not answer, takes too long, is overloaded or limits the pace, it ends with a failure another attempt can fix (to move to the fallback model); the reason never carries the key. A provider without a key or with an unknown API is not called.
Implicados: ASSISTANT-F04, ASSISTANT-F06, ASSISTANT-F07

### ASSISTANT-F04 Choose a provider's models
<!-- origen: fi:saas/support/auth-services#modelo-aimodel, fi:saas/django-admin#admin-aimodel -->
Estado: hecho
Actor: ERPlora's staff
Pantalla: Admin: AI providers, Admin: Choose models from the provider, Admin: AI models
Pasos:
1. On the provider's page, click «Choose models from the provider»: erplora.com asks the provider's API, with its key, which conversation models it has.
2. Tick the ones that stay (those it has come ticked) and click «Save the choice».
3. Back on the page with the summary, for example «Local: 1 new, 0 kept, 1 removed, 0 in use by the policy.»: the ticked ones are available and the rest are removed, except those the answering model uses, which stay.
4. On the page or in «AI models», type each model's input and output price (dollars per million tokens), correct its name or context, or turn it off.
Entra: the provider with an active key; the choice of models; the prices.
Sale: the provider's models, exactly the chosen ones plus those in use (`assistant.model.selected`, with how many were created, kept, removed and protected).
Si falla: without an active readable key, «This provider has no active key: add one on its page and try again.» and nothing is asked of the provider; if the provider refuses the key or does not answer, «The provider did not give its models:» with its reason; if it has no conversation models, «The provider listed no chat models.»; without permission to see providers and to add and remove models, the admin does not let in; a model in use by the answering model cannot be deleted.
Implicados: ASSISTANT-F03, ASSISTANT-F05

## For whoever maintains it

- Anatomy, data and operations: `assistant/README.md`.
- The key is encrypted with Fernet and `FERNET_KEY` (`assistant/crypto.py`, `assistant/fields.py`); during a rotation
  `FERNET_KEY_PREVIOUS` still reads it. A key neither opens reads as empty and is logged as
  `assistant.crypto.undecryptable`, without the token.
- Writes through `assistant.credential.save|delete` (`services.py`), with the Django model permission that backs
  them (`add|change|delete_aiprovidercredential`); the admin calls them as the member of the staff who clicks.
- «Choose models from the provider» is an asynchronous admin view (`AIProviderAdmin.models_view`): the call to the
  provider does not hold the thread the other requests use; it reads the connection with
  `assistant.provider.connection` (`view_aiprovider`) and saves with `assistant.model.select` (`add_aimodel` and
  `delete_aimodel`).
- Clients (`assistant/providers/`): `httpx` against each API (no SDK nor LiteLLM), no cache, one per call; all end
  with a single `finish` and a failure is an `error` with `retriable`, never an exception. Tested against
  `assistant/tests/fake_provider.py` (an HTTP server on `127.0.0.1` speaking each provider's format).
- Traps of the old product covered: saas#528 (key in the clear in the database: `test_fields.py`), saas#2489 (app
  name untranslated in the admin: `test_apps.py`).

## What it does NOT do, on purpose

- It never shows a stored key, not even to a superuser: it is typed again.
- It has no screen in erplora.com's panel nor in the Hub.
