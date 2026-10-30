<!-- generated from WORKBOOK.md sha256:46d58bc86f379928fbafbd1834d90acf828cefc9d24d5ce7c9bd3a049996797f -->

## What it is for and who uses it

The Hub never talks to the provider of an AI model: it talks to erplora.com, which keeps the provider's key, decides
which model answers and calls it. So the key never leaves erplora.com and the AI spend is controlled in one place.

- Each provider's key is kept encrypted; it is typed once and never shown again: only its last four characters, to
  recognise it.
- One model answers and, if its provider fails, a fallback one.
- Before a model answers it can be tried from the admin, with how long it takes, what it consumes and what it costs.
- Each message a person writes to the assistant spends one of the monthly allowance of their business's plan (a demo
  has 10 in its whole life); the rest (the tools, the attachments, the fingerprints, the voice) spends no messages,
  but is measured.
- erplora.com uses the conversation to call the model and forgets it: it keeps it nowhere.

Who uses it:

- **ERPlora's staff**, in erplora.com's admin, with the AI gateway's permissions. The support group does not have
  them: the keys are ERPlora's spend.
- The **Hub's assistant** of each business (and of each demo): it sends erplora.com each turn, its attachments, the
  texts of its index, the dictations and what is to be read aloud, and shows the person what is left of the allowance.
- **ERPlora's staff**, in "Assistant usage records", see what each business spends and what it costs.

## Adopted reference

- **AI gateways** (OpenRouter, Portkey, Cloudflare AI Gateway, Vercel AI Gateway, LiteLLM's router): a primary model
  and a fallback one if the provider fails; the providers' keys in the gateway, never in the client.
- **The providers' consoles** (OpenAI, Anthropic, Google AI Studio, DeepSeek): the key is shown once when created
  and then only its end; the list of models comes from the provider's own API
  (https://platform.openai.com/docs/models, https://docs.anthropic.com/en/docs/about-claude/models).
- **ERPlora's old product** (the SaaS's `apps/assistant`): providers with their key and models on one page, the
  policy of which model answers and the tester with cost and latency; the Hub's turn through the gateway, with the
  allowance per business, the attachments, the fingerprints and the voice.
- **Assistants with an allowance** (ChatGPT, Claude, Gemini, Microsoft 365 Copilot, Shopify Magic): a number of
  messages per period by plan, which comes back when the next one starts; when it is spent the person is told and a
  plan up is offered; a message that fails before answering is not charged. The tools that are not the business's
  are run by the server, never by the device; the voice is dictation to text and reading
  aloud by the same provider (https://platform.openai.com/docs/guides/speech-to-text,
  https://platform.openai.com/docs/guides/text-to-speech).

## Before you start

- erplora.com needs its credentials encryption key in the environment; without it no provider key can be kept and
  the page says so on saving.
- Each provider needs an active readable key for its models to answer or be tried.
- The prices per million tokens of each model are typed by the staff: the providers' APIs do not give them. Without
  a price, the trial says the consumption and a cost of zero.
- The index's fingerprints, the dictation and the reading aloud are done by the services' provider (OpenAI): it must
  be added, enabled and with its key.
- The message allowance of each plan ("AI assistant messages a month") is typed in the admin of "Plans".

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

### Admin: Assistant usage records
One row per business and month (a demo, a single one in its whole life; an account, one per month with the panel's
assistant) with "Business, demo or account" (an account's, its email), "Month", "Messages", "Input tokens", "Output
tokens", "Embedding tokens", "Dictations", "Characters read aloud" and "Cost (USD)". On top, the search box (by the
business's name or address, by the demo's address or by the account's email) and the months; on the right, the "By
kind" filter ("Businesses", "Demos" or "Accounts") and the month's. Each row opens to see it whole, without being able
to change it.

## States of each screen

| State | What the person sees |
|---|---|
| Loading | The normal loading of an admin page; when trying a model, "Sending…" and the "Send" button off until it ends ("Done."). |
| Empty | "0 AI providers" and the empty list; in "Assistant usage records", "0 assistant usage records" until a business's first message; a provider without a key says "No key"; without models that can answer, "No model can answer yet: add a provider with its key and choose its models." |
| Error | In "Choose models from the provider", the reason in red: "This provider has no active key: add one on its page and try again.", "The provider did not give its models: …" or "The provider listed no chat models."; on the pages, the error in red next to the field: "Use an https address: the provider's key travels to it.", "Type the provider's key.", "The key of the credentials is not configured: no provider key can be kept."; when trying a model, in red: "The model did not answer: …", "Too many tries in a minute: wait a moment and try again." or "The try could not be sent: check the connection and try again.". |
| No permission | Without the gateway's permissions, the admin answers there is no permission; whoever may only look sees the pages without the "Key" field. "Assistant usage records" cannot be changed nor deleted, not even by a superuser. |

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
| ASSISTANT-F11 | Know who calls and for which business | done |
| ASSISTANT-F12 | Answer an assistant turn live | done |
| ASSISTANT-F13 | Answer the same turn at once | done |
| ASSISTANT-F14 | Use erplora.com's tools and the business's | partial |
| ASSISTANT-F15 | Refuse a turn with its reason | done |
| ASSISTANT-F16 | Stop a business that asks too much | done |
| ASSISTANT-F17 | Do not keep the conversation | done |
| ASSISTANT-F18 | Count the messages of each business's plan | done |
| ASSISTANT-F19 | Read the attachments of a question | done |
| ASSISTANT-F20 | Compute the fingerprint of some texts for the business's index | done |
| ASSISTANT-F21 | Transcribe a voice dictation | done |
| ASSISTANT-F22 | Read an answer aloud | done |
| ASSISTANT-F23 | Receive the report of an answer of the assistant | done |
| ASSISTANT-F24 | See what a business spent of the assistant | done |
| ASSISTANT-F25 | Answer the panel's assistant of an account | partial |
| ASSISTANT-F26 | Count an account's messages with the panel's assistant | done |

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
If it fails: if the provider refuses the key or the request, the turn ends with its reason and is marked as a failure repeating does not fix; if it does not answer, takes too long, is overloaded or limits the pace, it ends with a failure another attempt can fix (to move to the fallback model); the reason never carries the key. If erplora.com cannot load its trusted certificates (`SSL_CERT_FILE` names a file that is not there or holds none), the call never goes out: it ends with a failure repeating does not fix, and its reason and the server's log name the variable and the file. A provider without a key or with an unknown API is not called.
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

### ASSISTANT-F11 Know who calls and for which business
Status: done
Actor: the Hub's assistant of a business (or of a demo)
Screen: none
Steps:
1. Every time a business's assistant asks erplora.com for something (a turn, the allowance left, some fingerprints, a dictation, a reading aloud or a report), the request is signed with the secret the Hub and erplora.com share, with its time, and says which business it is for: its address, its identifier or, for a demo, the demo's address.
2. erplora.com checks the signature and that it is not older than five minutes before reading anything else.
3. It looks for the business: it must exist and be working (active, or with a payment pending in its grace days); a demo is recognised by its address.
4. With the business recognised, the request goes on: the rate limit, the allowance and what it asked for apply to that business and to no other.
In: the signature and its time, the business (or the demo) and what it asks for.
Out: the business or the demo the answer is for; no business sees nor spends another's allowance.
If it fails: without a signature, with a bad one, a stale one or one of another secret, it is refused as unauthorised; a business that does not exist or was already deleted, as unknown; one being prepared, suspended or being deleted, as inactive; a request that is not what each door expects is refused saying which fields fail; anything other than a submission is refused; a body over its door's size is refused without keeping it. None of that spends messages nor the rate limit.
Involved: ASSISTANT-F16, ASSISTANT-F18

### ASSISTANT-F12 Answer an assistant turn live
Status: done
Actor: the Hub's assistant of a business
Screen: none
Steps:
1. The person writes to the Hub's assistant; the Hub sends erplora.com the whole conversation (it is its own: it lives in the person's browser), its instructions and the tools the business offers.
2. erplora.com prepares the conversation: its instructions are the only system ones, the last 100 messages stay, the answer of a tool nobody asked for goes and the attachments become what the model can read.
3. It takes a message from the business's allowance and sends the turn to the model that answers (or to its fallback, if its provider fails before answering anything).
4. It sends the answer back live, piece by piece, and each tool of the business the model asks for; at the end, the whole answer with its consumption, what the business has left of its allowance and the close.
5. If the model asked for tools of the business, the turn ends there with a continuation pass: the Hub runs them and sends the conversation back with their results and that pass, and that return spends no other message.
In: the business, the conversation, the instructions, the business's tools and, when answering some tools, its continuation pass.
Out: the text as it arrives, the tools the business has to run, the turn's consumption and the allowance left (`assistant.message.claimed`; what it spent, `assistant.usage.recorded`).
If it fails: what is known before calling the model is a refusal and spends no message (see ASSISTANT-F15); if the provider fails after starting, the turn ends with a failure notice that says whether it is worth repeating; if the turn did not answer anything, its message goes back to the allowance, also if the Hub cuts the connection halfway. A continuation pass already used, expired (15 minutes), of another business or of other tools is not valid: that return spends a message.
Involved: ASSISTANT-F06, ASSISTANT-F13, ASSISTANT-F14, ASSISTANT-F15, ASSISTANT-F17, ASSISTANT-F18, ASSISTANT-F19

### ASSISTANT-F13 Answer the same turn at once
Status: done
Actor: the Hub's assistant of a business
Screen: none
Steps:
1. When the Hub does not need to see the answer as it arrives (a task of the Hub itself, a message that is not painted), it sends the same turn as in ASSISTANT-F12 to the door that answers at once. That is how the «Ask the assistant» step of one of the business's automations arrives, with nobody in front: one more turn, with nothing that tells it from the chat.
2. erplora.com does the same as live: it prepares the conversation, takes the message from the allowance, calls the model (or its fallback) and runs its own tools.
3. It sends back at once the whole answer, the tools the business has to run with their continuation pass, the consumption and the allowance left.
In: the same as the live turn.
Out: the whole answer with its consumption, its continuation pass and the allowance left (`assistant.message.claimed`; what it spent, `assistant.usage.recorded`).
If it fails: the refusals before the model, the same as live; if the provider fails, a gateway error with its reason, whether it is worth repeating and the allowance left, and the message goes back to the allowance if nothing was answered. An automation's step spends the same as the chat: its first turn, one message; the turns that answer all its tools (also those that were not made) with their continuation pass, none; if they answer after the pass's 15 minutes (a change that waited for a person's yes), one.
Involved: ASSISTANT-F12, ASSISTANT-F15, ASSISTANT-F18 and, in the Hub, FLOW-F39

### ASSISTANT-F14 Use erplora.com's tools and the business's
Status: partial — the old product's web search and exchange rate between currencies come with the ERP stage; today erplora.com gives the date and the time
Actor: the Hub's assistant of a business
Screen: none
Steps:
1. In each turn, the model can use the business's tools (those the Hub sends: find a customer, create an appointment…) and erplora.com's: today's date, time and weekday.
2. If the model asks for a tool of erplora.com, erplora.com runs it and gives it the result without the Hub seeing anything.
3. If it asks for one of the business, the turn passes it to the Hub to run it (see ASSISTANT-F12).
4. The model is asked again at most five times in a turn; in the last one erplora.com's tools are no longer offered and it has to answer.
In: the business's tools and the model's questions.
Out: the result of each tool of erplora.com for the model; its consumption adds up to the turn's and spends no other message.
If it fails: a tool of erplora.com that fails gives the model the reason to answer with, never a failed turn; a tool of the business named as one of erplora.com's is run by erplora.com; the web search and the exchange rate are not offered, even if erplora.com's environment has a search engine's key.
Involved: ASSISTANT-F12, ASSISTANT-F13

### ASSISTANT-F15 Refuse a turn with its reason
Status: done
Actor: the Hub's assistant of a business
Screen: none
Steps:
1. Before calling the model, erplora.com checks the turn: its form, its size, that there is a model that can answer and that the business has allowance left.
2. If something does not fit, it refuses the turn without calling the model and without spending any message, with a code the Hub translates to its text and whether it is worth repeating.
3. If the allowance is spent, the refusal says how many messages were used out of how many, when they come back and that a plan up is needed for more.
In: the turn.
Out: a refusal with its code: allowance spent, no model to answer, provider not configured, conversation or attachment too big, or a form that is not the expected one.
If it fails: an unexpected failure is sent back as an internal error worth repeating, without details; neither the provider's key nor its words ever go out.
Involved: ASSISTANT-F12, ASSISTANT-F13, ASSISTANT-F18, ASSISTANT-F19

### ASSISTANT-F16 Stop a business that asks too much
Status: done
Actor: the Hub's assistant of a business
Screen: none
Steps:
1. Each door of the assistant has a maximum of requests per hour for each business (and for each demo): 600 turns and allowance queries, 600 batches of fingerprints, 120 dictations, 120 readings aloud and 60 reports.
2. Only a request with a good signature and of a working business counts: a fake request spends nobody's limit.
3. Over the maximum, the request is refused and it says how many seconds are left before asking again.
In: each business's requests.
Out: the request served or stopped; one business's limit does not stop another.
If it fails: a stopped business waits what it is told and tries again; the maximums change in erplora.com's environment without touching the code.
Involved: ASSISTANT-F11

### ASSISTANT-F17 Do not keep the conversation
Status: done
Actor: system
Screen: none
Steps:
1. Each turn's conversation arrives with the request, is used to call the model and is forgotten at the end.
2. erplora.com only notes what was spent: the business's messages, tokens and cost in the month.
3. If the provider fails, erplora.com's log only notes the status of the provider's answer, never its words (they may quote the conversation).
In: the turn's conversation.
Out: the answer for the Hub and what was spent; neither the database, nor the logs, nor the audit log keep a word of the conversation, its attachments, its dictations nor what is read aloud.
If it fails: if something of the conversation reached a log, a test catches it before it ships.
Involved: ASSISTANT-F12, ASSISTANT-F19, ASSISTANT-F21, ASSISTANT-F22, ASSISTANT-F23

### ASSISTANT-F18 Count the messages of each business's plan
Status: done
Actor: the Hub's assistant of a business
Screen: none
Steps:
1. A business's allowance is that of the plan it has now ("AI assistant messages a month"); 0 is none, never unlimited. A demo has 10 messages in its whole life.
2. Each message the person writes spends one when the turn starts, before calling the model; if two turns arrive at once with a single message free, only one passes.
3. If the turn does not answer anything (the provider fails, the Hub cuts), the message goes back to the month it was taken from.
4. Each turn adds its tokens and its cost to the business's month; the tools, the fingerprints, the dictations and the voice are measured but spend no messages.
5. The Hub asks how much is left (how many were used, out of how many and when they come back) and shows it; the close of each turn brings the same figures. The allowance comes back on day 1 of each month at 00:00 UTC; a demo's does not come back.
In: the business (or the demo) and its plan.
Out: the message taken or given back and what was spent in the month (`assistant.message.claimed`, `assistant.message.released`, `assistant.usage.recorded`).
If it fails: with no free messages, the turn is refused with the allowance spent and the offer of a plan up (see ASSISTANT-F15); there are no packs of loose messages: more messages is a plan up.
Involved: ASSISTANT-F12, ASSISTANT-F15, ASSISTANT-F24, HUBS-F05

### ASSISTANT-F19 Read the attachments of a question
Status: done
Actor: the Hub's assistant of a business
Screen: none
Steps:
1. The person attaches images or documents to their question; the Hub sends them inside the turn.
2. An image (PNG, JPEG, WebP or GIF) goes to the model as it is if it sees images; if it does not, the model gets a note in its place.
3. A document (PDF, Word, Excel, text, CSV, Markdown or a .json file) becomes its text (a spreadsheet, sheet by sheet) and the model reads it with its name.
4. Everything happens in memory: nothing is downloaded from any address nor written to disk.
In: the question's images and documents.
Out: what the model can read of each attachment, or a note if it cannot be read.
If it fails: an attachment of more than about 9 MB or more than 20 attachments in a conversation refuse the turn as too big, cutting nothing and spending no message; a broken document, a protected one, one of a type that is not read or that would grow too much when opened is a note for the model, never a failed turn; an image or a document given by an address is not downloaded; the file's name reaches no log.
Involved: ASSISTANT-F12, ASSISTANT-F15, ASSISTANT-F17

### ASSISTANT-F20 Compute the fingerprint of some texts for the business's index
Status: done
Actor: the Hub's assistant of a business
Screen: none
Steps:
1. So the assistant finds what it looks for (which app does what, which screen to open), the Hub keeps an index with the fingerprint of each text and sends erplora.com the texts it needs the fingerprint of, 1 to 256 at a time.
2. erplora.com asks the services' provider for the fingerprints, always with the same fingerprint model, and gives them back in the order of the texts.
3. The tokens and their cost add up to the business's month.
In: the business and the texts.
Out: one fingerprint per text, in their order, with the name of the model that computed them (`assistant.usage.recorded`).
If it fails: without the services' provider configured (or without its key), it is refused saying the provider is not configured; if the provider refuses the request or does not answer, a gateway error that says whether it is worth repeating; an empty text or more than 256 are refused; it spends no messages of the allowance.
Involved: ASSISTANT-F11, ASSISTANT-F16, ASSISTANT-F24

### ASSISTANT-F21 Transcribe a voice dictation
Status: done
Actor: the Hub's assistant of a business
Screen: none
Steps:
1. The person dictates their question in the Hub; the Hub sends erplora.com the audio, its type (WebM, Ogg, WAV, MP4, MP3 or FLAC) and, if it knows it, the language.
2. erplora.com passes it to the services' provider from memory, without writing it to disk, and gives back the text and the language.
3. The dictation is counted in the business's month; it spends no messages (the message is spent by the turn sent with that text).
In: the business, the audio, its type and its language.
Out: the dictated text and its language (`assistant.usage.recorded`).
If it fails: an audio over 2 MB is refused as too big; empty, badly encoded or of another type, it is refused saying what fails; without the services' provider configured, that it is not configured; if the provider fails, a gateway error that says whether it is worth repeating. Neither the audio nor the text stay kept nor in a log.
Involved: ASSISTANT-F11, ASSISTANT-F16, ASSISTANT-F17, ASSISTANT-F24

### ASSISTANT-F22 Read an answer aloud
Status: done
Actor: the Hub's assistant of a business
Screen: none
Steps:
1. The person asks the assistant to read its answer; the Hub sends erplora.com the text and, if it wants, the voice (alloy, echo, fable, onyx, nova or shimmer).
2. erplora.com asks the services' provider for the audio (at most the first 4,096 characters) and gives it back in MP3.
3. The characters read are counted in the business's month; it spends no messages.
In: the business, the text and the voice.
Out: the audio of the answer (`assistant.usage.recorded`).
If it fails: an empty text is refused; a voice that does not exist is changed to the default one; without the services' provider configured, that it is not configured; if the provider fails, a gateway error that says whether it is worth repeating. The text stays neither kept nor in a log.
Involved: ASSISTANT-F11, ASSISTANT-F16, ASSISTANT-F17, ASSISTANT-F24

### ASSISTANT-F23 Receive the report of an answer of the assistant
Status: done
Actor: the Hub's assistant of a business
Screen: none
Steps:
1. The person marks an answer of the assistant as incorrect, harmful, not doing what was asked or something else, and adds, if they want, a comment.
2. The Hub sends erplora.com the report with the question and the answer.
3. erplora.com mails it to ERPlora's support mailbox with the business, the reason, the comment, the question and the answer (each text, at most 4,000 characters), and keeps nothing.
4. If the same answer of the same business is reported again within 24 hours (a double tap, a retry), no other mail is sent.
In: the business, the reported answer, the reason, the comment and the question.
Out: the mail in the support mailbox, or the notice that it had already been sent (`assistant.report.sent`).
If it fails: if the mail cannot leave, it says it could not be sent and to try again in a moment, and it can be sent again; a reason that is not one of the four is refused; a business that stops working (deleted or suspended) while its report arrives sends nothing and gets the same answer as in any other call (ASSISTANT-F11).
Involved: ASSISTANT-F11, ASSISTANT-F16, ASSISTANT-F17

### ASSISTANT-F24 See what a business spent of the assistant
Status: done
Actor: ERPlora's staff
Screen: Admin: Assistant usage records
Steps:
1. In erplora.com's admin, open "Assistant usage records".
2. Search the business by its name or its address (the demo by its address, the account by its email), or filter "By kind" ("Businesses", "Demos" or "Accounts") and by month.
3. Read its row of the month: "Messages" of the allowance, "Input tokens", "Output tokens", "Embedding tokens", "Dictations", "Characters read aloud" and "Cost (USD)" (with the prices of the model that answered each turn).
4. Open the row to see it whole, with when it was created and when it changed.
In: the business, the demo or the account and the month.
Out: what the business (or the account) spent in the month, without being able to change it.
If it fails: nobody can add, change nor delete a row, not even a superuser (deleting the month's row gave the business its whole allowance back); a team member without the permission to see it does not enter.
Involved: ASSISTANT-F18, ASSISTANT-F20, ASSISTANT-F21, ASSISTANT-F22, ASSISTANT-F26

### ASSISTANT-F25 Answer the panel's assistant of an account
Status: partial — erplora.com already answers each turn of the account; the chat that opens it from the panel's bar comes with its screen
Actor: the person with an account at erplora.com
Screen: none
Steps:
1. The person, signed in to erplora.com's panel, writes to the assistant ("Which businesses do I have?", "How much do I pay a month?", "Create a business for my hair salon").
2. erplora.com offers the model the panel's tools this account may use (its businesses and their people, the plans, its invoices and subscriptions, its account, the catalogue of apps), first those of what was asked, and always the list of its businesses.
3. A read the model asks for runs on its own, as the person themselves: it never sees a business that is not theirs.
4. A change the model asks for stops at a card that says what it will do, where (the panel's screen: "Businesses", "Billing", "Account" or "Store") and with which data, naming the business by its name; it is only done if the person says yes. Creating, deleting or changing the address of a business, offering it to someone else or cancelling its plan also ask to type "CONFIRM"; changing plan is not done from the chat but in the Store, which shows first what will be charged.
5. With what the tools returned, the model answers live, piece by piece, in the person's language, and links the panel's screen where what it cannot do is done; for what happens inside a business (sales, products, the people at the till) it says to open the business and ask its assistant.
In: the conversation (it lives in the person's browser), the tools the model asked for and the person's answer to its card.
Out: what was done and its result, the card of the change that waits, the text as it arrives, the allowance left and the close; what each tool does leaves its own trace (`hubs.business.created`…), never the conversation.
If it fails: without a session, it does not answer (one must sign in); with the month's allowance spent, the first notice is the allowance spent, with how many were used and when they come back (see ASSISTANT-F26); with too many turns in a row, it says to wait a moment; without a model that answers, that the assistant cannot answer now. A tool the account does not have, or that is not for the chat (downloading a file, creating an API key, opening the payment, entering a business), never runs. Without the word typed or with a "no", the change is not made and the model says so. Where nothing is sold (the account opened from the installed app), neither the Store nor its plan changes are offered. Past six rounds of tools in a single question, it stops.
Involved: ASSISTANT-F12, ASSISTANT-F14, ASSISTANT-F15, ASSISTANT-F16, ASSISTANT-F17, ASSISTANT-F23, ASSISTANT-F26, HUBS-F01, HUBS-F09, BILLING-F13

### ASSISTANT-F26 Count an account's messages with the panel's assistant
Status: done
Actor: the person with an account at erplora.com
Screen: none
Steps:
1. Each account has 30 messages a month with the panel's assistant, whatever businesses it has and whatever their plans; each business's allowance is apart, its plan's in its Hub (see ASSISTANT-F18).
2. Each message the person writes spends one when the turn starts, before calling the model; the return with the results of the tools the model asked for spends no other.
3. If the turn does not answer anything (the provider fails, the person cuts), the message goes back to the month it was taken from.
4. The panel asks how much is left (how many were used, out of how many and when they come back); the close of each turn brings the same figures. The allowance comes back on day 1 of each month at 00:00 UTC.
In: the session's account.
Out: the message taken or given back and what was spent in the account's month (`assistant.message.claimed`, `assistant.message.released`, `assistant.usage.recorded`, with the account).
If it fails: with no free messages, the turn is refused with the allowance spent and the date they come back; there is no plan to go up nor loose packs. An account never spends its businesses' messages, nor a business its account's; deleting the account deletes its rows.
Involved: ASSISTANT-F18, ASSISTANT-F24, ASSISTANT-F25
