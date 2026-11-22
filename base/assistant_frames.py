"""The gateway's frames of one turn (``assistant.turn.frames``) as the panel reads them: what it shows as they come and
what the closing ``done`` keeps for the browser."""

from dataclasses import dataclass, field
from typing import Any

#: What the panel is told of the account's allowance: by each turn's ``usage`` and by the refusal of a spent month.
ALLOWANCE = ("used", "limit", "resets_at", "demo")


def assistant_message(text: str, calls: list[dict]) -> dict:
    """The model's message as the browser keeps it in the conversation: its text and the tools it asked for, if any."""
    message: dict[str, Any] = {"role": "assistant", "content": text}
    if calls:
        message["tool_calls"] = [
            {
                "id": call["call_id"],
                "type": "function",
                "function": {"name": call["name"], "arguments": call["arguments"]},
            }
            for call in calls
        ]
    return message


@dataclass
class GatewayAnswer:
    """The gateway's frames of one turn, read in order: what was said, the tools the model asked for, their
    ``continuation``, whether pages came from the web, and whether the turn ended (``"[DONE]"``) or failed."""

    text: list[str] = field(default_factory=list)
    calls: list[dict] = field(default_factory=list)
    continuation: str | None = None
    web: bool = False
    finished: bool = False
    failed: bool = False

    def read(self, frame: dict | str) -> dict | None:
        """The panel's frame of the gateway's ``frame``: a piece of ``text``, the ``usage`` of the allowance or the
        provider's ``error``. None for the others: what they say only the closing ``done`` carries."""
        if frame == "[DONE]":
            self.finished = True
            return None
        kind = frame.get("type")
        if kind == "text_delta" and frame.get("text"):
            self.text.append(str(frame["text"]))
            return {"type": "text", "text": str(frame["text"])}
        if kind == "usage":
            return {"type": "usage", **{key: frame.get(key) for key in ALLOWANCE}}
        if kind == "error":
            self.failed = True
            return {"type": "error", "code": "assistant.provider_failed", "retriable": bool(frame.get("retriable"))}
        self.keep(kind, frame)
        return None

    def keep(self, kind: Any, frame: dict) -> None:
        """What a frame the panel does not show tells the closing ``done``: a tool the model asked for, the turn's
        ``continuation``, or that the answer brought pages from the web."""
        if kind == "function_call":
            self.calls.append(
                {
                    "call_id": str(frame.get("call_id")),
                    "name": str(frame.get("name")),
                    "arguments": str(frame.get("arguments") or "{}"),
                }
            )
        elif kind == "response":
            self.continuation = frame.get("continuation") or None
        elif kind == "web":
            self.web = True

    def done(self) -> dict:
        """The closing frame: what the browser keeps (``append``), the tools that wait (``pending``), their
        ``continuation`` and ``web``. A turn that failed or never ended keeps only what was said, if anything was."""
        said = "".join(self.text)
        if self.failed or not self.finished:
            append = [assistant_message(said, [])] if said else []
            return {"type": "done", "append": append, "pending": [], "continuation": None, "web": self.web}
        return {
            "type": "done",
            "append": [assistant_message(said, self.calls)],
            "pending": self.calls,
            "continuation": self.continuation,
            "web": self.web,
        }
