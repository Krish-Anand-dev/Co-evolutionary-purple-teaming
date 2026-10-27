"""LLM client interface for the Blue agent.

Interface Contract section 4: all LLM calls go through ONE class owned by Prateek,
`generate(prompt, schema=None) -> (text, meta)`. Until his version lands we code against this
Protocol. `OllamaClient` is a minimal stand-in (stdlib only) so T09/T18 can run on the GPU PC;
swap it for Prateek's class without touching the agent.
"""
from __future__ import annotations

import json
import time
import urllib.request
from typing import Any, Protocol


class LLMClient(Protocol):
    def generate(self, prompt: str, schema: dict | None = None) -> tuple[str, dict[str, Any]]: ...


class LlamaServerClient:
    """llama.cpp `llama-server` (OpenAI-compatible /v1/chat/completions), as set up in C:\\AI\\Tools."""

    def __init__(self, base_url: str = "http://127.0.0.1:8080", model: str = "local", temperature: float = 0.2,
                 seed: int = 0, max_tokens: int = 1000, timeout_s: float = 900.0,
                 chat_template_kwargs: dict[str, Any] | None = None):
        self.base_url, self.model = base_url.rstrip("/"), model
        self.temperature, self.seed, self.max_tokens, self.timeout_s = temperature, seed, max_tokens, timeout_s
        # Gemma 4 / Qwen3 style models spend the whole token budget on hidden reasoning unless told not to.
        self.chat_template_kwargs = {"enable_thinking": False} if chat_template_kwargs is None else chat_template_kwargs

    def generate(self, prompt: str, schema: dict | None = None) -> tuple[str, dict[str, Any]]:
        body: dict[str, Any] = {
            "model": self.model, "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature, "seed": self.seed, "max_tokens": self.max_tokens,
            "chat_template_kwargs": self.chat_template_kwargs,
        }
        if schema is not None:
            body["response_format"] = {"type": "json_schema", "json_schema": {"name": "rules", "schema": schema}}
        req = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        start = time.perf_counter()
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
            payload = json.loads(resp.read())
        usage, timings = payload.get("usage", {}), payload.get("timings", {})
        meta = {
            "model": payload.get("model", self.model), "temperature": self.temperature, "seed": self.seed,
            "latency_s": time.perf_counter() - start,
            "tokens_in": usage.get("prompt_tokens"), "tokens_out": usage.get("completion_tokens"),
            "predicted_per_second": timings.get("predicted_per_second"),
            "finish_reason": payload["choices"][0].get("finish_reason"),
        }
        return payload["choices"][0]["message"].get("content") or "", meta


class OllamaClient:
    def __init__(self, model: str, temperature: float = 0.2, seed: int = 0,
                 host: str = "http://localhost:11434", timeout_s: float = 300.0):
        self.model, self.temperature, self.seed = model, temperature, seed
        self.host, self.timeout_s = host.rstrip("/"), timeout_s

    def generate(self, prompt: str, schema: dict | None = None) -> tuple[str, dict[str, Any]]:
        body: dict[str, Any] = {
            "model": self.model, "prompt": prompt, "stream": False,
            "options": {"temperature": self.temperature, "seed": self.seed},
        }
        if schema is not None:
            body["format"] = schema
        req = urllib.request.Request(
            f"{self.host}/api/generate", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        start = time.perf_counter()
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
            payload = json.loads(resp.read())
        meta = {
            "model": self.model, "temperature": self.temperature, "seed": self.seed,
            "latency_s": time.perf_counter() - start,
            "tokens_in": payload.get("prompt_eval_count"), "tokens_out": payload.get("eval_count"),
        }
        return payload.get("response", ""), meta
