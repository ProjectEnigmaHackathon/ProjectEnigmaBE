"""
LLM Configuration

Provides a centralized way to configure and access the Language Model
for the Project Enigma application.
"""

from langchain_openai import ChatOpenAI
from app.core.config import get_settings


# Global LLM instance
_llm = None


def get_llm() -> ChatOpenAI:
    """
    Get the configured LLM instance.
    
    Returns:
        ChatOpenAI: Configured language model instance
    """
    global _llm
    if _llm is None:
        settings = get_settings()
        _llm = ChatOpenAI(
            model="gpt-4",
            temperature=0,
            openai_api_key=settings.openai_api_key
        )
    return _llm


def reset_llm():
    """Reset the LLM instance (useful for testing)."""
    global _llm
    _llm = None