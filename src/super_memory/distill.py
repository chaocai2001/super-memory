"""Call an OpenAI-compatible chat API to distill transcripts into wiki ops."""

from __future__ import annotations

import json
import os
import re
import tomllib
import urllib.request
import urllib.error
from dataclasses import dataclass
from pathlib import Path

from .prompts import DISTILL_SYSTEM, build_distill_user_prompt


@dataclass
class LLMConfig:
    base_url: str
    api_key: str
    model: str


class DistillError(RuntimeError):
    pass


def _strip_jsonc(text: str) -> str:
    """Remove // and /* */ comments (string-aware) and trailing commas."""
    out = []
    i, n = 0, len(text)
    in_str = False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(c)
        i += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


def _opencode_llm_defaults() -> dict:
    """Read base_url/api_key/model from opencode config (~/.config/opencode/opencode.json[c])."""
    cfg: dict = {}
    for name in ("opencode.jsonc", "opencode.json"):
        path = Path.home() / ".config" / "opencode" / name
        if not path.is_file():
            continue
        try:
            cfg = json.loads(_strip_jsonc(path.read_text()))
        except (json.JSONDecodeError, OSError):
            continue
        if cfg:
            break
    providers = cfg.get("provider") or {}
    if not isinstance(providers, dict) or not providers:
        return {}
    disabled = set(cfg.get("disabled_providers") or [])

    provider_name = model = ""
    top_model = str(cfg.get("model") or "")
    if "/" in top_model:
        pname, mname = top_model.split("/", 1)
        if pname in providers:
            provider_name, model = pname, mname
    if not provider_name:
        provider_name = next((p for p in providers if p not in disabled), "")
    if not provider_name:
        return {}
    provider = providers.get(provider_name) or {}
    if not model:
        models = provider.get("models") or {}
        model = next(iter(models), "") if isinstance(models, dict) else ""

    options = provider.get("options") or {}
    base_url = options.get("baseURL") or options.get("baseUrl") or ""
    api_key = options.get("apiKey") or ""
    m = re.fullmatch(r"\{env:(\w+)\}", api_key)
    if m:
        api_key = os.environ.get(m.group(1), "")
    if not api_key:
        try:
            auth = json.loads((Path.home() / ".local" / "share" / "opencode" / "auth.json").read_text())
            entry = auth.get(provider_name) or {}
            api_key = entry.get("key") or ""
        except (json.JSONDecodeError, OSError):
            pass
    return {"base_url": base_url, "api_key": api_key, "model": model}


def load_config() -> LLMConfig:
    """Resolve API settings: env > ~/.codex/config.toml > opencode config."""
    base_url = os.environ.get("SUPER_MEMORY_BASE_URL", "")
    api_key = os.environ.get("SUPER_MEMORY_API_KEY", "")
    model = os.environ.get("SUPER_MEMORY_MODEL", "")

    if not (base_url and api_key and model):
        codex_cfg = Path.home() / ".codex" / "config.toml"
        if codex_cfg.is_file():
            try:
                cfg = tomllib.loads(codex_cfg.read_text())
            except (tomllib.TOMLDecodeError, OSError):
                cfg = {}
            provider_name = cfg.get("model_provider", "")
            provider = (cfg.get("model_providers") or {}).get(provider_name, {})
            if not base_url:
                base_url = provider.get("base_url", "")
            if not api_key:
                env_key = provider.get("env_key", "")
                api_key = os.environ.get(env_key, "") if env_key else ""
            if not model:
                model = cfg.get("model", "")

    if not (base_url and api_key and model):
        defaults = _opencode_llm_defaults()
        if not base_url:
            base_url = defaults.get("base_url", "")
        if not api_key:
            api_key = defaults.get("api_key", "")
        if not model:
            model = defaults.get("model", "")

    missing = [
        name
        for name, val in (("SUPER_MEMORY_BASE_URL", base_url), ("SUPER_MEMORY_API_KEY", api_key), ("SUPER_MEMORY_MODEL", model))
        if not val
    ]
    if missing:
        raise DistillError(
            "Missing LLM settings: " + ", ".join(missing) +
            ". Set them as environment variables or configure ~/.codex/config.toml"
            " or ~/.config/opencode/opencode.json."
        )
    return LLMConfig(base_url=base_url.rstrip("/"), api_key=api_key, model=model)


def _chat_completion(cfg: LLMConfig, messages: list[dict], use_json_mode: bool) -> str:
    body: dict = {
        "model": cfg.model,
        "messages": messages,
        "temperature": 0.2,
    }
    if use_json_mode:
        body["response_format"] = {"type": "json_object"}

    req = urllib.request.Request(
        cfg.base_url + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cfg.api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        detail = e.read()[:500].decode("utf-8", errors="replace")
        raise DistillError(f"LLM API HTTP {e.code}: {detail}") from e
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        raise DistillError(f"LLM API request failed: {e}") from e

    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise DistillError(f"Unexpected LLM response shape: {str(data)[:300]}") from e


def _extract_json(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        return json.loads(m.group(0))
    raise DistillError(f"Could not parse JSON from LLM output: {text[:300]}")


def validate_ops(data: dict) -> dict:
    ops = data.get("ops")
    if not isinstance(ops, list):
        raise DistillError("LLM output missing 'ops' list")
    clean = []
    for op in ops:
        if not isinstance(op, dict):
            continue
        if op.get("action") not in ("create", "append", "revise"):
            continue
        if not op.get("page") or not op.get("content"):
            continue
        clean.append(op)
    return {"ops": clean, "log_entry": str(data.get("log_entry", "")).strip()}


def distill(transcript_text: str, index_summary: str, session_id: str, date: str,
            cfg: LLMConfig | None = None) -> dict:
    cfg = cfg or load_config()
    messages = [
        {"role": "system", "content": DISTILL_SYSTEM},
        {"role": "user", "content": build_distill_user_prompt(transcript_text, index_summary, session_id, date)},
    ]
    try:
        raw = _chat_completion(cfg, messages, use_json_mode=True)
    except DistillError:
        raw = _chat_completion(cfg, messages, use_json_mode=False)
    return validate_ops(_extract_json(raw))
