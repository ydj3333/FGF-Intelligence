"""Provider-agnostic LLM client with tool calling (standard library only).

Supported providers
-------------------
* ``anthropic`` – Claude via the Messages API.
* ``openai``    – any OpenAI-compatible Chat Completions endpoint: OpenAI,
                  OpenRouter, Groq, Together, Mistral, DeepSeek, Google Gemini's
                  OpenAI-compatible endpoint, or a local Ollama / LM Studio
                  server. Set ``FGF_LLM_BASE_URL`` to switch.

Configuration (environment variables)
-------------------------------------
FGF_LLM_PROVIDER   anthropic | openai   (auto-detected from the key if unset)
ANTHROPIC_API_KEY  key for anthropic
FGF_LLM_API_KEY / OPENAI_API_KEY   key for openai-compatible providers
FGF_AGENT_MODEL    model id (falls back to FGF_LLM_MODEL, then a provider default)
FGF_LLM_BASE_URL   base URL for openai-compatible providers (default https://api.openai.com/v1)
FGF_LLM_TIMEOUT    seconds per call (default 45)

The neutral message format used by the agent:
    {"role": "user", "content": "text"}
    {"role": "assistant", "content": "text", "tool_calls": [{"id","name","arguments"}]}
    {"role": "tool", "results": [{"id","name","content"}]}
"""
from __future__ import annotations

import http.client
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-5-5",
    "openai": "gpt-5.6-luna",  # matches the project's existing FGF_LLM_MODEL default
}


class LLMError(RuntimeError):
    def __init__(self, category: str, detail: str = ""):
        super().__init__(f"{category}: {detail}"[:300])
        self.category = category
        self.detail = detail[:300]


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class LLMResponse:
    text: str
    tool_calls: List[ToolCall] = field(default_factory=list)
    stop_reason: str = ""
    usage: Dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0


def _env(*names: str, default: str = "") -> str:
    for n in names:
        v = os.getenv(n, "").strip()
        if v:
            return v
    return default


def detect_provider() -> Optional[str]:
    explicit = _env("FGF_LLM_PROVIDER").lower()
    if explicit in ("anthropic", "claude"):
        return "anthropic" if _env("ANTHROPIC_API_KEY", "FGF_LLM_API_KEY") else None
    if explicit in ("openai", "openai-compatible", "openrouter", "groq", "ollama", "gemini"):
        if _env("FGF_LLM_API_KEY", "OPENAI_API_KEY") or "localhost" in _env("FGF_LLM_BASE_URL") or "127.0.0.1" in _env("FGF_LLM_BASE_URL"):
            return "openai"
        return None
    if _env("ANTHROPIC_API_KEY"):
        return "anthropic"
    if _env("FGF_LLM_API_KEY", "OPENAI_API_KEY"):
        return "openai"
    return None


class LLMClient:
    """Base class. Subclasses implement ``_call``."""

    provider = "base"

    def __init__(self, model: str, timeout: float = 45.0, max_tokens: int = 1400):
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens

    def chat(self, system: str, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]],
             temperature: float = 0.2) -> LLMResponse:
        last: Optional[LLMError] = None
        for attempt in range(3):
            try:
                started = time.time()
                resp = self._call(system, messages, tools, temperature)
                resp.latency_ms = round((time.time() - started) * 1000, 1)
                return resp
            except LLMError as e:
                last = e
                if e.category not in ("rate_limited", "server_error", "timeout", "transport_failure"):
                    raise
                time.sleep(1.5 * (attempt + 1))
        raise last or LLMError("unknown", "LLM call failed")

    # ----------------------------------------------------------- HTTP helper
    def _post(self, url: str, headers: Dict[str, str], body: Dict[str, Any]) -> Dict[str, Any]:
        req = Request(url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                      headers={**headers, "Content-Type": "application/json", "Accept": "application/json"},
                      method="POST")
        try:
            with urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except HTTPError as e:
            code = e.code
            try:
                raw = e.read().decode("utf-8", "replace")
                err = json.loads(raw).get("error", {})
                detail = (err.get("type") or err.get("code") or "") if isinstance(err, dict) else ""
            except Exception:
                detail = ""
            cat = ("auth_failure" if code in (401, 403)
                   # OpenAI reports an empty/expired balance as 429 insufficient_quota:
                   # retrying cannot help, so it is a hard failure.
                   else "quota_exhausted" if code in (402, 429) and ("quota" in detail or "billing" in detail or code == 402)
                   else "rate_limited" if code == 429
                   else "bad_request" if code in (400, 404, 422) else "server_error" if code >= 500 else "http_error")
            raise LLMError(cat, f"HTTP {code} {detail}".strip())
        except TimeoutError:
            raise LLMError("timeout", "request timed out")
        except URLError as e:
            raise LLMError("transport_failure", type(getattr(e, "reason", e)).__name__)
        except (http.client.HTTPException, ConnectionError, OSError) as e:
            # e.g. RemoteDisconnected / IncompleteRead / connection reset: the
            # provider dropped the connection. Retryable, and counted by the breaker.
            raise LLMError("transport_failure", type(e).__name__)
        except json.JSONDecodeError:
            raise LLMError("malformed_response", "provider returned invalid JSON")

    def _call(self, system, messages, tools, temperature) -> LLMResponse:  # pragma: no cover
        raise NotImplementedError


class AnthropicClient(LLMClient):
    provider = "anthropic"

    def __init__(self, api_key: str, model: str, base_url: str = "https://api.anthropic.com", **kw):
        super().__init__(model, **kw)
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    @staticmethod
    def _convert(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for m in messages:
            role = m["role"]
            if role == "user":
                out.append({"role": "user", "content": m["content"]})
            elif role == "assistant":
                blocks: List[Dict[str, Any]] = []
                if m.get("content"):
                    blocks.append({"type": "text", "text": m["content"]})
                for tc in m.get("tool_calls") or []:
                    blocks.append({"type": "tool_use", "id": tc["id"], "name": tc["name"], "input": tc["arguments"]})
                out.append({"role": "assistant", "content": blocks or m.get("content", "")})
            elif role == "tool":
                out.append({"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": r["id"], "content": r["content"]}
                    for r in m["results"]
                ]})
        # The API requires alternating roles; merge consecutive user turns.
        merged: List[Dict[str, Any]] = []
        for m in out:
            if merged and merged[-1]["role"] == m["role"] == "user":
                prev = merged[-1]["content"]
                prev_blocks = prev if isinstance(prev, list) else [{"type": "text", "text": prev}]
                cur_blocks = m["content"] if isinstance(m["content"], list) else [{"type": "text", "text": m["content"]}]
                merged[-1] = {"role": "user", "content": prev_blocks + cur_blocks}
            else:
                merged.append(m)
        return merged

    def _call(self, system, messages, tools, temperature) -> LLMResponse:
        body: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": self._convert(messages),
            "temperature": temperature,
        }
        if tools:
            body["tools"] = [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]} for t in tools]
        data = self._post(self.base_url + "/v1/messages",
                          {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"}, body)
        text_parts, calls = [], []
        for block in data.get("content") or []:
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                calls.append(ToolCall(block.get("id") or uuid.uuid4().hex, block.get("name", ""), block.get("input") or {}))
        if not text_parts and not calls:
            raise LLMError("malformed_response", "no content blocks")
        return LLMResponse("".join(text_parts).strip(), calls, data.get("stop_reason", ""), data.get("usage") or {})


class OpenAICompatibleClient(LLMClient):
    provider = "openai"

    def __init__(self, api_key: str, model: str, base_url: str = "https://api.openai.com/v1", **kw):
        super().__init__(model, **kw)
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    @staticmethod
    def _convert(system: str, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = [{"role": "system", "content": system}]
        for m in messages:
            role = m["role"]
            if role == "user":
                out.append({"role": "user", "content": m["content"]})
            elif role == "assistant":
                msg: Dict[str, Any] = {"role": "assistant", "content": m.get("content") or None}
                if m.get("tool_calls"):
                    msg["tool_calls"] = [{"id": tc["id"], "type": "function",
                                          "function": {"name": tc["name"], "arguments": json.dumps(tc["arguments"], ensure_ascii=False)}}
                                         for tc in m["tool_calls"]]
                out.append(msg)
            elif role == "tool":
                for r in m["results"]:
                    out.append({"role": "tool", "tool_call_id": r["id"], "content": r["content"]})
        return out

    def _call(self, system, messages, tools, temperature) -> LLMResponse:
        body: Dict[str, Any] = {"model": self.model, "messages": self._convert(system, messages)}
        # OpenAI's newer models use max_completion_tokens and may reject a custom
        # temperature; most other compatible servers accept max_tokens/temperature.
        if "api.openai.com" in self.base_url:
            body["max_completion_tokens"] = self.max_tokens
        else:
            body["max_tokens"] = self.max_tokens
            body["temperature"] = temperature
        if tools:
            body["tools"] = [{"type": "function", "function": t} for t in tools]
            body["tool_choice"] = "auto"
        headers = {"Authorization": "Bearer " + self.api_key} if self.api_key else {}
        data = self._post(self.base_url + "/chat/completions", headers, body)
        choices = data.get("choices") or []
        if not choices:
            raise LLMError("malformed_response", "no choices")
        msg = choices[0].get("message") or {}
        calls = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function") or {}
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {"_raw": fn.get("arguments")}
            calls.append(ToolCall(tc.get("id") or uuid.uuid4().hex, fn.get("name", ""), args if isinstance(args, dict) else {}))
        text = msg.get("content") or ""
        if isinstance(text, list):  # some providers return content parts
            text = "".join(p.get("text", "") for p in text if isinstance(p, dict))
        return LLMResponse(str(text).strip(), calls, choices[0].get("finish_reason", ""), data.get("usage") or {})


def build_client_from_env() -> Optional[LLMClient]:
    provider = detect_provider()
    if not provider:
        return None
    timeout = float(_env("FGF_LLM_TIMEOUT", default="45"))
    max_tokens = int(_env("FGF_AGENT_MAX_TOKENS", default="1400"))
    if provider == "anthropic":
        # FGF_LLM_MODEL historically holds an OpenAI model id, so it is not
        # used as a fallback for Claude.
        model = _env("FGF_AGENT_MODEL", default=DEFAULT_MODELS["anthropic"])
    else:
        model = _env("FGF_AGENT_MODEL", "FGF_LLM_MODEL", default=DEFAULT_MODELS["openai"])
    if provider == "anthropic":
        return AnthropicClient(_env("ANTHROPIC_API_KEY", "FGF_LLM_API_KEY"), model,
                               base_url=_env("ANTHROPIC_BASE_URL", default="https://api.anthropic.com"),
                               timeout=timeout, max_tokens=max_tokens)
    return OpenAICompatibleClient(_env("FGF_LLM_API_KEY", "OPENAI_API_KEY"), model,
                                  base_url=_env("FGF_LLM_BASE_URL", default="https://api.openai.com/v1"),
                                  timeout=timeout, max_tokens=max_tokens)
