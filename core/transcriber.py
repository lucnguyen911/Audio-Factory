import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any

from core.importer import validate_input_file, MediaImportError
from core.subtitle_exporter import TranscriptSegment

class TranscriptionError(Exception):
    """Exception raised for errors during media transcription."""
    pass


@dataclass
class TranscriptionOptions:
    model_size: str = "base"
    language: Optional[str] = None
    device: str = "cpu"
    compute_type: str = "int8"
    beam_size: int = 5
    vad_filter: bool = True
    word_timestamps: bool = False


PRESETS: Dict[str, str] = {
    "fast": "base",
    "balanced": "small",
    "accurate": "medium",
    "best": "large-v3"
}


def model_size_from_preset(preset: str) -> str:
    """
    Map preset to whisper model size.
    Raises TranscriptionError if preset is not valid.
    """
    preset_lower = preset.lower()
    if preset_lower not in PRESETS:
        raise TranscriptionError(
            f"Invalid preset '{preset}'. Valid options are: {', '.join(sorted(PRESETS.keys()))}"
        )
    return PRESETS[preset_lower]


def load_whisper_model(options: TranscriptionOptions) -> Any:
    """
    Lazy load faster-whisper model.
    Raises TranscriptionError if library is not installed or loading fails.
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise TranscriptionError(
            "The 'faster-whisper' package is not installed. "
            "Please run: pip install faster-whisper"
        ) from e

    try:
        model = WhisperModel(
            options.model_size,
            device=options.device,
            compute_type=options.compute_type
        )
        return model
    except Exception as e:
        raise TranscriptionError(f"Failed to load Whisper model '{options.model_size}': {e}") from e


def transcribe_media(
    input_path: Path,
    options: Optional[TranscriptionOptions] = None
) -> List[TranscriptSegment]:
    """
    Transcribe a media file to a list of TranscriptSegment.
    """
    if options is None:
        options = TranscriptionOptions()

    try:
        input_path_obj = validate_input_file(input_path)
    except MediaImportError as e:
        raise TranscriptionError(f"Invalid input file: {e}") from e

    model = load_whisper_model(options)

    try:
        # model.transcribe returns an iterable of segments and transcription info
        segments_iterable, _ = model.transcribe(
            str(input_path_obj),
            language=options.language,
            beam_size=options.beam_size,
            vad_filter=options.vad_filter,
            word_timestamps=options.word_timestamps
        )

        segments = []
        for idx, seg in enumerate(segments_iterable):
            text_str = str(seg.text).strip()
            if not text_str:
                continue

            segments.append(
                TranscriptSegment(
                    start=float(seg.start),
                    end=float(seg.end),
                    text=text_str,
                    index=idx + 1
                )
            )

        # Re-index to ensure sequential values if any empty items were filtered out
        for new_idx, seg in enumerate(segments):
            seg.index = new_idx + 1

        return segments

    except Exception as e:
        raise TranscriptionError(f"Error during audio transcription: {e}") from e


def transcribe_to_dicts(
    input_path: Path,
    options: Optional[TranscriptionOptions] = None
) -> List[Dict[str, Any]]:
    """
    Transcribe media file, returning a list of dictionaries with standard keys.
    """
    segments = transcribe_media(input_path, options)
    return [
        {
            "index": seg.index,
            "start": seg.start,
            "end": seg.end,
            "text": seg.text
        }
        for seg in segments
    ]
