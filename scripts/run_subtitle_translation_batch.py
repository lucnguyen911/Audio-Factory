"""Run ASR + SRT + Vietnamese translation for a fixed local audio batch.

All audio-altering options are deliberately disabled.  The saved Gemini keys
are read at runtime and are never printed to stdout.
"""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config_manager import load_config
from core.pipeline import PipelineOptions, run_batch_pipeline


def main() -> None:
    downloads = Path(r"C:\Users\lucng\Downloads")
    inputs = [downloads / f"{number}.mp3" for number in ("24", "25", "26", "27")]
    missing = [str(path) for path in inputs if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing input audio: " + ", ".join(missing))

    api_key = str(load_config().get("gemini_api_key", "")).strip()
    if not api_key:
        raise RuntimeError("No saved Gemini API key is configured.")

    options = PipelineOptions(
        merge_first=False,
        enable_voice_cleanup=False,
        enable_volume_leveling=False,
        enable_silence_shortening=False,
        enable_social_optimize=False,
        enable_transcription=True,
        enable_subtitle_export=True,
        enable_translation=True,
        translation_engine="gemini",
        translation_target_lang="vi",
        translation_api_key=api_key,
        output_format="mp3",
        project_name="AudioFactory_test_24_27",
        overwrite=True,
        transcription_preset="best",
        whisper_model="large-v3-turbo",
        asr_audio_speed=1.0,
        batch_size=8,
        target_video_format="horizontal",
        subtitle_lines=1,
    )

    output_dir = downloads / "AudioFactory_test_24_27"
    results = run_batch_pipeline(
        inputs,
        output_dir,
        options,
        status_callback=lambda message: print(message, flush=True),
    )
    print("BATCH_COMPLETED", flush=True)
    for result in results:
        print(f"RESULT input={result.input_files} subtitles={result.subtitle_files}", flush=True)


if __name__ == "__main__":
    main()
