"""Thin async client for the reasoning models (Groq, OpenAI-compatible)."""

from __future__ import annotations

import asyncio
import json
import re

import httpx

from .config import settings

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

_clients: dict[int, httpx.AsyncClient] = {}


class LLMError(RuntimeError):
    pass


def _http() -> httpx.AsyncClient:
    loop_id = id(asyncio.get_running_loop())     # one client per event loop
    c = _clients.get(loop_id)
    if c is None or c.is_closed:
        c = _clients[loop_id] = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0))
    return c


def _extract_json(text: str) -> dict:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise LLMError(f"no JSON object in model output: {text[:200]}")
    return json.loads(text[start:end + 1])


def _salvage_tool_call(resp: httpx.Response) -> dict | None:
    try:
        gen = resp.json()["error"]["failed_generation"]
        call = _extract_json(gen)
    except (KeyError, ValueError, LLMError):
        return None
    name = call.get("name")
    if not name:
        return None
    args = call.get("arguments") or call.get("args") or {}
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            args = {}
    if isinstance(args, dict) and "args" in args:
        args = args["args"] or {}
    return {"say": "", "tool": {"name": name, "args": args if isinstance(args, dict) else {}}}


_SPENT: dict[str, float] = {}     # model -> when its daily quota was found used up


async def chat_json(model: str, messages: list[dict], *, temperature: float = 0.7,
                    max_tokens: int = 900) -> dict:
    """Call a chat model and parse a JSON object from its reply.

    If the model's daily token quota is used up, the fast model answers instead (for an hour before
    the big one is tried again), so a person on a call never waits out a quota that won't come back."""
    import time as _t
    if model != settings.fast_model and _t.time() - _SPENT.get(model, 0) < 3600:
        model = settings.fast_model
    if not settings.groq_api_key:
        raise LLMError("GROQ_API_KEY is not set in .env")
    body: dict = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_completion_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    if model.startswith("openai/gpt-oss"):
        body["reasoning_effort"] = "low"
    last = ""
    start = _t.monotonic()
    for attempt in range(6):
        if _t.monotonic() - start > 40:          # someone is waiting on the other end
            break
        try:
            resp = await _http().post(
                GROQ_URL, json=body,
                headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            )
        except httpx.HTTPError as exc:
            last = str(exc)
            await asyncio.sleep(0.5 * (attempt + 1))
            continue
        if resp.status_code == 429 and "per day" not in resp.text and model != settings.fast_model:
            # per-minute limit on the big model (shared with Kavach): the fast model has its own budget
            return await chat_json(settings.fast_model, messages, temperature=temperature, max_tokens=max_tokens)
        if resp.status_code == 429 and "per day" in resp.text and model != settings.fast_model:
            _SPENT[model] = _t.time()
            return await chat_json(settings.fast_model, messages, temperature=temperature, max_tokens=max_tokens)
        if resp.status_code == 429 or resp.status_code >= 500:
            last = f"HTTP {resp.status_code}: {resp.text[:200]}"
            try:
                wait = float(resp.headers.get("retry-after") or 0)
            except ValueError:
                wait = 0
            await asyncio.sleep(min(8.0, max(wait, 1.0 * (attempt + 1))))
            continue
        if resp.status_code == 400 and "tool_use_failed" in resp.text:
            # gpt-oss sometimes emits a native tool call instead of our JSON contract.
            salvaged = _salvage_tool_call(resp)
            if salvaged:
                return salvaged
            last = resp.text[:200]
            continue
        if resp.status_code == 400 and "json_validate_failed" in resp.text:
            # The model produced something that wasn't valid JSON; try again.
            last = resp.text[:200]
            continue
        if resp.status_code >= 400:
            raise LLMError(f"HTTP {resp.status_code}: {resp.text[:300]}")
        content = resp.json()["choices"][0]["message"].get("content") or ""
        try:
            return _extract_json(content)
        except (LLMError, json.JSONDecodeError) as exc:
            last = str(exc)
            continue
    raise LLMError(f"{model} failed: {last}")
