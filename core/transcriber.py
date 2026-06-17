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
    model_size: str = "large-v3-turbo"
    language: Optional[str] = None
    device: str = "cpu"
    compute_type: str = "int8"
    beam_size: int = 5
    vad_filter: bool = True
    word_timestamps: bool = False
    asr_audio_speed: float = 1.0
    batch_size: int = 8


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

    from core.language_options import resolve_language_code
    try:
        options.language = resolve_language_code(options.language)
    except ValueError as e:
        raise TranscriptionError(str(e)) from e

    try:
        input_path_obj = validate_input_file(input_path)
    except MediaImportError as e:
        raise TranscriptionError(f"Invalid input file: {e}") from e

    # Validate ASR audio speed
    if options.asr_audio_speed < 0.5 or options.asr_audio_speed > 2.0:
        raise TranscriptionError(f"ASR audio speed must be between 0.5 and 2.0. Received: {options.asr_audio_speed}")

    temp_speed_path = None
    transcription_source = input_path_obj

    # Create temporary speed-adjusted audio if speed is not 1.0
    if options.asr_audio_speed != 1.0:
        import tempfile
        from core.ffmpeg_runner import run_ffmpeg, FFmpegError

        temp_fd, temp_path_str = tempfile.mkstemp(suffix=".wav")
        os.close(temp_fd)
        temp_speed_path = Path(temp_path_str)

        args = [
            "-y",
            "-i", str(input_path_obj),
            "-filter:a", f"atempo={options.asr_audio_speed}",
            str(temp_speed_path)
        ]
        try:
            run_ffmpeg(args)
            transcription_source = temp_speed_path
        except FFmpegError as e:
            if temp_speed_path.exists():
                try:
                    os.unlink(temp_speed_path)
                except Exception:
                    pass
            raise TranscriptionError(f"Failed to create speed-adjusted audio for transcription: {e}") from e

    model = load_whisper_model(options)

    try:
        if options.batch_size > 1:
            from faster_whisper import BatchedInferencePipeline
            pipeline = BatchedInferencePipeline(model)
            segments_iterable, _ = pipeline.transcribe(
                str(transcription_source),
                language=options.language,
                beam_size=options.beam_size,
                vad_filter=options.vad_filter,
                word_timestamps=options.word_timestamps,
                batch_size=options.batch_size
            )
        else:
            segments_iterable, _ = model.transcribe(
                str(transcription_source),
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

            seg_start = float(seg.start)
            seg_end = float(seg.end)

            # Remap timestamps if speed is modified
            if options.asr_audio_speed != 1.0:
                seg_start = seg_start * options.asr_audio_speed
                seg_end = seg_end * options.asr_audio_speed

            # Extract word-level timestamps if requested/available
            words_list = None
            if options.word_timestamps and getattr(seg, "words", None) is not None:
                words_list = []
                for w in seg.words:
                    w_start = float(w.start)
                    w_end = float(w.end)
                    if options.asr_audio_speed != 1.0:
                        w_start = w_start * options.asr_audio_speed
                        w_end = w_end * options.asr_audio_speed
                    words_list.append({
                        "word": w.word,
                        "start": w_start,
                        "end": w_end,
                        "probability": getattr(w, "probability", 0.0)
                    })

            segments.append(
                TranscriptSegment(
                    start=seg_start,
                    end=seg_end,
                    text=text_str,
                    index=idx + 1,
                    words=words_list
                )
            )

        # Re-index to ensure sequential values
        for new_idx, seg in enumerate(segments):
            seg.index = new_idx + 1

        return segments

    except Exception as e:
        raise TranscriptionError(f"Error during audio transcription: {e}") from e
    finally:
        if temp_speed_path is not None and temp_speed_path.exists():
            try:
                os.unlink(temp_speed_path)
            except Exception:
                pass


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
            "text": seg.text,
            "words": seg.words
        }
        for seg in segments
    ]
