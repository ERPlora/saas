from config.settings.core import config

# «Try a model» of the admin per member of the staff: each try spends
# ERPlora's key with the provider (django-ratelimit, over the default cache).
ASSISTANT_TRY_RATELIMIT = config("ASSISTANT_TRY_RATELIMIT", default="10/m")
# The Hub's doors of the assistant (/internal/assistant/*, /internal/speech/*), per business or demo,
# counted after the signature and the business pass (django-ratelimit, over the default cache): the turn's doors
# (live, JSON and the allowance), the embeddings, the searches in the documentation, each voice door on its own and
# the reports of an answer.
ASSISTANT_TURN_RATELIMIT = config("ASSISTANT_TURN_RATELIMIT", default="600/h")
ASSISTANT_EMBED_RATELIMIT = config("ASSISTANT_EMBED_RATELIMIT", default="600/h")
ASSISTANT_DOCS_RATELIMIT = config("ASSISTANT_DOCS_RATELIMIT", default="600/h")
ASSISTANT_TRANSCRIBE_RATELIMIT = config("ASSISTANT_TRANSCRIBE_RATELIMIT", default="120/h")
ASSISTANT_SYNTHESIZE_RATELIMIT = config("ASSISTANT_SYNTHESIZE_RATELIMIT", default="120/h")
ASSISTANT_REPORT_RATELIMIT = config("ASSISTANT_REPORT_RATELIMIT", default="60/h")
# What a caller may ask of the providers of erplora.com's own tools: the search's free credit is shared
# by every business (about 4,000 searches a month) and the rates are a free public service. Every demo shares one.
ASSISTANT_WEB_SEARCH_RATELIMIT = config("ASSISTANT_WEB_SEARCH_RATELIMIT", default="20/d")
ASSISTANT_CURRENCY_RATE_RATELIMIT = config("ASSISTANT_CURRENCY_RATE_RATELIMIT", default="60/h")
# A demo's messages for its whole life (each browser gets a new demo).
ASSISTANT_DEMO_MESSAGES = config("ASSISTANT_DEMO_MESSAGES", default=10, cast=int)
# An account's messages a month with the assistant of erplora.com's own panel: fixed, whatever the
# plans of its businesses, each of which has its own allowance in its Hub.
ASSISTANT_ACCOUNT_MESSAGES = config("ASSISTANT_ACCOUNT_MESSAGES", default=30, cast=int)
# The provider (its identifier in the admin, of OpenAI's API) whose key computes the embeddings and the dictation.
ASSISTANT_SERVICE_PROVIDER = config("ASSISTANT_SERVICE_PROVIDER", default="openai")

# The AI gateway (assistant/): the providers' keys `import_ai_keys_from_env` keeps encrypted in the
# database; the staff may type them in the admin instead. Empty = nothing to load. The gateway reads
# the keys from the database, never from here.
OPENAI_API_KEY = config("OPENAI_API_KEY", default="")
ANTHROPIC_API_KEY = config("ANTHROPIC_API_KEY", default="")
GEMINI_API_KEY = config("GEMINI_API_KEY", default="")
DEEPSEEK_API_KEY = config("DEEPSEEK_API_KEY", default="")

# The providers of erplora.com's own tools (assistant/server_tools.py). The rates need no key. The search
# reads its key here, from the environment and not from the database, and without it is not offered: the assistant
# just does not search and the server starts as usual. Before filling the key in production, the privacy policy must
# name the provider (saas#277). Its addresses move only for the e2e's double.
BRAVE_SEARCH_API_KEY = config("BRAVE_SEARCH_API_KEY", default="")
ASSISTANT_SEARCH_URL = config("ASSISTANT_SEARCH_URL", default="https://api.search.brave.com/res/v1/web/search")
ASSISTANT_RATES_URL = config("ASSISTANT_RATES_URL", default="https://api.frankfurter.dev/v1/latest")
