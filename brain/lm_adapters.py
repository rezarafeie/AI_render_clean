"""Wire-format adapters. No arbitrary URL, shell, or model-produced code execution."""
from __future__ import annotations

PATHS = {"chat": "chat/completions", "responses": "responses", "messages": "messages", "embeddings": "embeddings",
         "image": "images/generations", "speech": "audio/speech", "transcription": "audio/transcriptions", "video": "videos/generations"}


def payload(endpoint, model, messages, *, tokens=4096, temperature=None, stream=False, extra=None):
    data = {"model": model}
    if endpoint == "chat":
        data.update(messages=messages, max_tokens=tokens)
    elif endpoint == "responses":
        data.update(input=messages, max_output_tokens=tokens)
    elif endpoint == "messages":
        data.update(messages=[m for m in messages if m["role"] != "system"], max_tokens=tokens)
        system = [m["content"] for m in messages if m["role"] == "system"]
        if system: data["system"] = "\n".join(system)
    elif endpoint == "embeddings":
        data["input"] = messages
    elif endpoint == "image":
        data['prompt'] = messages
    else:
        raise ValueError("Media endpoints require a separately verified media adapter")
    if endpoint != "embeddings":
        if temperature is not None: data["temperature"] = temperature
        if stream: data["stream"] = True
    if extra: data.update(extra)
    return data


def text(endpoint, data):
    if endpoint == "chat":
        choices = data.get("choices") or []
        value = choices[0].get("message", {}).get("content") if choices else None
        if isinstance(value, str): return value
        if isinstance(value, list): return "".join(p.get("text", "") for p in value if p.get("type") == "text")
    elif endpoint == "responses":
        return data.get("output_text") or "".join(p.get("text", "") for item in data.get("output", [])
                    for p in item.get("content", []) if p.get("type") == "output_text")
    elif endpoint == "messages":
        return "".join(p.get("text", "") for p in data.get("content", []) if p.get("type") == "text")
    return ""


def usage(data):
    """Tokens of one answer. `input_tokens` is everything sent (cached part included); the cached parts are reported separately so they can be priced apart."""
    value = data.get("usage") or {}
    prompt = value.get("prompt_tokens", value.get("input_tokens"))
    details = value.get("prompt_tokens_details") or value.get("input_tokens_details") or {}
    read = value.get("cache_read_input_tokens", details.get("cached_tokens") if isinstance(details, dict) else None)
    write = value.get("cache_creation_input_tokens")
    if "prompt_tokens" not in value and (read or write) and prompt is not None:
        prompt = int(prompt) + int(read or 0) + int(write or 0)      # Anthropic style: input_tokens excludes the cache, so add it back
    out = {"input_tokens": prompt,
           "output_tokens": value.get("completion_tokens", value.get("output_tokens")),
           "cache_read_tokens": int(read) if isinstance(read, (int, float)) and read else None,
           "cache_write_tokens": int(write) if isinstance(write, (int, float)) and write else None,
           "cost": value.get("cost") if isinstance(value.get("cost"), (int, float)) else None}
    return out
