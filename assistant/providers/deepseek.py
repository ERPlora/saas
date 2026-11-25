"""The client of DeepSeek: OpenAI's Chat Completions format at DeepSeek's address
(``https://api.deepseek.com``), and every model it lists is a chat model."""

from assistant.providers.openai import OpenAIProvider


class DeepSeekProvider(OpenAIProvider):
    kind = "deepseek"

    @staticmethod
    def is_newer(model_id: str) -> bool:
        return False

    def is_chat_model(self, model_id: str) -> bool:
        return True
