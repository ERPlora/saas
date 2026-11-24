"""The conversation the model reads: the request in progress and the one before whole, the older ones lighter and only
as many as fit.

The Hub sends the whole conversation with every call (the person's browser keeps it). A request is a message of the
person and everything that answered it: the model's calls of tools, their results, the answers to its cards and its
reply. The request in progress goes whole, and so does the one before: the person often answers the model's question
or speaks of what it just did («remove those two»), and the model reads what that request's tools gave. What an older
request's tools gave was read for it, and its reply says what mattered: each such result reaches the model as a short
note, as the providers' own context editing clears old tool results, and the model calls the tool again if it needs
that data now. The older requests go, oldest first and whole, beyond ``BUDGET_TOKENS``.

What changes only changes when the person writes: within a request, its rounds leave the rest as it was, so the
provider's cache reads it again.
"""

from __future__ import annotations

import json
import math

#: What the model reads in place of a result of an older request.
CLEARED = "[Cleared: this result answered an earlier request. Call the tool again if you need its data now.]"
#: The requests that go whole, the one in progress included.
WHOLE = 2
#: The older requests the model reads, in tokens (estimated: ``tokens``).
BUDGET_TOKENS = 16_000
#: The estimate's characters of a token, as the usual approximate counters take them.
CHARS_PER_TOKEN = 4


def tokens(message: dict) -> int:
    """About how many tokens ``message`` is: its characters over ``CHARS_PER_TOKEN``, an attachment's data left out
    (it has its own limit, ``attachments``)."""
    from assistant import attachments

    [measured] = attachments.without_data([message])
    return math.ceil(len(json.dumps(measured, ensure_ascii=False, default=str)) / CHARS_PER_TOKEN)


def requests(messages: list[dict]) -> list[list[dict]]:
    """``messages`` split at each message of the person; what comes before the first one is a request of its own."""
    split: list[list[dict]] = []
    for message in messages:
        if message["role"] == "user" or not split:
            split.append([])
        split[-1].append(message)
    return split


def lighter(request: list[dict]) -> list[dict]:
    """An older request with each tool result in it as ``CLEARED``, unless the result is no longer than the note."""
    kept = []
    for message in request:
        note = {**message, "content": CLEARED}
        kept.append(note if message["role"] == "tool" and tokens(note) < tokens(message) else message)
    return kept


def window(messages: list[dict]) -> list[dict]:
    """The conversation the model reads: the newest older requests, lighter, that fit ``BUDGET_TOKENS``, then the
    ``WHOLE`` last ones as they are."""
    split = requests(messages)
    older, whole = split[:-WHOLE], split[-WHOLE:]
    kept: list[list[dict]] = []
    spent = 0
    for request in map(lighter, reversed(older)):
        spent += sum(tokens(message) for message in request)
        if spent > BUDGET_TOKENS:
            break
        kept.append(request)
    return [message for request in [*reversed(kept), *whole] for message in request]
