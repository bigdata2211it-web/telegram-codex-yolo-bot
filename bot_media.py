import json
import os
import re
import shlex
import subprocess
import time
import urllib.request
from pathlib import Path

from bot_state import ROOT
from bot_state import UPLOADS_DIR
from bot_telegram import telegram
from bot_telegram import telegram_file_url


def stt_command_config():
    command = os.environ.get("STT_COMMAND")
    if not command:
        venv_python = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        return [str(venv_python), str(ROOT / "scripts" / "transcribe_voice.py")]
    return shlex.split(command)


def stt_model():
    return os.environ.get("STT_MODEL", "base")


def stt_device():
    return os.environ.get("STT_DEVICE", "cpu")


def stt_compute_type():
    return os.environ.get("STT_COMPUTE_TYPE", "int8")


def safe_filename(name):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name or "upload")
    return cleaned.strip("._") or "upload"


def extension_from_file_path(file_path, fallback):
    suffix = Path(file_path or "").suffix
    return suffix if suffix else fallback


def download_telegram_file(file_id, filename_hint, fallback_ext):
    file_info = telegram("getFile", {"file_id": file_id}, timeout=30)
    file_path = file_info["file_path"]
    ext = extension_from_file_path(file_path, fallback_ext)
    filename = f"{int(time.time())}_{safe_filename(filename_hint)}{ext}"
    local_path = UPLOADS_DIR / filename
    with urllib.request.urlopen(telegram_file_url(file_path), timeout=120) as response:
        local_path.write_bytes(response.read())
    return local_path


def collect_attachments(message):
    attachments = []
    if message.get("photo"):
        photo = max(message["photo"], key=lambda item: item.get("file_size", 0))
        path = download_telegram_file(photo["file_id"], f"photo_{photo.get('file_unique_id', 'image')}", ".jpg")
        attachments.append({"kind": "image", "path": path})
    if message.get("video"):
        video = message["video"]
        path = download_telegram_file(video["file_id"], video.get("file_name") or "video", ".mp4")
        attachments.append({"kind": "video", "path": path})
    if message.get("voice"):
        voice = message["voice"]
        path = download_telegram_file(voice["file_id"], f"voice_{voice.get('file_unique_id', 'audio')}", ".oga")
        attachments.append({"kind": "voice", "path": path})
    if message.get("audio"):
        audio = message["audio"]
        path = download_telegram_file(audio["file_id"], audio.get("file_name") or "audio", ".mp3")
        attachments.append({"kind": "audio", "path": path})
    if message.get("document"):
        document = message["document"]
        mime_type = document.get("mime_type", "")
        path = download_telegram_file(document["file_id"], document.get("file_name") or "document", "")
        kind = "image" if mime_type.startswith("image/") else "file"
        attachments.append({"kind": kind, "path": path})
    return attachments


def transcribe_audio(path, language, timeout):
    cmd = stt_command_config() + [
        str(path),
        "--model",
        stt_model(),
        "--language",
        language,
        "--device",
        stt_device(),
        "--compute-type",
        stt_compute_type(),
    ]
    result = subprocess.run(
        cmd,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-2000:] or result.stdout[-2000:] or "speech transcription failed")
    return json.loads(result.stdout.strip())


def prompt_with_attachments(text, attachments):
    text = text or "Опиши вложение."
    if not attachments:
        return text
    non_images = [item for item in attachments if item["kind"] != "image"]
    if not non_images:
        return text
    lines = [text, "", "Локальные вложения:"]
    for item in non_images:
        lines.append(f"- {item['kind']}: {item['path']}")
    lines.append("Если нужно, используй локальные инструменты для чтения этих файлов.")
    return "\n".join(lines)


def prompt_with_transcripts(prompt, transcripts):
    if not transcripts:
        return prompt
    lines = [prompt or "Ответь на голосовое сообщение.", "", "Расшифровка голосовых сообщений:"]
    for index, transcript in enumerate(transcripts, start=1):
        lines.append(
            f"{index}. language={transcript['language']} path={transcript['path']}\n{transcript['text']}"
        )
    return "\n".join(lines)
