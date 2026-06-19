"""LLM provider factory.

This is the single swap point for the model. `init_chat_model` resolves the right
LangChain integration from `model_provider`, so adding a provider is: install its
integration package (e.g. `langchain-anthropic`) and set LLM_PROVIDER / LLM_MODEL in .env.
No other code changes.
"""

from langchain.chat_models import init_chat_model

from .config import settings


def build_llm():
    return init_chat_model(
        settings.llm_model,
        model_provider=settings.llm_provider,
        temperature=0.7,
    )
