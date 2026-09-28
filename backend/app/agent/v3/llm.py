"""
Provider-thin LLM interface: one `chat()` call with tools, streaming text
deltas, normalised usage and real cost. Adapters: OpenAI Responses API,
Google Gemini (google-genai) and Anthropic. Every LLM call in the app goes
through here so a model swap is an env change.

Neutral message shapes (what callers pass in `messages`):
  {"role": "user" | "assistant", "content": str}
  {"role": "assistant", "content": str, "tool_calls": [ToolCall-as-dict], "native": {...}}
  {"role": "tool", "tool_call_id": str, "name": str, "content": str}
`native` carries provider items (reasoning, thought signatures) for replay
within one turn; it is ignored by other providers.

Caching: callers keep `system` and `tools` byte-stable and put volatile text
in `messages`. OpenAI uses prompt_cache_key, Anthropic cache_control
breakpoints, Gemini implicit caching.
"""
import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# Model roles -> env var, with the documented defaults. Model strings live only here.
MODEL_ENV_DEFAULTS = {
    "AGENT_MODEL": "gpt-6-luna",
    "SUMMARY_MODEL": "gpt-6-luna",
    "NEWS_ENRICHMENT_MODEL": "gpt-6-luna",
}

# USD per 1M tokens: (input, cached input, cache write, output). Verified 2026-09-28.
PRICES = {
    "gpt-6-luna": (0.10, 0.01, 0.125, 0.50),
    "gemini-3.5-flash-lite": (0.30, 0.03, 0.30, 2.50),
    "claude-sonnet-5": (2.00, 0.20, 2.50, 10.00),
    "gpt-5-mini": (0.25, 0.025, 0.25, 2.00),
    "gpt-5-nano": (0.05, 0.005, 0.05, 0.40),
}
DISCOUNTED_TIERS = {"flex": 0.5, "batch": 0.5}

PROMPT_CACHE_KEY = "footy-nac-v3"
RETRIES = 2


def model_for(role: str) -> str:
    return os.getenv(role) or MODEL_ENV_DEFAULTS[role]


class LLMError(RuntimeError):
    pass


@dataclass
class Usage:
    input_tokens: int = 0          # all input, cached included
    cached_input_tokens: int = 0
    cache_write_tokens: int = 0
    output_tokens: int = 0         # reasoning included
    reasoning_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(*(a + b for a, b in zip(asdict(self).values(), asdict(other).values())))

    def as_dict(self) -> Dict[str, int]:
        return asdict(self)


def cost_usd(model: str, usage: Usage, service_tier: Optional[str] = None) -> float:
    if model not in PRICES:
        raise LLMError(f"No price for model {model!r}; add it to llm.PRICES")
    p_in, p_cached, p_write, p_out = PRICES[model]
    uncached = max(usage.input_tokens - usage.cached_input_tokens - usage.cache_write_tokens, 0)
    cost = (uncached * p_in + usage.cached_input_tokens * p_cached
            + usage.cache_write_tokens * p_write + usage.output_tokens * p_out) / 1e6
    return round(cost * DISCOUNTED_TIERS.get(service_tier or "", 1.0), 8)


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str  # raw JSON text from the model


@dataclass
class LLMResult:
    text: str
    tool_calls: List[ToolCall]
    usage: Usage
    model: str
    cost_usd: float
    latency_s: float
    first_text_s: Optional[float] = None
    native: Dict[str, Any] = field(default_factory=dict)

    def assistant_message(self) -> Dict[str, Any]:
        """The neutral message to append to `messages` for the next call."""
        return {"role": "assistant", "content": self.text,
                "tool_calls": [asdict(c) for c in self.tool_calls], "native": self.native}


def provider_for(model: str) -> str:
    if model.startswith("gemini"):
        return "gemini"
    if model.startswith("claude"):
        return "anthropic"
    return "openai"


_clients: Dict[str, Any] = {}


def _tls_context():
    """Plain stdlib TLS context with certifi CAs. httpx2's default is a
    truststore.SSLContext, whose verify_mode setter recurses forever under
    gevent's patched ssl (the production gunicorn GeventWebSocketWorker)."""
    import ssl
    import certifi
    return ssl.create_default_context(cafile=certifi.where())


def _client(provider: str):
    if provider in _clients:
        return _clients[provider]
    key_env = {"openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}[provider]
    if not os.getenv(key_env):
        raise LLMError(f"{key_env} is not set")
    if provider == "openai":
        from openai import DefaultHttpxClient, OpenAI
        client = OpenAI(api_key=os.getenv(key_env), timeout=60.0, max_retries=2,
                        http_client=DefaultHttpxClient(verify=_tls_context()))
    elif provider == "gemini":
        from google import genai
        client = genai.Client(api_key=os.getenv(key_env))
    else:
        from anthropic import Anthropic, DefaultHttpxClient
        client = Anthropic(api_key=os.getenv(key_env), timeout=60.0, max_retries=2,
                           http_client=DefaultHttpxClient(verify=_tls_context()))
    _clients[provider] = client
    return client


def chat(
    messages: List[Dict[str, Any]],
    *,
    system: str = "",
    tools: Optional[List[Dict[str, Any]]] = None,
    model: Optional[str] = None,
    effort: Optional[str] = "low",
    on_text: Optional[Callable[[str], None]] = None,
    json_mode: bool = False,
    max_output_tokens: Optional[int] = None,
    timeout: float = 60.0,
    service_tier: Optional[str] = None,
) -> LLMResult:
    """One model call. `tools` are neutral {name, description, parameters} dicts
    with strict JSON schemas. Text deltas go to `on_text` as they stream."""
    model = model or model_for("AGENT_MODEL")
    provider = provider_for(model)
    adapter = {"openai": _openai_call, "gemini": _gemini_call, "anthropic": _anthropic_call}[provider]
    t0 = time.monotonic()
    state = {"first": None}

    def emit(delta: str):
        if state["first"] is None:
            state["first"] = time.monotonic() - t0
        if on_text:
            on_text(delta)

    client = _client(provider)
    for attempt in range(RETRIES + 1):
        try:
            text, calls, usage, native, tier = adapter(
                client, model, system, messages, tools or [], effort, emit,
                json_mode, max_output_tokens, timeout, service_tier)
            break
        except Exception as e:
            # Transient mid-stream server errors happen; retry only if nothing
            # was streamed to the user yet.
            if attempt == RETRIES or state["first"] is not None:
                raise
            logger.warning(f"LLM call failed ({type(e).__name__}: {e}); retry {attempt + 1}")
            time.sleep(0.5 * (attempt + 1))
    return LLMResult(text=text, tool_calls=calls, usage=usage, model=model,
                     cost_usd=cost_usd(model, usage, tier), latency_s=round(time.monotonic() - t0, 3),
                     first_text_s=state["first"], native={provider: native} if native else {})


def complete(prompt: str, *, system: str = "", role: str = "AGENT_MODEL", model: Optional[str] = None,
             track_endpoint: Optional[str] = None, **kwargs) -> LLMResult:
    """Single-turn helper for background jobs and v2 nodes. With
    `track_endpoint`, records model/tokens/cost in api_usage."""
    result = chat([{"role": "user", "content": prompt}], system=system,
                  model=model or model_for(role), **kwargs)
    if track_endpoint:
        record_usage(result.model, result.usage, result.cost_usd, endpoint=track_endpoint)
    return result


def record_usage(model: str, usage: Usage, cost: float, *, endpoint: str,
                 visitor_id: str = "system", ip_address: str = "") -> None:
    from app.middleware.usage_tracker import UsageTracker
    UsageTracker.track_usage(visitor_id=visitor_id, ip_address=ip_address, model=model,
                             input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
                             cached_input_tokens=usage.cached_input_tokens,
                             endpoint=endpoint, cost_usd=cost)


def parse_json(text: str) -> Any:
    """Parse model JSON output, tolerating markdown fences."""
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        raw = raw.rsplit("```", 1)[0]
    return json.loads(raw)


# ── OpenAI (Responses API) ─────────────────────────────────────────────────

def _openai_call(client, model, system, messages, tools, effort, emit, json_mode,
                 max_output_tokens, timeout, service_tier):
    items: List[Dict[str, Any]] = []
    for m in messages:
        if m["role"] == "tool":
            items.append({"type": "function_call_output", "call_id": m["tool_call_id"], "output": m["content"]})
        elif m.get("native", {}).get("openai"):
            items.extend(m["native"]["openai"])
        elif m.get("tool_calls"):
            if m.get("content"):
                items.append({"role": "assistant", "content": m["content"]})
            items.extend({"type": "function_call", "call_id": c["id"], "name": c["name"],
                          "arguments": c["arguments"]} for c in m["tool_calls"])
        else:
            items.append({"role": m["role"], "content": m["content"]})
    kwargs: Dict[str, Any] = dict(model=model, input=items, stream=True, store=False,
                                  prompt_cache_key=PROMPT_CACHE_KEY)
    if system:
        kwargs["instructions"] = system
    if tools:
        kwargs["tools"] = [{"type": "function", "name": t["name"], "description": t["description"],
                            "parameters": t["parameters"], "strict": True} for t in tools]
        kwargs["parallel_tool_calls"] = True
    if effort:
        kwargs["reasoning"] = {"effort": effort}
        if effort != "none":
            kwargs["include"] = ["reasoning.encrypted_content"]
    if json_mode:
        kwargs["text"] = {"format": {"type": "json_object"}}
    if max_output_tokens:
        kwargs["max_output_tokens"] = max_output_tokens
    if service_tier:
        kwargs["service_tier"] = service_tier

    text, final = [], None
    for ev in client.with_options(timeout=timeout).responses.create(**kwargs):
        if ev.type == "response.output_text.delta":
            text.append(ev.delta)
            emit(ev.delta)
        elif ev.type in ("response.completed", "response.incomplete"):
            final = ev.response
        elif ev.type in ("response.failed", "error"):
            raise LLMError(f"OpenAI stream failed: {getattr(ev, 'response', ev)}")
    if final is None:
        raise LLMError("OpenAI stream ended without a response")
    calls = [ToolCall(o.call_id, o.name, o.arguments) for o in final.output if o.type == "function_call"]
    u = final.usage
    in_det, out_det = getattr(u, "input_tokens_details", None), getattr(u, "output_tokens_details", None)
    usage = Usage(input_tokens=u.input_tokens, output_tokens=u.output_tokens,
                  cached_input_tokens=getattr(in_det, "cached_tokens", 0) or 0,
                  cache_write_tokens=getattr(in_det, "cache_write_tokens", 0) or 0,
                  reasoning_tokens=getattr(out_det, "reasoning_tokens", 0) or 0)
    native = [o.model_dump(exclude_none=True) for o in final.output] if calls else None
    return "".join(text), calls, usage, native, getattr(final, "service_tier", None)


# ── Google Gemini (google-genai) ────────────────────────────────────────────

def _gemini_call(client, model, system, messages, tools, effort, emit, json_mode,
                 max_output_tokens, timeout, service_tier):
    from google.genai import types

    contents: List[Any] = []
    tool_turn = None  # consecutive tool results share one user Content
    for m in messages:
        if m["role"] == "tool":
            part = types.Part(function_response=types.FunctionResponse(
                id=m["tool_call_id"], name=m["name"], response={"result": m["content"]}))
            if tool_turn is not None and contents and contents[-1] is tool_turn:
                tool_turn.parts.append(part)
            else:
                tool_turn = types.Content(role="user", parts=[part])
                contents.append(tool_turn)
            continue
        if m.get("native", {}).get("gemini"):
            contents.append(types.Content.model_validate(m["native"]["gemini"]))
        elif m.get("tool_calls"):
            parts = [types.Part(text=m["content"])] if m.get("content") else []
            parts += [types.Part(function_call=types.FunctionCall(id=c["id"], name=c["name"],
                                                                  args=json.loads(c["arguments"] or "{}")))
                      for c in m["tool_calls"]]
            contents.append(types.Content(role="model", parts=parts))
        else:
            contents.append(types.Content(role="user" if m["role"] == "user" else "model",
                                          parts=[types.Part(text=m["content"])]))
    config = types.GenerateContentConfig(
        system_instruction=system or None,
        max_output_tokens=max_output_tokens,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        http_options=types.HttpOptions(timeout=int(timeout * 1000)),
    )
    if tools:
        config.tools = [types.Tool(function_declarations=[types.FunctionDeclaration(
            name=t["name"], description=t["description"], parameters_json_schema=t["parameters"])
            for t in tools])]
    if effort:
        config.thinking_config = types.ThinkingConfig(thinking_level="minimal" if effort == "none" else effort)
    if json_mode:
        config.response_mime_type = "application/json"

    text, parts, meta = [], [], None
    for chunk in client.models.generate_content_stream(model=model, contents=contents, config=config):
        meta = chunk.usage_metadata or meta
        for cand in (chunk.candidates or [])[:1]:
            for p in (cand.content.parts if cand.content and cand.content.parts else []):
                parts.append(p)
                if p.text and not p.thought:
                    text.append(p.text)
                    emit(p.text)
    calls = [ToolCall(p.function_call.id or f"call_{i}", p.function_call.name,
                      json.dumps(p.function_call.args or {}))
             for i, p in enumerate(parts) if p.function_call]
    thoughts = getattr(meta, "thoughts_token_count", 0) or 0
    usage = Usage(input_tokens=getattr(meta, "prompt_token_count", 0) or 0,
                  cached_input_tokens=getattr(meta, "cached_content_token_count", 0) or 0,
                  output_tokens=(getattr(meta, "candidates_token_count", 0) or 0) + thoughts,
                  reasoning_tokens=thoughts)
    native = types.Content(role="model", parts=parts).model_dump(exclude_none=True, mode="json") if calls else None
    return "".join(text), calls, usage, native, None


# ── Anthropic ───────────────────────────────────────────────────────────────

def _anthropic_call(client, model, system, messages, tools, effort, emit, json_mode,
                    max_output_tokens, timeout, service_tier):
    msgs: List[Dict[str, Any]] = []
    for m in messages:
        if m["role"] == "tool":
            block = {"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": m["content"]}
            if msgs and msgs[-1]["role"] == "user" and isinstance(msgs[-1]["content"], list) \
                    and msgs[-1]["content"][0].get("type") == "tool_result":
                msgs[-1]["content"].append(block)
            else:
                msgs.append({"role": "user", "content": [block]})
        elif m.get("native", {}).get("anthropic"):
            msgs.append({"role": "assistant", "content": m["native"]["anthropic"]})
        elif m.get("tool_calls"):
            blocks = [{"type": "text", "text": m["content"]}] if m.get("content") else []
            blocks += [{"type": "tool_use", "id": c["id"], "name": c["name"],
                        "input": json.loads(c["arguments"] or "{}")} for c in m["tool_calls"]]
            msgs.append({"role": "assistant", "content": blocks})
        else:
            msgs.append({"role": m["role"], "content": m["content"]})
    sys_text = system + ("\nRespond with a single JSON object only." if json_mode else "")
    kwargs: Dict[str, Any] = dict(model=model, max_tokens=max_output_tokens or 4096, messages=msgs,
                                  timeout=timeout, cache_control={"type": "ephemeral"})
    if sys_text:
        kwargs["system"] = [{"type": "text", "text": sys_text, "cache_control": {"type": "ephemeral"}}]
    if tools:
        kwargs["tools"] = [{"name": t["name"], "description": t["description"],
                            "input_schema": t["parameters"], "strict": True} for t in tools]
        kwargs["tools"][-1]["cache_control"] = {"type": "ephemeral"}
    if effort in ("low", "medium", "high"):
        kwargs["output_config"] = {"effort": effort}

    text = []
    with client.messages.stream(**kwargs) as stream:
        for delta in stream.text_stream:
            text.append(delta)
            emit(delta)
        final = stream.get_final_message()
    calls = [ToolCall(b.id, b.name, json.dumps(b.input)) for b in final.content if b.type == "tool_use"]
    u = final.usage
    read, write = u.cache_read_input_tokens or 0, u.cache_creation_input_tokens or 0
    usage = Usage(input_tokens=u.input_tokens + read + write, cached_input_tokens=read,
                  cache_write_tokens=write, output_tokens=u.output_tokens)
    native = [b.model_dump(exclude_none=True) for b in final.content] if calls else None
    return "".join(text), calls, usage, native, None
