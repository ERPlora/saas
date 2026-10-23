"""The client of DeepSeek (ASSISTANT-G34): OpenAI's Chat Completions format at DeepSeek's address
(``https://api.deepseek.com``), without ``parallel_tool_calls`` (DeepSeek's API does not document it), and every
model it lists is a chat model."""

from assistant.providers.openai import OpenAIProvider


class DeepSeekProvider(OpenAIProvider):
    kind = "deepseek"
    parallel_tool_calls_flag = False

    @staticmethod
    def is_newer(model_id: str) -> bool:
        return False

    def is_chat_model(self, model_id: str) -> bool:
        return True
