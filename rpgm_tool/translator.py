"""Batch AI translator with glossary injection, control-code protection, and checkpointing."""

from __future__ import annotations

import hashlib
import json
import random
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .dictionary import get_untranslated, load_json_dict, save_json_dict
from .text_guard import protect_text, restore_text


DEFAULT_SYSTEM_PROMPT = (
    "You are a professional RPG game localizer translating game text into {target_lang}. "
    "Keep the tone natural, vivid, and faithful to RPG dialogue, UI labels, and item descriptions."
)


@dataclass
class TranslatorConfig:
    api_key: str = ""
    base_url: str = "https://api.deepseek.com/v1"
    model: str = "deepseek-chat"
    target_lang: str = "Simplified Chinese"
    custom_prompt: str = ""
    thinking_mode: str = "off"  # "off" | "low" | "default"
    batch_size: int = 50
    max_workers: int = 4
    timeout: float = 180.0
    max_retries: int = 3
    temperature: float = 0.2
    mode: str = "ai"  # "ai" | "mt"
    mt_provider: str = "google_free"  # "google_free" | "baidu"
    mt_endpoint: str = "https://translate.googleapis.com/translate_a/single"
    mt_app_id: str = ""
    mt_secret_key: str = ""


def _extract_json_payload(raw_content: str) -> dict:
    # Strip <think>...</think> blocks emitted by reasoning models (e.g. Qwen3 / DeepSeek-R1)
    text = re.sub(r"<think>[\s\S]*?</think>", "", raw_content, flags=re.IGNORECASE).strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Fallback: extract first {...} JSON block if model added surrounding prose
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


_NO_JSON_FORMAT_URLS: set[str] = set()
_NO_REASONING_EFFORT_URLS: set[str] = set()


def call_openai_compatible(
    config: TranslatorConfig,
    system_prompt: str,
    user_prompt: str,
    on_log: Callable[[str], None] | None = None,
) -> str:
    """Call an OpenAI-compatible chat completions endpoint using stdlib urllib."""
    url = config.base_url.rstrip("/") + "/chat/completions"
    api_key = config.api_key or "sk-local"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    use_json_format = url not in _NO_JSON_FORMAT_URLS
    use_reasoning_effort = (
        config.thinking_mode in ("off", "low") and url not in _NO_REASONING_EFFORT_URLS
    )
    last_err: Exception | None = None
    for attempt in range(config.max_retries):
        payload: dict = {
            "model": config.model,
            "temperature": config.temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if use_json_format:
            payload["response_format"] = {"type": "json_object"}
        if use_reasoning_effort:
            payload["reasoning_effort"] = "none" if config.thinking_mode == "off" else "low"

        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if on_log:
            on_log(
                f"[API ->] POST {url} | model={config.model} | thinking={config.thinking_mode if use_reasoning_effort else 'server-default'} "
                f"| json_fmt={use_json_format} | bytes={len(data)} | attempt={attempt + 1}/{config.max_retries}"
            )
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=config.timeout) as resp:
                raw_text = resp.read().decode("utf-8")
                dt = time.perf_counter() - t0
                body = json.loads(raw_text)
                usage = body.get("usage") or {}
                if on_log:
                    ct = usage.get("completion_tokens", "?")
                    pt = usage.get("prompt_tokens", "?")
                    rt = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens", 0)
                    on_log(
                        f"[API <-] {resp.status} OK ({dt:.2f}s) | prompt_tok={pt}, "
                        f"completion_tok={ct}, reasoning_tok={rt}"
                    )
                return body["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as exc:
            dt = time.perf_counter() - t0
            err_body = ""
            try:
                err_body = exc.read().decode("utf-8", errors="replace").strip()
            except Exception:
                pass
            last_err = RuntimeError(f"HTTP {exc.code} {exc.reason}" + (f": {err_body}" if err_body else ""))
            if on_log:
                on_log(f"[API <-] HTTP {exc.code} ({dt:.2f}s): {err_body[:200]}")
            # Selectively disable only the unsupported field instead of dropping reasoning_effort!
            if exc.code in (400, 422):
                lower_err = err_body.lower()
                changed = False
                if use_json_format and ("response_format" in lower_err or "structured" in lower_err or not use_reasoning_effort):
                    use_json_format = False
                    _NO_JSON_FORMAT_URLS.add(url)
                    changed = True
                if use_reasoning_effort and ("reasoning_effort" in lower_err or not changed):
                    if "reasoning_effort" in lower_err or ("response_format" not in lower_err and "structured" not in lower_err):
                        use_reasoning_effort = False
                        _NO_REASONING_EFFORT_URLS.add(url)
                        changed = True
                if changed:
                    if on_log:
                        on_log(
                            f"[API !] 自动降级重试 (json_fmt={use_json_format}, reasoning_effort={use_reasoning_effort})"
                        )
                    continue
            if attempt + 1 < config.max_retries:
                time.sleep(1.5 * (2**attempt))
        except (urllib.error.URLError, KeyError, json.JSONDecodeError, TimeoutError) as exc:
            dt = time.perf_counter() - t0
            last_err = exc
            if on_log:
                on_log(f"[API ERR] ({dt:.2f}s) {type(exc).__name__}: {exc}")
            if attempt + 1 < config.max_retries:
                time.sleep(1.5 * (2**attempt))
    raise RuntimeError(f"Translation API failed after {config.max_retries} attempts: {last_err}")


def _build_prompts(
    protected_items: list[str],
    glossary: dict[str, str],
    target_lang: str,
    custom_prompt: str = "",
) -> tuple[str, str]:
    relevant_terms = {
        src: dst
        for src, dst in glossary.items()
        if dst and any(src in item for item in protected_items)
    }

    base_instruction = (
        custom_prompt.strip().replace("{target_lang}", target_lang)
        if custom_prompt and custom_prompt.strip()
        else DEFAULT_SYSTEM_PROMPT.format(target_lang=target_lang)
    )

    system_lines = [
        base_instruction,
        "",
        "Strict Output & Format Rules:",
        "1. Preserve every placeholder token like ⟦0⟧, ⟦1⟧, etc. exactly as-is without translating or removing them.",
        '2. Return ONLY a valid JSON object of the form: {"items": [{"id": 0, "text": "..."}, ...]} matching every input id.',
    ]
    if relevant_terms:
        glossary_block = "\n".join(f"- {k} => {v}" for k, v in relevant_terms.items())
        system_lines.append(f"Glossary (must follow consistently):\n{glossary_block}")

    user_payload = {
        "items": [{"id": idx, "text": text} for idx, text in enumerate(protected_items)]
    }
    return "\n".join(system_lines), json.dumps(user_payload, ensure_ascii=False)


def _translate_mt_single(text: str, config: TranslatorConfig) -> str:
    """Translate a single protected string via configured machine translation API."""
    if config.mt_provider == "baidu":
        if not config.mt_app_id or not config.mt_secret_key:
            raise ValueError("百度翻译需要配置 AppID 和 Secret Key")
        salt = str(random.randint(32768, 65536))
        sign = hashlib.md5(f"{config.mt_app_id}{text}{salt}{config.mt_secret_key}".encode("utf-8")).hexdigest()
        params = urllib.parse.urlencode(
            {
                "q": text,
                "from": "auto",
                "to": "zh",
                "appid": config.mt_app_id,
                "salt": salt,
                "sign": sign,
            }
        )
        url = f"{config.mt_endpoint.rstrip('?')}?{params}"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=config.timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        if "trans_result" not in body:
            raise RuntimeError(f"Baidu MT error: {body}")
        return "\n".join(seg["dst"] for seg in body["trans_result"])

    # Default: Google GTX public endpoint (supports custom mirror via mt_endpoint)
    tl = "zh-CN" if "Chinese" in config.target_lang or "zh" in config.target_lang.lower() else config.target_lang
    params = urllib.parse.urlencode(
        {"client": "gtx", "sl": "auto", "tl": tl, "dt": "t", "q": text}
    )
    base = config.mt_endpoint or "https://translate.googleapis.com/translate_a/single"
    url = f"{base.rstrip('?')}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}, method="GET")
    with urllib.request.urlopen(req, timeout=config.timeout) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    if not isinstance(body, list) or not body or not isinstance(body[0], list):
        raise RuntimeError(f"Unexpected MT response: {body}")
    return "".join(seg[0] for seg in body[0] if isinstance(seg, list) and seg and seg[0])


def translate_batch(
    sources: list[str],
    config: TranslatorConfig,
    glossary: dict[str, str] | None = None,
    llm_caller: Callable[[TranslatorConfig, str, str], str] | None = None,
    on_log: Callable[[str], None] | None = None,
) -> dict[str, str]:
    """Translate a single batch of source strings while protecting control codes."""
    if config.mode == "mt":
        results: dict[str, str] = {}
        t0 = time.perf_counter()
        if on_log:
            on_log(f"[MT ->] {config.mt_provider} | batch={len(sources)} 条")
        for src in sources:
            p_text, tokens = protect_text(src)
            tr_p = _translate_mt_single(p_text, config)
            results[src] = restore_text(tr_p, tokens)
        if on_log:
            on_log(f"[MT <-] 完成 {len(results)}/{len(sources)} 条 ({time.perf_counter() - t0:.2f}s)")
        return results

    glossary = glossary or {}
    protected_list: list[str] = []
    tokens_list: list[list[str]] = []

    for src in sources:
        p_text, tokens = protect_text(src)
        protected_list.append(p_text)
        tokens_list.append(tokens)

    sys_prompt, usr_prompt = _build_prompts(
        protected_list, glossary, config.target_lang, config.custom_prompt
    )
    if llm_caller is not None:
        raw_resp = llm_caller(config, sys_prompt, usr_prompt)
    else:
        raw_resp = call_openai_compatible(config, sys_prompt, usr_prompt, on_log=on_log)
    try:
        parsed = _extract_json_payload(raw_resp)
    except (json.JSONDecodeError, ValueError) as exc:
        if len(sources) > 1:
            mid = len(sources) // 2
            if on_log:
                on_log(f"[解析 !] JSON 解析失败 ({exc})，自动拆半重试 ({mid} + {len(sources) - mid})")
            left = translate_batch(sources[:mid], config, glossary, llm_caller, on_log)
            right = translate_batch(sources[mid:], config, glossary, llm_caller, on_log)
            left.update(right)
            return left
        raise

    items = parsed.get("items")
    if not isinstance(items, list):
        raise ValueError(f"Unexpected response schema (missing 'items' list): {parsed}")

    id_to_text: dict[int, str] = {}
    for entry in items:
        if isinstance(entry, dict) and "id" in entry and "text" in entry:
            id_to_text[int(entry["id"])] = str(entry["text"])

    results = {}
    for idx, src in enumerate(sources):
        if idx in id_to_text:
            results[src] = restore_text(id_to_text[idx], tokens_list[idx])
    if on_log:
        on_log(f"[解析] 成功映射 {len(results)}/{len(sources)} 条")
    return results


def translate_dictionary_file(
    dict_path: str | Path,
    config: TranslatorConfig,
    glossary_path: str | Path | None = None,
    llm_caller: Callable[[TranslatorConfig, str, str], str] = call_openai_compatible,
    on_progress: Callable[[int, int], None] | None = None,
) -> tuple[int, int]:
    """Translate all untranslated entries in ManualTransFile.json with checkpoint saving.

    Returns (translated_now, total_untranslated).
    """
    data = load_json_dict(dict_path)
    glossary = load_json_dict(glossary_path) if glossary_path else {}
    pending = get_untranslated(data)
    total = len(pending)
    if total == 0:
        return 0, 0

    batches = [
        pending[i : i + config.batch_size]
        for i in range(0, total, max(1, config.batch_size))
    ]
    lock = threading.Lock()
    done_count = 0

    with ThreadPoolExecutor(max_workers=max(1, config.max_workers)) as pool:
        futures = {
            pool.submit(translate_batch, batch, config, glossary, llm_caller): batch
            for batch in batches
        }
        for future in as_completed(futures):
            batch_result = future.result()
            with lock:
                for src, dst in batch_result.items():
                    if dst:
                        data[src] = dst
                        done_count += 1
                save_json_dict(dict_path, data)
                if on_progress:
                    on_progress(done_count, total)

    return done_count, total


def test_translation_connection(config: TranslatorConfig) -> tuple[bool, str, int]:
    """Test AI or Machine Translation connectivity with a minimal sample.

    Returns (ok, message_or_translation, latency_ms).
    """
    t0 = time.perf_counter()
    sample = "こんにちは"
    try:
        if config.mode == "mt":
            res = translate_batch([sample], config)
        else:
            is_local = "127.0.0.1" in config.base_url or "localhost" in config.base_url
            if not config.api_key and not is_local:
                return False, "API Key 不能为空", 0
            res = translate_batch([sample], config)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        translated = res.get(sample, "")
        if translated:
            return True, translated, elapsed_ms
        return False, "接口返回为空", elapsed_ms
    except Exception as exc:  # noqa: BLE001
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        return False, str(exc), elapsed_ms
