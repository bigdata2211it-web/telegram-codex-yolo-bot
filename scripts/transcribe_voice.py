#!/usr/bin/env python3
import argparse
import json

from faster_whisper import WhisperModel


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("audio_path")
    parser.add_argument("--model", default="small")
    parser.add_argument("--language", default="ru")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--compute-type", default="int8")
    args = parser.parse_args()

    language = None if args.language == "auto" else args.language
    model = WhisperModel(args.model, device=args.device, compute_type=args.compute_type)
    segments, info = model.transcribe(args.audio_path, language=language, vad_filter=True)
    text = " ".join(segment.text.strip() for segment in segments).strip()
    print(
        json.dumps(
            {
                "text": text,
                "language": info.language,
                "language_probability": info.language_probability,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
