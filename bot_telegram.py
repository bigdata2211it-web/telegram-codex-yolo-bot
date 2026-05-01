import json
import os
import re
import urllib.parse
import urllib.request


MAX_TELEGRAM_MESSAGE = 3900
MDV2_SPECIALS = set("_*[]()~`>#+-=|{}.!")


def require_env(name):
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def telegram(method, data=None, timeout=60):
    token = require_env("TELEGRAM_BOT_TOKEN")
    url = f"https://api.telegram.org/bot{token}/{method}"
    payload = {}
    for key, value in (data or {}).items():
        payload[key] = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value
    encoded = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(url, data=encoded)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read().decode("utf-8")
    parsed = json.loads(payload)
    if not parsed.get("ok"):
        raise RuntimeError(f"Telegram API error on {method}: {parsed!r}")
    return parsed["result"]


def telegram_file_url(file_path):
    token = require_env("TELEGRAM_BOT_TOKEN")
    return f"https://api.telegram.org/file/bot{token}/{file_path}"


def telegram_parse_mode():
    return os.environ.get("TELEGRAM_PARSE_MODE", "MarkdownV2").strip()


def escape_markdown_v2(text):
    return "".join(f"\\{char}" if char in MDV2_SPECIALS else char for char in text)


def format_inline_markdown(line):
    placeholders = []

    def stash(value):
        placeholders.append(value)
        return f"\x00{len(placeholders) - 1}\x00"

    line = re.sub(r"`([^`\n]+)`", lambda m: stash(f"`{escape_markdown_v2(m.group(1))}`"), line)
    escaped = escape_markdown_v2(line)
    escaped = re.sub(r"\\\*\\\*(.+?)\\\*\\\*", r"*\1*", escaped)
    escaped = re.sub(r"(?<!\\)\\\*([^*\n]+?)\\\*", r"_\1_", escaped)
    for index, value in enumerate(placeholders):
        escaped = escaped.replace(f"\x00{index}\x00", value)
    return escaped


def markdown_to_telegram(text):
    text = text or ""
    parts = re.split(r"(```.*?```)", text, flags=re.DOTALL)
    rendered = []
    for part in parts:
        if part.startswith("```") and part.endswith("```"):
            body = part[3:-3]
            if body.startswith("\n"):
                body = body[1:]
            rendered.append(f"```{escape_markdown_v2(body)}```")
        else:
            rendered.append("\n".join(format_inline_markdown(line) for line in part.splitlines()))
    return "".join(rendered)


def send_message(chat_id, text, reply_markup=None):
    text = text or "(empty response)"
    for start in range(0, len(text), MAX_TELEGRAM_MESSAGE):
        chunk = text[start : start + MAX_TELEGRAM_MESSAGE]
        payload = {"chat_id": chat_id, "text": chunk}
        if reply_markup and start == 0:
            payload["reply_markup"] = reply_markup
        parse_mode = telegram_parse_mode()
        if parse_mode == "MarkdownV2":
            try:
                markdown_payload = dict(payload)
                markdown_payload["text"] = markdown_to_telegram(chunk)
                markdown_payload["parse_mode"] = "MarkdownV2"
                telegram("sendMessage", markdown_payload, timeout=30)
                continue
            except Exception as exc:
                print(f"MarkdownV2 send failed, falling back to plain text: {exc}", flush=True)
        telegram("sendMessage", payload, timeout=30)
