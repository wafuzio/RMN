"""
Centralized client for the AlchemyAI / Gale relay.

The relay presents an OpenAI-compatible API that routes to GPT, Claude,
Gemini, and Sonar models.  All access goes through the same OpenAI SDK —
even for non-OpenAI models — because the relay handles provider dispatch.

Environment variables
---------------------
ALCHEMY_API_KEY           (required) JWT token for relay auth
ALCHEMY_RELAY_BASE_URL    (optional) override relay endpoint

Usage
-----
    from llm_client import RelayClient, chat

    # One-shot convenience
    answer = chat("Summarize this quarter's results.")

    # Full control
    client = RelayClient()
    for chunk in client.stream("Explain PX detection.", model="claude-opus-4-6"):
        print(chunk, end="", flush=True)
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Generator, Sequence

from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError

# ── Relay defaults ─────────────────────────────────────────────────────────
DEFAULT_RELAY_BASE_URL = "https://relay.ai.gale.technology/api/relay/openai/v1"
_RETRYABLE = (APIConnectionError, APITimeoutError, RateLimitError)
_MAX_RETRIES = 3
_BACKOFF_BASE = 1.5  # seconds; exponential: 1.5, 3.0, 6.0


# ── Model catalog ──────────────────────────────────────────────────────────
# Exact relay-defined model IDs.  DO NOT rename or normalize these strings.
# "status" tracks empirical testing against v1/chat/completions.
#   ok      → known working
#   failing → known broken on chat.completions (may work on other endpoints)
#   untested→ not yet verified

@dataclass(frozen=True)
class ModelInfo:
    """Metadata for a single relay model."""
    id: str                              # exact relay model string
    display_name: str                    # human label
    capabilities: frozenset[str]         # {"chat", "edit", "apply"}
    tier: str                            # "fast" | "thinking" | "pro"
    family: str                          # "gpt" | "claude" | "gemini" | "sonar"
    status: str = "untested"             # "ok" | "failing" | "untested"
    note: str = ""

    @property
    def supports_chat(self) -> bool:
        return "chat" in self.capabilities and self.status != "failing"


# Build catalog from the tested relay inventory.
_CATALOG_LIST: list[ModelInfo] = [
    # ── GPT ────────────────────────────────────────────────────────────────
    # Tested 2026-03-27 against relay
    ModelInfo("gpt-5.4-2026-03-05", "GPT-5.4 Auto",     frozenset({"chat", "edit", "apply"}), "auto",     "gpt",    status="ok"),
    ModelInfo("gpt-5.4-instant",    "GPT-5.4 Instant",   frozenset({"chat", "edit", "apply"}), "fast",     "gpt",    status="failing",
             note="404 — model not found on relay"),
    ModelInfo("gpt-5.4-thinking",   "GPT-5.4 Thinking",  frozenset({"chat", "edit", "apply"}), "thinking", "gpt",    status="failing",
             note="404 — model not found on relay"),
    ModelInfo("gpt-5.4-pro",        "GPT-5.4 Pro",       frozenset({"chat", "edit", "apply"}), "pro",      "gpt",    status="failing",
             note="Not a chat model; needs a different endpoint"),
    # ── Claude ─────────────────────────────────────────────────────────────
    # All 404 as of 2026-03-27 — IDs may be wrong or not provisioned for this key
    ModelInfo("claude-haiku-4-5-20251001", "Claude Haiku 4.5",  frozenset({"chat"}), "fast",     "claude", status="failing",
             note="404 — model not found on relay"),
    ModelInfo("claude-sonnet-4-6",         "Claude Sonnet 4.6", frozenset({"chat"}), "thinking", "claude", status="failing",
             note="404 — model not found on relay"),
    ModelInfo("claude-opus-4-6",           "Claude Opus 4.6",   frozenset({"chat"}), "pro",      "claude", status="failing",
             note="404 — model not found on relay"),
    # ── Gemini ─────────────────────────────────────────────────────────────
    # All 404 as of 2026-03-27
    ModelInfo("gemini-3-flash-preview",    "Gemini 3 Fast",     frozenset({"chat"}), "fast",     "gemini", status="failing",
             note="404 — model not found on relay"),
    ModelInfo("gemini-3-thinking-preview", "Gemini 3 Thinking", frozenset({"chat"}), "thinking", "gemini", status="failing",
             note="404 — model not found on relay"),
    ModelInfo("gemini-3.1-pro-preview",    "Gemini 3.1 Pro",    frozenset({"chat"}), "pro",      "gemini", status="failing",
             note="404 — model not found on relay"),
    # ── Sonar (Perplexity) ─────────────────────────────────────────────────
    # All 404 as of 2026-03-27
    ModelInfo("sonar",               "Sonar",              frozenset({"chat"}), "fast",     "sonar", status="failing",
             note="404 — model not found on relay"),
    ModelInfo("sonar-pro",           "Sonar Pro",          frozenset({"chat"}), "thinking", "sonar", status="failing",
             note="404 — model not found on relay"),
    ModelInfo("sonar-reasoning-pro", "Sonar Reasoning Pro",frozenset({"chat"}), "pro",      "sonar", status="failing",
             note="404 — model not found on relay"),
]

MODEL_CATALOG: dict[str, ModelInfo] = {m.id: m for m in _CATALOG_LIST}


def list_models(
    *,
    family: str | None = None,
    tier: str | None = None,
    chat_only: bool = False,
) -> list[ModelInfo]:
    """Filter the catalog.  All filters are AND-ed."""
    out = list(_CATALOG_LIST)
    if family:
        out = [m for m in out if m.family == family]
    if tier:
        out = [m for m in out if m.tier == tier]
    if chat_only:
        out = [m for m in out if m.supports_chat]
    return out


def validate_model(model_id: str, *, require_chat: bool = True) -> ModelInfo:
    """Look up a model ID; raise ValueError if unknown or incapable."""
    info = MODEL_CATALOG.get(model_id)
    if info is None:
        known = ", ".join(sorted(MODEL_CATALOG))
        raise ValueError(
            f"Unknown relay model {model_id!r}.  Known models: {known}"
        )
    if require_chat and info.status == "failing":
        raise ValueError(
            f"Model {model_id!r} is known-failing on chat.completions"
            f"{(': ' + info.note) if info.note else ''}"
        )
    return info


# ── Transport config (env-driven) ─────────────────────────────────────────

@dataclass(frozen=True)
class RelayConfig:
    """Immutable transport settings — derived entirely from environment."""
    api_key: str
    base_url: str

    @classmethod
    def from_env(cls) -> RelayConfig:
        api_key = os.environ.get("ALCHEMY_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "ALCHEMY_API_KEY is not set.  "
                "Export it in your shell or .env before using the relay client."
            )
        base_url = os.environ.get(
            "ALCHEMY_RELAY_BASE_URL", DEFAULT_RELAY_BASE_URL
        ).strip().rstrip("/")
        return cls(api_key=api_key, base_url=base_url)


# ── Completion config (app-level) ─────────────────────────────────────────

@dataclass
class CompletionConfig:
    """Per-call generation parameters.  Separate from transport."""
    model: str = "gpt-5.4-2026-03-05"
    temperature: float = 0.2
    max_tokens: int = 2000
    thinking_effort: str | None = None   # relay-specific; passed via extra_body

    def to_create_kwargs(self) -> dict[str, Any]:
        """Build the kwargs dict for client.chat.completions.create()."""
        kw: dict[str, Any] = {
            "model": self.model,
            "temperature": self.temperature,
            "max_completion_tokens": self.max_tokens,
        }
        if self.thinking_effort:
            kw["extra_body"] = {"thinking_effort": self.thinking_effort}
        return kw


# ── Relay client ───────────────────────────────────────────────────────────

Message = dict[str, str]  # {"role": "...", "content": "..."}


class RelayClient:
    """Thin, composable wrapper around the AlchemyAI relay.

    Handles auth, model validation, retries, streaming.
    All methods accept an optional ``model`` override so the same client
    instance can hit different relay models.
    """

    def __init__(
        self,
        config: RelayConfig | None = None,
        default_completion: CompletionConfig | None = None,
    ):
        self._config = config or RelayConfig.from_env()
        self._default = default_completion or CompletionConfig()
        self._openai = OpenAI(
            api_key=self._config.api_key,
            base_url=self._config.base_url,
        )

    # ── internal helpers ───────────────────────────────────────────────────

    def _resolve_config(self, **overrides: Any) -> CompletionConfig:
        """Merge per-call overrides onto the default CompletionConfig."""
        vals = {
            "model": overrides.get("model", self._default.model),
            "temperature": overrides.get("temperature", self._default.temperature),
            "max_tokens": overrides.get("max_tokens", self._default.max_tokens),
            "thinking_effort": overrides.get("thinking_effort", self._default.thinking_effort),
        }
        return CompletionConfig(**vals)

    @staticmethod
    def _ensure_messages(
        prompt: str | None,
        messages: Sequence[Message] | None,
        system: str | None,
    ) -> list[Message]:
        """Build a messages list from the various convenience args."""
        if messages and prompt:
            raise ValueError("Pass prompt or messages, not both")
        if messages:
            msgs = list(messages)
        elif prompt:
            msgs = [{"role": "user", "content": prompt}]
        else:
            raise ValueError("Either prompt or messages is required")
        if system:
            msgs.insert(0, {"role": "system", "content": system})
        return msgs

    def _call_with_retry(self, create_fn, **kw) -> Any:
        """Retry on transient network / rate-limit errors."""
        last_err: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                return create_fn(**kw)
            except _RETRYABLE as exc:
                last_err = exc
                wait = _BACKOFF_BASE * (2 ** attempt)
                time.sleep(wait)
        raise RuntimeError(
            f"Relay call failed after {_MAX_RETRIES} retries: {last_err}"
        ) from last_err

    # ── public API ─────────────────────────────────────────────────────────

    def complete(
        self,
        prompt: str | None = None,
        *,
        messages: Sequence[Message] | None = None,
        system: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        thinking_effort: str | None = None,
    ) -> str:
        """Single-turn or multi-turn completion.  Returns the assistant text."""
        overrides: dict[str, Any] = {}
        if model is not None:
            overrides["model"] = model
        if temperature is not None:
            overrides["temperature"] = temperature
        if max_tokens is not None:
            overrides["max_tokens"] = max_tokens
        if thinking_effort is not None:
            overrides["thinking_effort"] = thinking_effort

        cfg = self._resolve_config(**overrides)
        validate_model(cfg.model)
        msgs = self._ensure_messages(prompt, messages, system)

        response = self._call_with_retry(
            self._openai.chat.completions.create,
            messages=msgs,
            stream=False,
            **cfg.to_create_kwargs(),
        )
        return response.choices[0].message.content or ""

    def stream(
        self,
        prompt: str | None = None,
        *,
        messages: Sequence[Message] | None = None,
        system: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        thinking_effort: str | None = None,
    ) -> Generator[str, None, None]:
        """Streaming completion.  Yields content deltas as strings."""
        overrides: dict[str, Any] = {}
        if model is not None:
            overrides["model"] = model
        if temperature is not None:
            overrides["temperature"] = temperature
        if max_tokens is not None:
            overrides["max_tokens"] = max_tokens
        if thinking_effort is not None:
            overrides["thinking_effort"] = thinking_effort

        cfg = self._resolve_config(**overrides)
        validate_model(cfg.model)
        msgs = self._ensure_messages(prompt, messages, system)

        stream_resp = self._call_with_retry(
            self._openai.chat.completions.create,
            messages=msgs,
            stream=True,
            **cfg.to_create_kwargs(),
        )
        for chunk in stream_resp:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta

    @property
    def relay_url(self) -> str:
        return self._config.base_url


# ── Convenience functions ──────────────────────────────────────────────────
# For simple one-off calls without instantiating RelayClient yourself.

_default_client: RelayClient | None = None


def _get_default_client() -> RelayClient:
    global _default_client
    if _default_client is None:
        _default_client = RelayClient()
    return _default_client


def chat(prompt: str, *, model: str | None = None, **kw) -> str:
    """One-shot chat completion via the relay."""
    return _get_default_client().complete(prompt, model=model, **kw)


def stream_chat(prompt: str, *, model: str | None = None, **kw) -> Generator[str, None, None]:
    """One-shot streaming chat via the relay."""
    yield from _get_default_client().stream(prompt, model=model, **kw)


# ── CLI smoke test ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AlchemyAI relay smoke test")
    parser.add_argument("--model", default="gpt-5.4-2026-03-05",
                        help="Relay model ID (default: gpt-5.4-2026-03-05)")
    parser.add_argument("--list", action="store_true",
                        help="List all catalog models and exit")
    parser.add_argument("--stream", action="store_true",
                        help="Use streaming mode")
    parser.add_argument("prompt", nargs="?", default="Say hello in one sentence.",
                        help="Prompt to send")
    args = parser.parse_args()

    if args.list:
        print(f"{'Model ID':<35} {'Display':<25} {'Tier':<10} {'Family':<8} {'Status'}")
        print("-" * 95)
        for m in _CATALOG_LIST:
            print(f"{m.id:<35} {m.display_name:<25} {m.tier:<10} {m.family:<8} {m.status}")
        raise SystemExit(0)

    print(f"relay:  {DEFAULT_RELAY_BASE_URL}")
    print(f"model:  {args.model}")
    print(f"stream: {args.stream}")
    print("-" * 40)

    if args.stream:
        for tok in stream_chat(args.prompt, model=args.model):
            print(tok, end="", flush=True)
        print()
    else:
        print(chat(args.prompt, model=args.model))