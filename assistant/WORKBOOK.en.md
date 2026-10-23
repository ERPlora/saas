<!-- generated from WORKBOOK.md sha256:53749f42191ebcc53bd0f97f21f0fc4af268d43ccebf2d5515a14755b4f8d692 -->

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
List of the providers with their API, whether enabled and the state of their key: "…" and the last four characters,
"No key" or "Unreadable: type the key again". Each provider's page has its keys inside: label, the "Key" field (typed
once, never shown; empty keeps the one there was), whether active, when it changed and by whom; and its models, with their input and output price, their context and whether they are available. On top,
"Choose models from the provider".

### Admin: Choose models from the provider
The list of conversation models the provider's API gives, with a "Keep" checkbox (ticked on those it already has),
their name and context, and the "Save the choice" and "Back to the provider" buttons.

### Admin: AI models
Every model of every provider, with its price, its context and whether it is available, to correct them.

### Admin: Model that answers
One page (its list opens it): "Model that answers" and "Fallback model", each with the models that can answer
(available and of an enabled provider), who made the last change and "Save". Whoever may only look sees it without
being able to change it. On top, "Try a model" (only for whoever may change it).

### Admin: Try a model
"Model" (those that can answer), "Message", "Tools" (optional, a list as in the example) and "Send". Below, "Answer": the model
that answers, the text as it arrives, the tools it asks for and a table with "Input tokens", "Output tokens", "Time"
and "Cost" (in dollars).

## States of each screen

| State | What the person sees |
|---|---|
| Loading | The normal loading of an admin page; when trying a model, "Sending…" and the "Send" button off until it ends ("Done."). |
| Empty | "0 AI providers" and the empty list; a provider without a key says "No key"; without models that can answer, "No model can answer yet: add a provider with its key and choose its models." |
| Error | In "Choose models from the provider", the reason in red: "This provider has no active key: add one on its page and try again.", "The provider did not give its models: …" or "The provider listed no chat models."; on the pages, the error in red next to the field: "Use an https address: the provider's key travels to it.", "Type the provider's key.", "The key of the credentials is not configured: no provider key can be kept."; when trying a model, in red: "The model did not answer: …", "Too many tries in a minute: wait a moment and try again." or "The try could not be sent: check the connection and try again.". |
| No permission | Without the gateway's permissions, the admin answers there is no permission; whoever may only look sees the pages without the "Key" field. |

## Flows

| ID | Flow | Status |
|---|---|---|
| ASSISTANT-F01 | Add an AI provider | done |
| ASSISTANT-F02 | Keep a provider's key without it being seen | done |
| ASSISTANT-F03 | Talk to each provider in its own API | done |
| ASSISTANT-F04 | Choose a provider's models | done |
| ASSISTANT-F05 | Choose which model answers | done |
| ASSISTANT-F06 | Choose the provider and model of each turn | done |
| ASSISTANT-F07 | Try a model before it answers | done |
| ASSISTANT-F08 | See who changed the configuration of the AI | done |
| ASSISTANT-F09 | Load the providers' keys from the environment | done |
| ASSISTANT-F10 | Change the encryption key without losing any credential | done |

### ASSISTANT-F01 Add an AI provider
Status: done
Actor: ERPlora's staff
Screen: Admin: AI providers
Steps:
1. In "AI providers", click "Add AI provider".
2. Type its name and a short identifier (for example "openai"), choose the API it speaks (OpenAI, Anthropic, Google Gemini or DeepSeek; a provider compatible with OpenAI's is "OpenAI" with its address) and, if it is not the provider's own, its address.
3. Leave it enabled or off and save.
In: name, identifier, API, address, enabled, notes.
Out: the provider in the list, ready for its key and its models.
If it fails: an address that is not https is refused with "Use an https address: the provider's key travels to it." (only an address of the machine itself is accepted without https); a repeated identifier is refused; without permission, the admin does not let in.
Involved: none

### ASSISTANT-F02 Keep a provider's key without it being seen
Status: done
Actor: ERPlora's staff
Screen: Admin: AI providers
Steps:
1. On the provider's page, add a key: label ("default" by default), the key in the "Key" field and whether active.
2. Save: the key is kept encrypted and the page and the list only show "…" and its last four characters.
3. To change it, type the new one in "Key" and save: the date of the change and who made it stay. Leaving "Key" empty saves the rest without touching the key.
4. To remove it, tick "Delete" on its row and save.
In: label, key, active.
Out: the encrypted key with its end in sight (`assistant.credential.saved`, with whether the key changed; on removal, `assistant.credential.deleted`). Neither the page, the list, the notices nor the log ever carry the key.
If it fails: a new key row without a key is refused with "Type the provider's key."; a repeated label in the same provider is refused; without erplora.com's encryption key, "The key of the credentials is not configured: no provider key can be kept." and nothing is saved; a key that can no longer be read shows as "Unreadable: type the key again" and saving the page without typing another does not touch it; whoever may only look does not see the "Key" field; without permission, the admin does not let in.
Involved: none

### ASSISTANT-F03 Talk to each provider in its own API
Status: done
Actor: system
Screen: none
Steps:
1. When a model has to be called (an assistant turn, an admin trial or a provider's list of models), erplora.com prepares the call in the shape the provider's API asks: OpenAI (and those compatible with it), Anthropic, Google Gemini or DeepSeek, with the provider's key and address.
2. It sends the conversation with its instructions, its images, the tools offered (only one per answer) and the output maximum, and receives the answer live, piece by piece.
3. It translates what each provider answers into the same for all: the text as it arrives, each tool the model asks for with its complete data, the input and output consumption and how it ended (normally, because it asked for a tool, for length or by the content filter).
4. For the list of models, it asks the provider for its conversation models, page by page, and leaves out those that do not converse (voice, images, text fingerprints).
In: the provider's API, address and key; the model, the conversation, the instructions and the tools.
Out: the text, the tools asked for, the consumption and the end of the turn, the same whatever the provider; or the list of conversation models.
If it fails: if the provider refuses the key or the request, the turn ends with its reason and is marked as a failure repeating does not fix; if it does not answer, takes too long, is overloaded or limits the pace, it ends with a failure another attempt can fix (to move to the fallback model); the reason never carries the key. A provider without a key or with an unknown API is not called.
Involved: ASSISTANT-F04, ASSISTANT-F06, ASSISTANT-F07

### ASSISTANT-F04 Choose a provider's models
Status: done
Actor: ERPlora's staff
Screen: Admin: AI providers, Admin: Choose models from the provider, Admin: AI models
Steps:
1. On the provider's page, click "Choose models from the provider": erplora.com asks the provider's API, with its key, which conversation models it has.
2. Tick the ones that stay (those it has come ticked) and click "Save the choice".
3. Back on the page with the summary, for example "Local: 1 new, 0 kept, 1 removed, 0 in use by the policy.": the ticked ones are available and the rest are removed, except those the answering model uses, which stay.
4. On the page or in "AI models", type each model's input and output price (dollars per million tokens), correct its name or context, or turn it off.
In: the provider with an active key; the choice of models; the prices.
Out: the provider's models, exactly the chosen ones plus those in use (`assistant.model.selected`, with how many were created, kept, removed and protected).
If it fails: without an active readable key, "This provider has no active key: add one on its page and try again." and nothing is asked of the provider; if the provider refuses the key or does not answer, "The provider did not give its models:" with its reason; if it has no conversation models, "The provider listed no chat models."; without permission to see providers and to add and remove models, the admin does not let in; a model in use by the answering model cannot be deleted.
Involved: ASSISTANT-F03, ASSISTANT-F05

### ASSISTANT-F05 Choose which model answers
Status: done
Actor: ERPlora's staff
Screen: Admin: Model that answers
Steps:
1. Open "Model that answers" (from the assistant's front page or its list, which leads straight to the page).
2. Choose the "Model that answers" and, if wanted, a different "Fallback model", among the available models of the enabled providers.
3. Click "Save": "The model that answers was saved."; the next assistant turn already uses this choice and who changed it stays.
In: the model that answers and the fallback one.
Out: the choice of the whole platform (`assistant.policy.updated`, with both models).
If it fails: a model that is off, of a provider that is off or that no longer exists is refused with "This model cannot answer: it is off, its provider is off or it does not exist."; the fallback equal to the first, with "The fallback model must be another model."; a fallback without a model that answers, with "Choose the model that answers before its fallback."; if the chosen model is turned off later, the page warns "The model that answers is off or its provider is: choose another one."; whoever may only look does not see "Save" and, if they try, nothing is saved; without permission, the admin does not let in. Nobody adds nor deletes this choice, and a model in use cannot be deleted.
Involved: ASSISTANT-F04, ASSISTANT-F06

### ASSISTANT-F06 Choose the provider and model of each turn
Status: done
Actor: system
Screen: none
Steps:
1. Every assistant turn reads again which model answers and which one is its fallback, with each provider's most recent active key that can be opened; so a changed key or another choice already counts on the next turn, without restarting anything.
2. A model that is off, one of a provider that is off and one of a provider without a usable key are skipped; the turn starts with the first one left and says which model answers.
3. If its provider fails before answering anything (down, overloaded, limiting the rate or refusing the key), the turn passes to the fallback model and warns of the change with its reason; if it had already started answering, the turn ends with the failure, because the person already saw the start of the answer.
4. When a model is tried from the admin, the turn goes to that model alone, without fallback.
In: the model that answers and its fallback (or the model being tried) and their providers' keys.
Out: the model that answers the turn and, if its provider fails before answering, the notice of the switch to the fallback model.
If it fails: without a model that answers, "No model answers yet: choose one on the page “Model that answers”."; if none of the chosen ones can be used, "No model can answer: the providers of the chosen models have no active key."; a model being tried that is off, or of a provider that is off, "This model is off or its provider is: turn them on to use it."; if all of them fail, the turn ends with the reason of the last one; the staff only try a model with permission to change the model that answers.
Involved: ASSISTANT-F03, ASSISTANT-F05, ASSISTANT-F07

### ASSISTANT-F07 Try a model before it answers
Status: done
Actor: ERPlora's staff
Screen: Admin: Try a model
Steps:
1. On "Model that answers", click "Try a model".
2. Choose the "Model", write the "Message" and, to see how it asks for tools, write in "Tools" a list of tools with their name, as in the example.
3. Click "Send": "Sending…" shows, then the model that answers and its answer as it arrives, with the tools it asks for.
4. At the end, "Done." and the table with "Input tokens", "Output tokens", "Time" and "Cost" (with the model's prices).
In: the model, the message and the tools.
Out: the model's answer with its usage, its time and its cost; the try stays in the audit trail with who made it, how long the message was and how many tools it had, never the message (`assistant.model.tried`). No business, quota nor conversation is touched.
If it fails: without a model of the list, "Choose the model to try from the list."; without a message, "Write the message to send."; badly written tools, "The tools are not well written: write a list of tools as in the example, each with its name."; a model that is off or of a provider that is off, "This model is off or its provider is: turn them on to use it."; a provider without a usable key, "No model can answer: the providers of the chosen models have no active key."; if the provider fails, "The model did not answer: …" with its reason, never the key; more than 10 tries in a minute, "Too many tries in a minute: wait a moment and try again."; without network, "The try could not be sent: check the connection and try again.". Only whoever may change the model that answers tries one (each try spends ERPlora's key); without that permission, the admin does not let in.
Involved: ASSISTANT-F05, ASSISTANT-F06

### ASSISTANT-F08 See who changed the configuration of the AI
Status: done
Actor: ERPlora superuser (or a team member allowed to see the log)
Screen: erplora.com's admin › "Audit log"
Steps:
1. Every addition, change or removal of an AI provider, of a provider's key (also turning it off or replacing it with another), of a model (its prices, whether it is available) and of the model that answers is written down: what changed, from which value to which, when, who did it and from which address.
2. Every try of a model is written down as an access to that model, with who made it, how long the message was and how many tools it had.
3. Open "Audit log" in the admin, filter by resource type or search, and open an entry to see its changes.
In: the changes to the configuration of the AI, made from the admin or by erplora.com's commands.
Out: one entry per change in the same audit log as the accounts, the charges and the fiscal documentation.
If it fails: a provider's key is never written down, neither in clear nor encrypted: its change shows in its last four characters and in when it changed; nor is the message of a try. Nobody can create, change or delete an entry by hand, and a team member without the permission cannot open the log.
Involved: ACCOUNTS-F36, ASSISTANT-F02, ASSISTANT-F07

### ASSISTANT-F09 Load the providers' keys from the environment
Status: done
Actor: ERPlora's staff, on erplora.com's command line
Screen: none
Steps:
1. With the keys of OpenAI, Anthropic, Google Gemini and DeepSeek in erplora.com's environment, run the loading of the environment's keys.
2. Each key is kept encrypted in its provider with the default label (or another one chosen); if the provider is missing, it is added with its name and its API.
3. If the provider already had a key with that label, it stays as it is, unless replacing it is asked for: then it changes, it is turned on and when it changed stays.
4. The providers to load can be chosen, and the loading can be rehearsed without keeping anything.
In: the keys of the environment, the chosen providers, the label and whether the ones already there are replaced.
Out: the keys encrypted in their providers (`assistant.credential.saved`) and, for each one, whether it was created, changed, kept or skipped, with its last four characters.
If it fails: an empty variable is skipped; an unknown provider stops the loading before keeping anything; without the key of the credentials none is kept. It never writes a whole key on screen, and the change stays in the audit log.
Involved: ASSISTANT-F01, ASSISTANT-F02, ASSISTANT-F08

### ASSISTANT-F10 Change the encryption key without losing any credential
Status: done
Actor: ERPlora's staff, on erplora.com's command line
Screen: none
Steps:
1. Put the new encryption key as the current one and leave the old one as the previous one (which only reads), and deploy erplora.com.
2. Rehearse the change: it says how many values would be encrypted again in each place, writing nothing.
3. Run the change: every value kept with the key of the credentials (the AI providers' keys and WhatsApp's tokens and PINs) is encrypted again with the new key; those already are stay as they are.
4. If it ends without errors, remove the previous key: every credential still reads.
In: the new key and the old one.
Out: every credential encrypted with the new key (`assistant.encryption.rotated`, with how many changed, how many already were and how many could not be read).
If it fails: a value neither key opens is never written: its row is named and the change ends with an error, so the previous key is not removed while something needs it (bring back the key that encrypted it or type the value again, and repeat). Without the encryption key nothing changes. It never shows a value nor its encryption, and no date of the rows moves.
Involved: ASSISTANT-F02, ASSISTANT-F09
