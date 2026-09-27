"""Thin, provider-agnostic wrapper around an OpenAI-compatible chat completion API.

Supports OpenAI, Azure OpenAI (via OPENAI_BASE_URL) and any gateway implementing
the same REST contract. Structured output is enforced by asking for strict JSON
and validating/repairing against a Pydantic schema.
"""
from __future__ import annotations

import json
import logging
from typing import Type, TypeVar

import httpx
from openai import APIConnectionError, APIStatusError, APITimeoutError, BadRequestError, NotFoundError, OpenAI
from pydantic import BaseModel, ValidationError
from tenacity import retry, retry_if_exception, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Transient network/provider errors worth retrying (in addition to malformed JSON output).
_TRANSIENT_ERRORS = (
    json.JSONDecodeError,
    ValidationError,
    APIConnectionError,
    APITimeoutError,
    APIStatusError,
    httpx.HTTPError,
)

# BadRequestError/NotFoundError under native structured outputs usually mean "this model/
# provider doesn't support response_format=json_schema" — a deterministic failure that
# should fall back immediately rather than burn retries.
_NATIVE_NON_RETRYABLE = (BadRequestError, NotFoundError)


class LLMNotConfiguredError(RuntimeError):
    """Raised when no LLM API key is configured."""


class LLMOutputError(RuntimeError):
    """Raised when the model repeatedly fails to produce valid structured output."""


def _client() -> OpenAI:
    if not settings.llm_configured:
        raise LLMNotConfiguredError(
            "OPENAI_API_KEY is not set. Configure it in your .env file to enable AI-generated content."
        )
    # Generous read timeout + streaming (below) avoids proxies/VPNs killing long-idle connections
    # while a large non-streamed completion is still being generated server-side.
    timeout = httpx.Timeout(connect=10.0, read=180.0, write=30.0, pool=10.0)
    return OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url, timeout=timeout, max_retries=0)


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise LLMOutputError("Model response did not contain a JSON object.")
    return json.loads(text[start : end + 1])


class LLMClient:
    """Runs single structured-output completions against the configured model."""

    def __init__(self) -> None:
        self._client: OpenAI | None = None
        # Cached per-instance once we learn whether the provider/model supports the SDK's
        # native structured-output parsing, so we don't retry a doomed request every call.
        self._native_structured_supported: bool | None = None

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            self._client = _client()
        return self._client

    def _complete(self, system_prompt: str, user_prompt: str) -> str:
        """Stream the completion and join it, rather than waiting for one large buffered response."""
        chunks: list[str] = []
        stream = self.client.chat.completions.create(
            model=settings.openai_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_output_tokens,
            stream=True,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        for event in stream:
            if not event.choices:
                continue
            delta = event.choices[0].delta.content
            if delta:
                chunks.append(delta)
        return "".join(chunks)

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=20),
        retry=retry_if_exception(
            lambda exc: isinstance(exc, _TRANSIENT_ERRORS) and not isinstance(exc, _NATIVE_NON_RETRYABLE)
        ),
        reraise=True,
    )
    def _generate_native(self, system_prompt: str, user_prompt: str, schema: Type[T]) -> T:
        completion = self.client.beta.chat.completions.parse(
            model=settings.openai_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_output_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format=schema,
        )
        message = completion.choices[0].message
        if message.refusal:
            raise LLMOutputError(f"Model refused to answer: {message.refusal}")
        if message.parsed is None:
            raise LLMOutputError("Model returned no parsed structured output.")
        return message.parsed

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=20),
        retry=retry_if_exception_type(_TRANSIENT_ERRORS + (LLMOutputError,)),
        reraise=True,
    )
    def _generate_fallback(self, system_prompt: str, user_prompt: str, schema: Type[T]) -> T:
        """Prompt-based JSON generation, for providers without native structured-output support."""
        schema_json = json.dumps(schema.model_json_schema(), indent=2)
        instructions = (
            f"{user_prompt}\n\n"
            "Respond with ONLY a single valid JSON object (no markdown fences, no commentary) "
            f"that conforms exactly to this JSON Schema:\n{schema_json}"
        )
        content = self._complete(system_prompt, instructions)
        try:
            data = _extract_json(content)
            return schema.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            logger.warning("Structured output validation failed: %s", exc)
            raise

    def generate_structured(self, system_prompt: str, user_prompt: str, schema: Type[T]) -> T:
        """Call the model and return `schema`-validated data.

        Prefers the SDK's native structured-output parsing (guarantees schema-conforming
        JSON) and transparently falls back to prompt+regex JSON extraction for providers
        or models that don't support it.
        """
        if settings.use_native_structured_outputs and self._native_structured_supported is not False:
            try:
                result = self._generate_native(system_prompt, user_prompt, schema)
                self._native_structured_supported = True
                return result
            except (BadRequestError, NotFoundError) as exc:
                logger.warning(
                    "Native structured outputs unsupported by model '%s' (%s); falling back to "
                    "prompt-based JSON for the rest of this run.",
                    settings.openai_model,
                    exc,
                )
                self._native_structured_supported = False
        return self._generate_fallback(system_prompt, user_prompt, schema)

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=20),
        retry=retry_if_exception_type(_TRANSIENT_ERRORS),
        reraise=True,
    )
    def generate_text(self, system_prompt: str, user_prompt: str) -> str:
        return self._complete(system_prompt, user_prompt)


llm_client = LLMClient()
