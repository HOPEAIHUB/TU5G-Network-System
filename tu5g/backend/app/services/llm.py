"""
LLM Service Module.
Provides a LangChain-style wrapper for interacting with OpenAI, Azure OpenAI,
and Anthropic LLM APIs asynchronously.
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Providers
PROVIDER_OPENAI = "openai"
PROVIDER_AZURE = "azure"
PROVIDER_ANTHROPIC = "anthropic"


class LLMError(Exception):
    """Custom exception class for LLM service errors."""
    pass


async def chat_completion(
    system: str,
    user_msg: str,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> str:
    """
    Sends a message to the configured LLM provider and returns the response.

    Args:
        system (str): The system prompt/instructions.
        user_msg (str): The user input message.
        temperature (Optional[float]): LLM sampling temperature (defaults to 0.6 or env var).
        max_tokens (Optional[int]): LLM max output tokens (defaults to 512 or env var).

    Returns:
        str: The generated response text.

    Raises:
        LLMError: If the provider is unknown or if the API call fails.
    """
    provider = os.getenv("LLM_PROVIDER", PROVIDER_OPENAI).lower()

    # Determine hyperparameters
    # Priority: passed parameters -> environment variables -> defaults
    final_temp = temperature
    if final_temp is None:
        try:
            final_temp = float(os.getenv("LLM_TEMPERATURE", "0.6"))
        except ValueError:
            final_temp = 0.6

    final_max_tokens = max_tokens
    if final_max_tokens is None:
        try:
            final_max_tokens = int(os.getenv("LLM_MAX_TOKENS", "512"))
        except ValueError:
            final_max_tokens = 512

    if provider == PROVIDER_OPENAI:
        try:
            from openai import AsyncOpenAI
        except ImportError as e:
            raise LLMError("openai library is not installed.") from e

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise LLMError("OPENAI_API_KEY environment variable is not set.")

        model = os.getenv("OPENAI_MODEL", "gpt-4o")

        try:
            client = AsyncOpenAI(api_key=api_key)
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_msg},
                ],
                temperature=final_temp,
                max_tokens=final_max_tokens,
            )
            if not response.choices:
                raise LLMError("OpenAI returned an empty response.")
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"OpenAI completion failed: {e}")
            raise LLMError(f"OpenAI API error: {str(e)}") from e

    elif provider == PROVIDER_AZURE:
        try:
            from openai import AsyncAzureOpenAI
        except ImportError as e:
            raise LLMError("openai library is not installed.") from e

        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01")

        if not api_key:
            raise LLMError("AZURE_OPENAI_API_KEY environment variable is not set.")
        if not endpoint:
            raise LLMError("AZURE_OPENAI_ENDPOINT environment variable is not set.")

        # In Azure, the deployment name is usually passed to 'model'
        model = os.getenv("AZURE_OPENAI_DEPLOYMENT", os.getenv("AZURE_OPENAI_MODEL", "gpt-4o"))

        try:
            client = AsyncAzureOpenAI(
                api_key=api_key,
                api_version=api_version,
                azure_endpoint=endpoint,
            )
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_msg},
                ],
                temperature=final_temp,
                max_tokens=final_max_tokens,
            )
            if not response.choices:
                raise LLMError("Azure OpenAI returned an empty response.")
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"Azure OpenAI completion failed: {e}")
            raise LLMError(f"Azure OpenAI API error: {str(e)}") from e

    elif provider == PROVIDER_ANTHROPIC:
        try:
            from anthropic import AsyncAnthropic
        except ImportError as e:
            raise LLMError("anthropic library is not installed.") from e

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise LLMError("ANTHROPIC_API_KEY environment variable is not set.")

        model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

        try:
            client = AsyncAnthropic(api_key=api_key)
            response = await client.messages.create(
                model=model,
                max_tokens=final_max_tokens,
                temperature=final_temp,
                system=system,
                messages=[
                    {"role": "user", "content": user_msg},
                ],
            )
            if not response.content:
                raise LLMError("Anthropic returned an empty response.")
            return response.content[0].text
        except Exception as e:
            logger.error(f"Anthropic completion failed: {e}")
            raise LLMError(f"Anthropic API error: {str(e)}") from e

    else:
        raise LLMError(
            f"Unsupported LLM provider: '{provider}'. "
            f"Supported providers: {PROVIDER_OPENAI}, {PROVIDER_AZURE}, {PROVIDER_ANTHROPIC}."
        )
